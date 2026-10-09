"""Isolated learning orchestration; the translation worker is never invoked."""
from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import secrets
import shutil
import threading
import time

from .learning_contracts import LearningError, POLICY_VERSION, SUPPORTED_LANGUAGE_CODES, check_id, require, validate_source, word_count
from .learning_catalog import load_catalog
from .learning_vocabulary import effective_catalog
from .learning_controls import (DEFAULT_LEARNING_MODEL, auto_context_chars, learning_model_options,
                                validate_options, surrounding_context)
from .learning_archive import save_personal_archive
from .learning_import import import_hebrew_epub, import_translation_job
from .learning_planner import plan_book, replan_chunk
from .learning_generation import build_request, parse_response, build_chapter_recap
from .learning_lesson import (LESSON_OUTPUT_TOKENS, LESSON_STAGE, build_lesson_request, parse_lesson,
                              unavailable_lesson)
from .learning_dictionary import dictionary_view
from .learning_render import render_chunk
from .learning_store import LearningStore


# Failures that a resend cannot fix: they wait for the user.
_NOT_RETRIABLE = frozenset({'budget_exhausted', 'context_capacity', 'output_capacity', 'missing_api_key',
    'stale_learner', 'catalog_changed', 'accounting_unavailable', 'learning_save_failed', 'invalid_status',
    'already_running', 'session_not_found', 'provider_configuration'})


class LearningService:
    @staticmethod
    def _dense_output_cap(plan, configuration):
        selection, _ = configuration.resolve('translator')
        words = sum(word_count(unit['text']) for unit in plan['units'] if unit['kind'] == 'paragraph')
        # Each accepted occurrence has a structured offset/ID envelope. A growing
        # known vocabulary can replace most words, unlike the sparse first chapter.
        return min(selection.capabilities.max_output_tokens or 6000,
                   max(6000, min(64000, 2048 + words * 128)))

    @staticmethod
    def _with_reasoning(tokens, configuration):
        """Add the selected reasoning level's headroom (reasoning tokens count
        as output), within the model's output limit; none adds nothing."""
        from .reasoning_budget import review_reasoning_headroom
        selection = configuration.resolve('translator')[0]
        try:
            headroom = review_reasoning_headroom(selection)
        except ValueError:
            headroom = 0
        if not headroom:
            return tokens
        return min(tokens + headroom, selection.capabilities.max_output_tokens or tokens + headroom)

    def _shared_cap(self, job, configuration):
        # Part of the persistent task policy: identical for every call of a job.
        if job['plans'][0]['policy_version'] == 'learning-policy@1':
            return self._with_reasoning(job.get('output_tokens', 6000), configuration)
        return self._with_reasoning(max(job.get('output_tokens', 6000),
                                        max(self._dense_output_cap(p, configuration) for p in job['plans'])), configuration)

    @staticmethod
    def _chapter_ids(job):
        return list(dict.fromkeys(p['chapter_id'] for p in job['plans']))

    def _max_calls(self, job):
        # Jobs started with grammar lessons add at most one call per chapter.
        return len(job['plans']) + (len(self._chapter_ids(job)) if 'lessons' in job else 0)

    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.store = LearningStore(self.root / 'state')
        self._lock = threading.RLock()
        self._running = {}
        self._path = self.root / 'service.json'
        self._data = json.loads(self._path.read_text(encoding='utf-8')) if self._path.exists() else {'version': 1, 'books': {}, 'jobs': {}}
        require(self._data.get('version') == 1, 'unsupported_schema')
        self._data.setdefault('selected_language', 'fr')
        require(self._data['selected_language'] in SUPPORTED_LANGUAGE_CODES, 'unsupported_language')
        # Recover the small crash window between claiming a slot and saving
        # its service checkpoint. No provider call was possible in that window.
        for session in self.store.list_sessions():
            sid = session['session_id']
            if sid not in self._data['jobs'] and session['status'] == 'imported':
                from .model_settings import build_configuration
                learner = self.store.get_learner(session['language'])
                source = self.store.get_source(session['book_id'])
                self._data['jobs'][sid] = {'session_id': sid, 'status': 'paused', 'budget_usd': None,
                    'configuration': build_configuration({'translator': {'source': 'catalog', 'provider': 'openai', 'model': 'gpt-6-luna'}}).to_dict(),
                    'plans': plan_book(source, learner, effective_catalog(
                        load_catalog(session['language'], version=session['catalog_version']), session.get('vocabulary', [])),
                                       policy_version=session['policy_version']),
                    'current_plan': None, 'chunks': [], 'proposals': [], 'projected': learner,
                    'error_code': 'budget_required'}
        # A process restart never restarts model calls or borrows credentials.
        for job in self._data['jobs'].values():
            if (job.get('auto_retry') or {}).get('token'):
                job['auto_retry']['token'] = None
            session = self.store.get_session(job['session_id'])
            if session['status'] in ('ready', 'completed'):
                job['status'] = session['status']
            if job['status'] == 'preparing':
                job['status'] = 'paused'
                session = self.store.get_session(job['session_id'])
                if session['status'] == 'preparing':
                    session['status'] = 'paused'
                    self.store.update_session(session)
        self._save()

    def _save(self):
        temporary = self._path.with_name('.service-' + secrets.token_hex(12) + '.tmp')
        with temporary.open('w', encoding='utf-8') as stream:
            json.dump(self._data, stream, ensure_ascii=False, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        # Windows scanners can briefly hold the destination after a close.
        # Retry that sharing failure only; failed writes keep prior state and
        # the complete staged file, and never report success prematurely.
        for attempt in range(6):
            try:
                os.replace(temporary, self._path)
                return
            except PermissionError as error:
                if attempt == 5:
                    raise LearningError('learning_save_failed') from error
                time.sleep(.03 * (2 ** attempt))

    def _add_source(self, source, *, epub=None, asset_kind='original'):
        validate_source(source)
        with self._lock:
            if epub is not None:
                from .learning_assets import retain_epub
                retain_epub(self.root, source, epub, kind=asset_kind)
            self.store.save_source(source)
            self._data['books'][source['book_id']] = {'book_id': source['book_id'], 'title': source['title'],
                'origin': source['origin']['kind'], 'epub_layout': 'retained' if epub is not None else 'text_only'}
            self._save()
        return deepcopy(self._data['books'][source['book_id']])

    def import_epub(self, content, title=None):
        raw = bytes(content) if isinstance(content, (bytes, bytearray)) else Path(content).read_bytes()
        return self._add_source(import_hebrew_epub(raw, book_id='book-' + secrets.token_hex(12), title=title), epub=raw)

    def import_translation(self, snapshot, *, epub_template=None):
        return self._add_source(import_translation_job(snapshot, book_id='book-' + secrets.token_hex(12)),
                                epub=epub_template, asset_kind='translation_template')

    def _title(self, source):
        """The learner-facing name: a rename lives in the book index, never in
        the immutable source (its hash covers the imported title)."""
        return self._data['books'].get(source['book_id'], {}).get('title') or source['title']

    def rename_book(self, book_id, title):
        require(isinstance(title, str), 'invalid_title')
        title = ' '.join(title.split())
        require(0 < len(title) <= 500, 'invalid_title')
        with self._lock:
            book = self._data['books'].get(check_id(book_id))
            require(book is not None and not book.get('hidden'), 'book_not_found')
            book['title'] = title
            self._save()
            return deepcopy(book)

    def delete_book(self, book_id):
        """Remove a book from the list. A book under active learning is
        refused; one with learning history is only hidden, so its sessions,
        progress and notebook keep working; otherwise its files are removed."""
        with self._lock:
            book_id = check_id(book_id)
            book = self._data['books'].get(book_id)
            require(book is not None and not book.get('hidden'), 'book_not_found')
            require(not any(self.store.get_learner(code)['active_book_id'] == book_id
                            for code in SUPPORTED_LANGUAGE_CODES), 'book_in_use')
            if any(session['book_id'] == book_id for session in self.store.list_sessions()):
                book['hidden'] = True
                self._save()
                return {'book_id': book_id, 'deleted': 'hidden'}
            del self._data['books'][book_id]
            self._save()
            self.store.delete_source(book_id)
            shutil.rmtree(self.root / 'epub_assets' / book_id, ignore_errors=True)
            return {'book_id': book_id, 'deleted': 'removed'}

    def summary(self):
        with self._lock:
            language = self._data['selected_language']
            sessions = self.store.list_sessions(language)
            visible_sids = {session['session_id'] for session in sessions}
            jobs = {sid: {'accepted_chunks': len(j['chunks']), 'total_chunks': len(j['plans']),
                          'error_code': j.get('error_code'), 'status': j['status'], 'budget_usd': j['budget_usd'],
                          'usage': self._usage(sid)}
                    for sid, j in self._data['jobs'].items() if sid in visible_sids}
            learner = self.store.get_learner(language)
            for sid, job in jobs.items():
                original = self._data['jobs'][sid]
                job.update({'context_chars': original.get('context_chars', 0),
                            'output_tokens': original.get('output_tokens', 6000),
                            'context_info': original.get('context_info'),
                            'warnings': original.get('warnings', []),
                            'model': self._model_of(original),
                            'auto_retry': self._auto_retry_view(original)})
                if 'lessons' in original:
                    job.update({'lessons_done': len(original['lessons']),
                                'lessons_total': len(self._chapter_ids(original))})
            progress = self._progress(learner, sessions)
            archive = self._archive_snapshot(learner, progress=progress)
            books = [book for book in self._data['books'].values() if not book.get('hidden')]
            return {'books': deepcopy(books), 'sessions': sessions,
                    'learner': learner, 'jobs': jobs, 'progress': progress, 'personal_archive': archive,
                    'selected_language': language,
                    'languages': [{'id': code, 'available': True} for code in SUPPORTED_LANGUAGE_CODES],
                    'levels': load_catalog(language)['levels'], 'model': DEFAULT_LEARNING_MODEL,
                    'models': learning_model_options()}

    @staticmethod
    def _model_of(job):
        translator = job['configuration']['models']['translator']
        return {'model': translator['model'], 'reasoning': translator['capabilities'].get('reasoning')}

    @staticmethod
    def _auto_retry_view(job):
        state = job.get('auto_retry')
        if not state:
            return None
        return {'count': state['count'], 'wasted_usd': state['wasted_usd'],
                'retry_at': state.get('retry_at') if state.get('token') else None,
                'stopped': bool(state.get('stopped'))}

    def _archive_snapshot(self, learner, *, progress=None, chapter=None):
        language = learner['language']
        directory = str(self.root / 'personal' / language)
        try:
            progress = progress or self._progress(learner, self.store.list_sessions(language))
            result = save_personal_archive(self.root, language, progress, chapter)
            return {'path': directory, 'status': result['status'], 'warning': None}
        except (LearningError, OSError):
            # Reading and the durable completion transaction stay available;
            # the UI explicitly reports failure and reopening retries the archive.
            return {'path': directory, 'status': 'save_failed', 'warning': 'archive_save_failed'}

    def select_language(self, language):
        require(language in SUPPORTED_LANGUAGE_CODES, 'unsupported_language')
        with self._lock:
            require(not any(self.store.get_learner(code)['active_book_id']
                            for code in SUPPORTED_LANGUAGE_CODES), 'active_book_conflict')
            load_catalog(language)
            self._data['selected_language'] = language
            self._save()
            return self.summary()

    def _progress(self, learner, sessions):
        active_chunks = []
        if learner['active_book_id']:
            for session in sessions:
                if session['book_id'] == learner['active_book_id'] and session['base_learner_revision'] == learner['revision']:
                    active_chunks = self._data['jobs'].get(session['session_id'], {}).get('chunks', [])
                    break
        catalog = effective_catalog(load_catalog(learner['language']), learner.get('vocabulary', []), active_chunks)
        items = {item['item_id']: item for item in catalog['items']}
        entries, examples = dictionary_view(self._dictionary_sources(learner, sessions))
        def rows(counts, book_ids):
            result = []
            for item_id, count in counts.items():
                item = items.get(item_id, {})
                row = {'item_id': item_id, 'kind': item.get('kind', 'unknown'),
                    'foreign': item.get('lemma', item_id), 'hebrew': item.get('sense_he', ''),
                    'encounters': count, 'last_book_title': self._data['books'].get(book_ids[item_id], {}).get('title', '')}
                if item.get('kind') in ('word', 'phrase'):
                    row.update({'entry': deepcopy(entries.get(item_id)), 'examples': deepcopy(examples.get(item_id, []))})
                elif item.get('kind') == 'grammar':
                    row['explanation_he'] = item.get('explanation_he', '')
                result.append(row)
            return sorted(result, key=lambda row: (items.get(row['item_id'], {}).get('priority_tier', 999999), row['item_id']))
        completed = rows({row['item_id']: row['introduced_count'] for row in learner['items']},
                         {row['item_id']: row['last_completed_book_id'] for row in learner['items']})
        active = None
        if learner['active_book_id']:
            session = next((s for s in sessions if s['book_id'] == learner['active_book_id'] and
                            s['base_learner_revision'] == learner['revision']), None)
            if session:
                source = self.store.get_source(session['book_id'])
                job = self._data['jobs'].get(session['session_id'], {})
                cursor = session['read_cursor']
                chapter_index = cursor.get('chapter_index') if cursor else None
                furthest = cursor.get('furthest_chapter_index', chapter_index) if cursor else None
                visited = {chapter['chapter_id'] for i, chapter in enumerate(source['chapters'])
                           if furthest is not None and i <= furthest}
                counts = {}
                for plan, chunk in zip(job.get('plans', []), job.get('chunks', [])):
                    if plan['chapter_id'] in visited:
                        for edit in chunk['edits']:
                            for item_id in edit['item_ids'] + edit['grammar_ids']:
                                counts[item_id] = counts.get(item_id, 0) + 1
                active = {'book_id': session['book_id'], 'title': self._title(source),
                    'chapter_index': chapter_index, 'chapter_count': len(source['chapters']),
                    'read_items': rows(counts, {item_id: session['book_id'] for item_id in counts}),
                    'prepared_chunks': len(job.get('chunks', [])), 'total_chunks': len(job.get('plans', []))}
        return {'initial_word_goal': 500,
            'catalog_word_count': sum(item['kind'] == 'word' and
                item['min_level'] <= max(int(level['level_id']) for level in catalog['levels']) for item in catalog['items']),
            'completed_word_count': sum(row['kind'] == 'word' for row in completed),
            'completed_structure_count': sum(row['kind'] != 'word' for row in completed),
            'completed_items': completed, 'active_book': active}

    def _dictionary_sources(self, learner, sessions):
        # Completed books in full; the active book only up to the furthest visited chapter.
        sources = []
        for session in sessions:
            job = self._data['jobs'].get(session['session_id'])
            if job is None:
                continue
            title = self._data['books'].get(session['book_id'], {}).get('title', '')
            if session['status'] == 'completed':
                sources.append((title, job['plans'], job['chunks'], None))
            elif (session['book_id'] == learner['active_book_id']
                  and session['base_learner_revision'] == learner['revision']):
                cursor = session['read_cursor'] or {}
                furthest = cursor.get('furthest_chapter_index', cursor.get('chapter_index'))
                chapters = self.store.get_source(session['book_id'])['chapters']
                visited = {c['chapter_id'] for i, c in enumerate(chapters) if furthest is not None and i <= furthest}
                sources.append((title, job['plans'], job['chunks'], visited))
        return sources

    def _known_entry_ids(self, sid, language):
        known = {row['item_id'] for chunk in self._data['jobs'][sid]['chunks']
                 for row in chunk.get('dictionary_entries', [])}
        for session in self.store.list_sessions(language):
            if session['status'] == 'completed' and session['session_id'] in self._data['jobs']:
                known.update(row['item_id'] for chunk in self._data['jobs'][session['session_id']]['chunks']
                             for row in chunk.get('dictionary_entries', []))
        return known

    def grammar_notebook(self):
        """Every received chapter lesson of the selected language, by book; no model call."""
        with self._lock:
            language = self._data['selected_language']
            books = []
            for session in self.store.list_sessions(language):
                job = self._data['jobs'].get(session['session_id'])
                if session['status'] not in ('ready', 'completed') or not job or not job.get('lessons'):
                    continue
                source = self.store.get_source(session['book_id'])
                chapters = []
                for index, chapter in enumerate(source['chapters']):
                    lesson = job['lessons'].get(chapter['chapter_id'])
                    if lesson and lesson['status'] == 'ready':
                        chapters.append({'chapter_index': index, 'chapter_title': chapter['title'],
                                         'topics': lesson['topics'], 'paragraphs': lesson['paragraphs']})
                if chapters:
                    books.append({'session_id': session['session_id'], 'title': self._title(source),
                                  'status': session['status'], 'chapters': chapters})
            return {'language': language, 'books': deepcopy(books)}

    def _upgrade_inactive_learner(self, learner, catalog):
        require(learner['active_book_id'] is None, 'active_book_conflict')
        if learner['catalog_version'] != catalog['version'] or learner['support_mode'] != 'context':
            previous = effective_catalog(load_catalog(learner['language'], version=learner['catalog_version']),
                                         learner.get('vocabulary', []))
            old = {item['item_id']: item for item in previous['items']}
            latest = {item['item_id']: item for item in catalog['items']}
            require(all(row['item_id'] in latest and old.get(row['item_id']) == latest[row['item_id']]
                        for row in learner['items']), 'catalog_changed')
            learner = deepcopy(learner)
            learner.update({'catalog_version': catalog['version'], 'support_mode': 'context',
                            'revision': learner['revision'] + 1})
            self.store.save_learner(learner)
        return learner

    def _ledger_statuses(self, sid):
        from .runtime_controls import ControlStore, RuntimeControlsError
        directory = self.root / 'calls' / sid
        paths = [directory / 'controls.sqlite3'] + sorted(directory.glob('attempt-*/controls.sqlite3'))
        results = []
        for path in paths:
            if path.exists():
                try:
                    with ControlStore(path, create=False) as controls:
                        results.append((path, controls.status(sid)))
                except RuntimeControlsError as exc:
                    # A task-less ledger can result from a capacity rejection
                    # before the first reservation. Never ignore damaged costs.
                    if str(exc) != 'unknown task_id':
                        raise LearningError('accounting_unavailable') from exc
        return results

    def _usage(self, sid):
        try:
            rows = self._ledger_statuses(sid)
        except LearningError:
            return {'accounting_unavailable': True}
        if not rows:
            return None
        return {**{key: sum(row[key] for _, row in rows) for key in
                   ('attempted_calls', 'list_estimated_spent_usd', 'held_usd')},
                'stopped': self._data['jobs'][sid]['status'] == 'failed'}

    def set_effort(self, level_id):
        with self._lock:
            language = self._data['selected_language']
            learner = self.store.get_learner(language)
            require(learner['active_book_id'] is None, 'active_book_conflict')
            level = next((x for x in load_catalog(language)['levels'] if x['level_id'] == level_id), None)
            require(level is not None, 'unavailable_level')
            learner['level_id'], learner['support_mode'] = level_id, level['support_mode']
            # Version prevents stale plans from surviving an effort change.
            learner['revision'] += 1
            self.store.save_learner(learner)
            return learner

    def start(self, book_id, budget_usd, configuration, adapter_factory, *, background=True,
              context_chars=None, output_tokens=None):
        # Omitted limits are automatic: context sized per passage, answer
        # length sized per passage and grown after a cut-off answer.
        output_tokens = 6000 if output_tokens is None else output_tokens
        validate_options(budget_usd, 0 if context_chars is None else context_chars, output_tokens)
        with self._lock:
            source = self.store.get_source(check_id(book_id))
            language = self._data['selected_language']
            require(not any(self.store.get_learner(code)['active_book_id']
                            for code in SUPPORTED_LANGUAGE_CODES), 'active_book_conflict')
            saved = self.store.get_learner(language)
            catalog = effective_catalog(load_catalog(language), saved.get('vocabulary', []))
            learner = self._upgrade_inactive_learner(saved, catalog)
            plans = plan_book(source, learner, catalog, policy_version=POLICY_VERSION)
            session = self.store.create_session(source, learner)
            sid = session['session_id']
            self._data['jobs'][sid] = {'session_id': sid, 'status': 'paused', 'budget_usd': budget_usd,
                'configuration': configuration.to_dict(), 'plans': plans, 'current_plan': None,
                'chunks': [], 'proposals': [], 'projected': learner, 'error_code': None,
                'context_chars': context_chars, 'output_tokens': output_tokens, 'control_epoch': 0,
                'retry_revision': 0, 'warnings': [], 'lessons': {}, 'dictionary': True}
            self._save()
        self.resume(sid, adapter_factory, background=background)
        return self.store.get_session(sid)

    def resume(self, session_id, adapter_factory, *, background=True, budget_usd=None,
               context_chars=None, output_tokens=None, retry=False, _automatic=False):
        from .model_config import ModelConfiguration
        sid = check_id(session_id)
        with self._lock:
            require(sid in self._data['jobs'], 'session_not_found')
            require(sid not in self._running, 'already_running')
            session = self.store.get_session(sid)
            require(session['status'] in ('imported', 'preparing', 'paused', 'failed'), 'invalid_status')
            require(self.store.get_learner(session['language'])['revision'] == session['base_learner_revision'], 'stale_learner')
            load_catalog(session['language'], version=session['catalog_version'])
            job = self._data['jobs'][sid]
            options = (budget_usd if budget_usd is not None else job['budget_usd'],
                       context_chars if context_chars is not None else job.get('context_chars', 0),
                       output_tokens if output_tokens is not None else job.get('output_tokens', 6000))
            validate_options(options[0], 0 if options[1] is None else options[1], options[2])
            require(type(retry) is bool, 'invalid_learning_request')
            require(job['budget_usd'] is None or options[0] >= job['budget_usd'], 'budget_cannot_decrease')
            changed = options != (job['budget_usd'], job.get('context_chars', 0), job.get('output_tokens', 6000))
            if (changed or retry) and self._ledger_statuses(sid):
                job['control_epoch'] = job.get('control_epoch', 0) + 1
            if retry:
                job['retry_revision'] = job.get('retry_revision', 0) + 1
                job['pending_explicit_retry'] = True
            job.update(dict(zip(('budget_usd', 'context_chars', 'output_tokens'), options)))
            configuration = ModelConfiguration.from_dict(job['configuration'])
            job['status'], job['error_code'] = 'preparing', None
            if _automatic:
                job['auto_retry']['token'] = None
            else:
                job['auto_retry'] = None  # A user decision starts a fresh row.
            if not job.get('auto_retry'):
                job['retry_base_usd'] = self._spent(sid)
            session['status'] = 'preparing'
            self.store.update_session(session)
            self._running[sid] = threading.Event()
            self._save()
        if background:
            threading.Thread(target=self._run, args=(sid, configuration, adapter_factory), daemon=True).start()
        else:
            self._run(sid, configuration, adapter_factory)
        return self.store.get_session(sid)

    def job_configuration(self, session_id):
        """The model configuration a saved preparation was started with."""
        from .model_config import ModelConfiguration
        with self._lock:
            job = self._data['jobs'].get(check_id(session_id))
            require(job is not None, 'session_not_found')
            return ModelConfiguration.from_dict(job['configuration'])

    def pause(self, session_id):
        sid = check_id(session_id)
        with self._lock:
            require(sid in self._data['jobs'], 'session_not_found')
            waiting = self._data['jobs'][sid].get('auto_retry') or {}
            if sid in self._running:
                self._running[sid].set()
            elif waiting.get('token'):
                waiting['token'], waiting['stopped'] = None, True
                self._save()
            else:
                require(self.store.get_session(sid)['status'] == 'paused', 'invalid_status')
        return {'pause_requested': True}

    def abandon(self, session_id):
        sid = check_id(session_id)
        with self._lock:
            require(sid not in self._running, 'already_running')
            session = self.store.abandon_session(sid)
            self._data['jobs'][sid]['status'] = 'abandoned'
            self._save()
            return session

    def _run(self, sid, configuration, adapter_factory):
        from .chapter_pipeline import _controlled
        from .runtime_controls import ControlStore
        from .work_journal import WorkJournal
        directory = self.root / 'calls' / sid
        directory.mkdir(parents=True, exist_ok=True)
        delay = None
        try:
            epoch = self._data['jobs'][sid].get('control_epoch', 0)
            ledger = directory / f'attempt-{epoch}' / 'controls.sqlite3' if epoch else directory / 'controls.sqlite3'
            ledger.parent.mkdir(parents=True, exist_ok=True)
            prior = sum(row['list_estimated_spent_usd'] + row['held_usd']
                        for path, row in self._ledger_statuses(sid) if path != ledger)
            with ControlStore(ledger) as controls, WorkJournal(directory / 'journal.sqlite3') as journal:
                journal.resume(sid)
                with self._lock:
                    job = self._data['jobs'][sid]
                    if job.get('pending_explicit_retry', False):
                        for step in journal.job_steps(sid):
                            if step['status'] in ('unknown', 'dispatched'):
                                journal.mark_failed(step['identity'],
                                    'Outcome remains unknown; user authorized a distinct new attempt at retry '
                                    + str(job['retry_revision']) + '; original cost hold retained')
                        job['pending_explicit_retry'] = False
                        self._save()  # One choice must not authorize later lost calls.
                while True:
                    with self._lock:
                        job = self._data['jobs'][sid]
                        if self._running[sid].is_set():
                            self._finish_status(sid, 'paused')
                            return
                        index = len(job['chunks'])
                        if index == len(job['plans']):
                            break
                        session = self.store.get_session(sid)
                        catalog = effective_catalog(load_catalog(session['language'], version=session['catalog_version']),
                                                    session.get('vocabulary', []), job['chunks'])
                        if job['current_plan'] is None:
                            job['current_plan'] = replan_chunk(job['plans'][index], job['projected'], catalog)
                            self._save()  # Dispatch identity must survive a crash.
                        plan = deepcopy(job['current_plan'])
                        budget, count = job['budget_usd'] - prior, self._max_calls(job)
                        require(budget > 0, 'budget_exhausted')
                        requested = job.get('context_chars', 0)
                        if requested is None:
                            requested = auto_context_chars(plan)
                        context, job['context_info'] = surrounding_context(job['plans'], index, requested)
                        self._save()
                        known, needed = None, None
                        if job.get('dictionary'):
                            # Entries arrive once per item, in the response that first uses it.
                            known = self._known_entry_ids(sid, session['language'])
                            kinds = {item['item_id']: item['kind'] for item in catalog['items']}
                            needed = [item_id for item_id in plan['selected_item_ids']
                                      if kinds.get(item_id) in ('word', 'phrase') and item_id not in known]
                    prompt, input_hash = build_request(plan, catalog, context, dictionary_needed=needed)

                    def validate(result):
                        chunk, recap = parse_response(result.text, plan, catalog, input_hash,
                            provider=configuration.resolve('translator')[1].provider_type,
                            model=result.observed_model or configuration.resolve('translator')[0].model,
                            dictionary_known=sorted(known) if known is not None else None)
                        return {'chunk': chunk, 'recap': recap}

                    stage = {'learning-policy@1': 'learning-generate-v1',
                             'learning-policy@2': 'learning-generate-v2'}.get(plan['policy_version'], 'learning-generate-v3')
                    model_limit = configuration.resolve('translator')[0].capabilities.max_output_tokens or 6000
                    require(job.get('output_tokens', 6000) <= model_limit, 'output_capacity')
                    shared_cap = self._shared_cap(job, configuration)
                    if plan['policy_version'] == 'learning-policy@1':
                        output_cap = shared_cap
                    else:
                        output_cap = self._with_reasoning(max(job.get('output_tokens', 6000),
                            self._dense_output_cap(plan, configuration) if plan['review_item_ids'] else 0), configuration)
                    dependencies = {'plan': plan, 'catalog_version': catalog['version']}
                    if job.get('retry_revision', 0):
                        dependencies['explicit_retry'] = job['retry_revision']
                    from .model_adapter import PRICING_VERSION
                    controls.get_or_create_task(sid, count, budget, PRICING_VERSION, shared_cap)
                    try:
                        parsed, _replay = _controlled(sid, 'translator', stage, prompt,
                            configuration, output_cap, controls, journal, budget, count, shared_cap, validate,
                            dependencies, adapter_factory)
                    except Exception as exc:
                        if any(step['status'] in ('unknown', 'dispatched') for step in journal.job_steps(sid)):
                            raise LearningError('retry_confirmation_required') from exc
                        raise
                    with self._lock:
                        job = self._data['jobs'][sid]
                        job['chunks'].append(parsed['chunk'])
                        job['proposals'].append({'chunk_id': parsed['chunk']['plan_id'], 'recap': parsed['recap']})
                        definitions = parsed['chunk'].get('introduced_items', [])
                        if definitions:
                            vocabulary = job['projected'].setdefault('vocabulary', [])
                            known = {row['item']['item_id']: row['item'] for row in vocabulary}
                            for item in definitions:
                                require(item['item_id'] not in known or known[item['item_id']] == item,
                                        'catalog_changed')
                                if item['item_id'] not in known:
                                    vocabulary.append({'item': deepcopy(item), 'origin': {
                                        key: parsed['chunk'][key] for key in ('provider', 'model', 'prompt_version', 'input_hash')}})
                                    known[item['item_id']] = item
                        # Exposure projects choices within this book, without mastery or durable advancement.
                        accepted_counts = {}
                        for edit in parsed['chunk']['edits']:
                            for item_id in edit['item_ids'] + edit['grammar_ids']:
                                accepted_counts[item_id] = accepted_counts.get(item_id, 0) + 1
                        for item_id, encounters in accepted_counts.items():
                            existing = next((x for x in job['projected']['items'] if x['item_id'] == item_id), None)
                            if existing:
                                existing['introduced_count'] += encounters
                            else:
                                job['projected']['items'].append({'item_id': item_id, 'introduced_count': encounters,
                                    'last_completed_book_id': plan['book_id']})
                        job['current_plan'] = None
                        self._accepted(sid)
                        self._save()
                if 'lessons' in self._data['jobs'][sid]:
                    if not self._prepare_lessons(sid, configuration, adapter_factory, controls, journal, prior):
                        return
                with self._lock:
                    job = self._data['jobs'][sid]
                    chapter_ids = list(dict.fromkeys(p['chapter_id'] for p in job['plans']))
                    recaps = []
                    for chapter_id in chapter_ids:
                        indices = [i for i,p in enumerate(job['plans']) if p['chapter_id'] == chapter_id]
                        recap = build_chapter_recap(chapter_id, [job['chunks'][i] for i in indices],
                                                    [job['proposals'][i] for i in indices])
                        if job.get('lessons', {}).get(chapter_id):
                            recap['lesson'] = job['lessons'][chapter_id]
                        recaps.append(recap)
                    self.store.save_prepared(sid, job['chunks'], recaps)
                    job['status'] = 'ready'
                    self._save()
        except Exception as exc:
            # No exception/provider payload can leak credentials through the browser.
            with self._lock:
                message = str(exc).lower()
                code = exc.code if isinstance(exc, LearningError) else 'preparation_stopped'
                if 'budget' in message or 'reservation limit' in message:
                    code = 'budget_exhausted'
                elif 'does not fit' in message:
                    code = 'context_capacity'
                elif 'truncated' in message or 'provider response failed' in message:
                    code = 'response_incomplete'
                elif 'unknown' in message or 'automatic resend refused' in message:
                    code = 'retry_confirmation_required'
                self._data['jobs'][sid]['error_code'] = code
                session = self.store.get_session(sid)
                if session['status'] == 'ready':
                    self._data['jobs'][sid]['status'] = 'ready'
                    self._save()
                else:
                    from .model_adapter import OpenAIConfigurationError
                    retriable = (code not in _NOT_RETRIABLE and not self._running[sid].is_set()
                                 and not isinstance(exc, OpenAIConfigurationError))
                    self._finish_status(sid, 'failed')
                    delay = self._plan_auto_retry(sid) if retriable else None
        finally:
            with self._lock:
                self._running.pop(sid, None)
        if delay is not None:
            self._schedule(delay, self._auto_resume, (sid, self._data['jobs'][sid]['auto_retry']['token'], adapter_factory))

    @staticmethod
    def _schedule(delay, function, args):
        timer = threading.Timer(delay, function, args)
        timer.daemon = True
        timer.start()

    def _spent(self, sid):
        """Charges so far, uncertain holds included (worst case)."""
        try:
            return sum(row['list_estimated_spent_usd'] + row['held_usd'] for _, row in self._ledger_statuses(sid))
        except LearningError:
            return float('inf')  # Unknown cost never authorizes an automatic resend.

    def _accepted(self, sid):
        """A validated answer ends any failure row; later waste counts from here."""
        job = self._data['jobs'][sid]
        job['auto_retry'] = None
        job['retry_base_usd'] = self._spent(sid)

    def _plan_auto_retry(self, sid):
        """User rule (shared with translation, job_blocks): a failed, truncated,
        invalid or unknown-outcome answer is resent automatically while the
        charges of this failure row stay below AUTO_ACCEPT_BELOW_USD and the row
        is shorter than AUTO_ACCEPT_MAX_STREAK. Returns the wait in seconds,
        or None when the user decides."""
        from .job_blocks import AUTO_ACCEPT_BELOW_USD, AUTO_ACCEPT_MAX_STREAK, AUTO_RETRY_DELAYS
        job = self._data['jobs'][sid]
        count = (job.get('auto_retry') or {}).get('count', 0) + 1
        wasted = max(0.0, self._spent(sid) - job.get('retry_base_usd', 0.0))
        if wasted >= AUTO_ACCEPT_BELOW_USD or count > AUTO_ACCEPT_MAX_STREAK:
            job['auto_retry'] = {'count': count - 1, 'wasted_usd': min(wasted, 1e9), 'token': None, 'stopped': True}
            self._save()
            return None
        if job.get('error_code') == 'response_incomplete' and job.get('context_chars', 0) is None:
            # Automatic limits: a cut-off answer is resent with twice the room.
            from .model_config import ModelConfiguration
            limit = ModelConfiguration.from_dict(job['configuration']).resolve('translator')[0]                 .capabilities.max_output_tokens or job['output_tokens']
            job['output_tokens'] = min(job['output_tokens'] * 2, limit)
        delay = AUTO_RETRY_DELAYS[min(count, len(AUTO_RETRY_DELAYS)) - 1]
        job['auto_retry'] = {'count': count, 'wasted_usd': wasted, 'token': secrets.token_hex(8),
                             'retry_at': time.time() + delay, 'stopped': False}
        self._save()
        return delay

    def _auto_resume(self, sid, token, adapter_factory):
        """Resend unless the user acted meanwhile (resumed, paused or abandoned)."""
        with self._lock:
            job = self._data['jobs'].get(sid)
            if (not job or job['status'] != 'failed' or sid in self._running
                    or (job.get('auto_retry') or {}).get('token') != token):
                return
        try:
            self.resume(sid, adapter_factory, retry=True, _automatic=True)
        except LearningError as exc:
            try:
                with self._lock:
                    job = self._data['jobs'][sid]
                    job['error_code'], job['auto_retry']['token'] = exc.code, None
                    self._save()
            except (LearningError, OSError):
                pass  # The user resumes this one.
        except OSError:
            pass

    def _prepare_lessons(self, sid, configuration, adapter_factory, controls, journal, prior):
        """One grammar-lesson call per chapter after all chunks; False when paused."""
        from .chapter_pipeline import _controlled
        from .model_adapter import PRICING_VERSION
        for chapter_id in self._chapter_ids(self._data['jobs'][sid]):
            with self._lock:
                job = self._data['jobs'][sid]
                if chapter_id in job['lessons']:
                    continue
                if self._running[sid].is_set():
                    self._finish_status(sid, 'paused')
                    return False
                pairs = [(p, c) for p, c in zip(job['plans'], job['chunks']) if p['chapter_id'] == chapter_id]
                if not any(u['kind'] == 'paragraph' for p, _ in pairs for u in p['units']):
                    job['lessons'][chapter_id] = None  # Nothing to teach from.
                    self._save()
                    continue
                session = self.store.get_session(sid)
                language = session['language']
                items = {item['item_id']: item for item in effective_catalog(
                    load_catalog(language, version=session['catalog_version']),
                    session.get('vocabulary', []), job['chunks'])['items']}
                prior_topics = list(dict.fromkeys(topic for cid in self._chapter_ids(job)
                    for topic in ((job['lessons'].get(cid) or {}).get('topics') or [])))[-30:]
                budget, count = job['budget_usd'] - prior, self._max_calls(job)
                require(budget > 0, 'budget_exhausted')
                shared_cap = self._shared_cap(job, configuration)
                output_cap = min(self._with_reasoning(max(LESSON_OUTPUT_TOKENS, job.get('output_tokens', 6000)),
                                                      configuration), shared_cap)
                dependencies = {'chapter_id': chapter_id}
                if job.get('retry_revision', 0):
                    dependencies['explicit_retry'] = job['retry_revision']
            prompt, input_hash, grounding = build_lesson_request(
                chapter_id, language, session['level_id'], pairs, items, prior_topics)
            dependencies['lesson_input'] = input_hash

            def validate(result):
                # The lesson is supplementary: a bad answer is recorded, never blocks the book.
                try:
                    lesson = parse_lesson(result.text, chapter_id, language, grounding, input_hash,
                                          provider=configuration.resolve('translator')[1].provider_type,
                                          model=result.observed_model or configuration.resolve('translator')[0].model)
                except LearningError as exc:
                    lesson = unavailable_lesson(input_hash, str(exc))
                return {'lesson': lesson}

            controls.get_or_create_task(sid, count, budget, PRICING_VERSION, shared_cap)
            try:
                parsed, _replay = _controlled(sid, 'translator', LESSON_STAGE, prompt, configuration, output_cap,
                    controls, journal, budget, count, shared_cap, validate, dependencies, adapter_factory)
            except Exception as exc:
                if any(step['status'] in ('unknown', 'dispatched') for step in journal.job_steps(sid)):
                    raise LearningError('retry_confirmation_required') from exc
                raise
            with self._lock:
                self._data['jobs'][sid]['lessons'][chapter_id] = parsed['lesson']
                self._accepted(sid)
                self._save()
        return True

    def _finish_status(self, sid, status):
        session = self.store.get_session(sid)
        session['status'] = status
        self.store.update_session(session)
        self._data['jobs'][sid]['status'] = status
        self._save()

    def reader(self, session_id, chapter_index=0, *, gloss_on_click=False):
        require(type(chapter_index) is int and chapter_index >= 0, 'invalid_cursor')
        require(type(gloss_on_click) is bool, 'invalid_learning_request')
        with self._lock:
            session = self.store.get_session(check_id(session_id))
            require(session['status'] in ('ready', 'completed'), 'book_not_ready')
            source = self.store.get_source(session['book_id'])
            require(chapter_index < len(source['chapters']), 'invalid_cursor')
            prepared = self.store.get_prepared(session_id)
            chapter = source['chapters'][chapter_index]
            plans = self._data['jobs'][session_id]['plans']
            rendered = []
            for plan, chunk in zip(plans, prepared['chunks']):
                if plan['chapter_id'] == chapter['chapter_id']:
                    rendered.append(render_chunk(plan['units'], chunk, 'click' if gloss_on_click else 'context'))
            recap = next(r for r in prepared['recaps'] if r['chapter_id'] == chapter['chapter_id'])
            chunks_by_id = {c['plan_id']: c for c in prepared['chunks']}
            for entry in recap['grammar']:
                for example in entry['examples']:
                    edit = chunks_by_id[example['chunk_id']]['edits'][example['edit_index']]
                    example.update({'foreign': edit['replacement'], 'hebrew': edit['original']})
            items = {item['item_id']: {'lemma': item['lemma'], 'sense_he': item['sense_he']}
                     for item in effective_catalog(load_catalog(session['language'], version=session['catalog_version']),
                                                   session.get('vocabulary', []), prepared['chunks'])['items']}
            archive = self._archive_snapshot(self.store.get_learner(session['language']), chapter={
                'session_id': session_id, 'book_id': session['book_id'], 'chapter_id': chapter['chapter_id'],
                'chapter_title': chapter['title'], 'recap': recap, 'items': items})
            return {'session': session, 'title': self._title(source), 'chapter_title': chapter['title'],
                    'chapter_index': chapter_index, 'chapter_count': len(source['chapters']),
                    'language': session['language'], 'html': ''.join(rendered), 'recap': recap,
                    'items': items, 'archive_warning': archive['warning']}

    def cursor(self, session_id, chapter_index):
        self.reader(session_id, chapter_index)  # Validate against this immutable source.
        with self._lock:
            previous = self.store.get_session(session_id)['read_cursor'] or {}
            furthest = max(previous.get('furthest_chapter_index', previous.get('chapter_index', 0)), chapter_index)
            self.store.save_cursor(session_id, {'chapter_index': chapter_index, 'furthest_chapter_index': furthest})
            language = self.store.get_session(session_id)['language']
            archive = self._archive_snapshot(self.store.get_learner(language))
        return {'saved': True, 'archive_warning': archive['warning']}

    def export_book(self, session_id, *, format='epub', include_meanings=True, preserve_layout=True):
        """Download the complete frozen learning edition without reading/progress effects."""
        from .learning_export import export_learning_book
        require(format in ('epub', 'html'), 'invalid_export_format')
        require(type(include_meanings) is bool, 'invalid_export_options')
        require(type(preserve_layout) is bool, 'invalid_export_options')
        with self._lock:
            session = self.store.get_session(check_id(session_id))
            require(session['status'] in ('ready', 'completed'), 'book_not_ready')
            require(session_id in self._data['jobs'], 'session_not_found')
            source = self.store.get_source(session['book_id'])
            prepared = self.store.get_prepared(session_id)
            catalog = effective_catalog(load_catalog(session['language'], version=session['catalog_version']),
                                        session.get('vocabulary', []), prepared['chunks'])
            plans = deepcopy(self._data['jobs'][session_id]['plans'])
            require(len(plans) == len(prepared['chunks']), 'invalid_export_coverage')
            # Stored plans describe source coverage; accepted chunks pin runtime
            # replan identities. Build a read-only export view of those identities.
            for plan, chunk in zip(plans, prepared['chunks']):
                plan['plan_id'] = chunk['plan_id']
            from .learning_assets import load_epub
            raw = load_epub(self.root, source) if format == 'epub' and preserve_layout else None
            if format == 'epub' and preserve_layout and self._data['books'][source['book_id']].get('epub_layout') == 'retained':
                require(raw is not None, 'invalid_preserved_epub')
            if raw is not None:
                from .learning_epub_preserve import build_preserved_epub
                body = build_preserved_epub(raw, source, plans, prepared, session, catalog,
                                            include_meanings=include_meanings)
                warnings = []
            else:
                body = export_learning_book(source, plans, prepared, session, catalog, format=format,
                                            include_meanings=include_meanings)
                warnings = ['reflowed_text']
            return {'body': body, 'filename': 'learning-' + session_id + '.' + session['language'] + '.' + format,
                    'media_type': 'application/epub+zip' if format == 'epub' else 'text/html; charset=utf-8',
                    'warnings': warnings}

    def complete(self, session_id, expected_prepared_hash, completion_id):
        with self._lock:
            receipt = self.store.complete_book(check_id(session_id), expected_prepared_hash, check_id(completion_id))
            if session_id in self._data['jobs']:
                self._data['jobs'][session_id]['status'] = 'completed'
                self._save()
            self._archive_snapshot(self.store.get_learner(self.store.get_session(session_id)['language']))
            return receipt
