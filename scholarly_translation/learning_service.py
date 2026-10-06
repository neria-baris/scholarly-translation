"""Isolated learning orchestration; the translation worker is never invoked."""
from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import secrets
import threading

from .learning_contracts import LearningError, POLICY_VERSION, SUPPORTED_LANGUAGE_CODES, check_id, require, validate_source, word_count
from .learning_catalog import load_catalog
from .learning_vocabulary import effective_catalog
from .learning_controls import validate_options, surrounding_context
from .learning_archive import save_personal_archive
from .learning_import import import_hebrew_epub, import_translation_job
from .learning_planner import plan_book, replan_chunk
from .learning_generation import build_request, parse_response, build_chapter_recap
from .learning_render import render_chunk
from .learning_store import LearningStore


class LearningService:
    @staticmethod
    def _dense_output_cap(plan, configuration):
        selection, _ = configuration.resolve('translator')
        words = sum(word_count(unit['text']) for unit in plan['units'] if unit['kind'] == 'paragraph')
        # Each accepted occurrence has a structured offset/ID envelope. A growing
        # known vocabulary can replace most words, unlike the sparse first chapter.
        return min(selection.capabilities.max_output_tokens or 6000,
                   max(6000, min(64000, 2048 + words * 128)))

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
        temporary = self._path.with_suffix('.tmp')
        with temporary.open('w', encoding='utf-8') as stream:
            json.dump(self._data, stream, ensure_ascii=False, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, self._path)

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
                            'warnings': original.get('warnings', [])})
            progress = self._progress(learner, sessions)
            archive = self._archive_snapshot(learner, progress=progress)
            return {'books': deepcopy(list(self._data['books'].values())), 'sessions': sessions,
                    'learner': learner, 'jobs': jobs, 'progress': progress, 'personal_archive': archive,
                    'selected_language': language,
                    'languages': [{'id': code, 'available': True} for code in SUPPORTED_LANGUAGE_CODES],
                    'levels': load_catalog(language)['levels'], 'model': 'gpt-6-luna'}

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
        def rows(counts, book_ids):
            result = []
            for item_id, count in counts.items():
                item = items.get(item_id, {})
                result.append({'item_id': item_id, 'kind': item.get('kind', 'unknown'),
                    'foreign': item.get('lemma', item_id), 'hebrew': item.get('sense_he', ''),
                    'encounters': count, 'last_book_title': self._data['books'].get(book_ids[item_id], {}).get('title', '')})
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
                active = {'book_id': session['book_id'], 'title': source['title'],
                    'chapter_index': chapter_index, 'chapter_count': len(source['chapters']),
                    'read_items': rows(counts, {item_id: session['book_id'] for item_id in counts}),
                    'prepared_chunks': len(job.get('chunks', [])), 'total_chunks': len(job.get('plans', []))}
        return {'initial_word_goal': 500,
            'catalog_word_count': sum(item['kind'] == 'word' and
                item['min_level'] <= max(int(level['level_id']) for level in catalog['levels']) for item in catalog['items']),
            'completed_word_count': sum(row['kind'] == 'word' for row in completed),
            'completed_structure_count': sum(row['kind'] != 'word' for row in completed),
            'completed_items': completed, 'active_book': active}

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
              context_chars=4000, output_tokens=6000):
        validate_options(budget_usd, context_chars, output_tokens)
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
                'retry_revision': 0, 'warnings': []}
            self._save()
        self.resume(sid, adapter_factory, background=background)
        return self.store.get_session(sid)

    def resume(self, session_id, adapter_factory, *, background=True, budget_usd=None,
               context_chars=None, output_tokens=None, retry=False):
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
            validate_options(*options)
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
            session['status'] = 'preparing'
            self.store.update_session(session)
            self._running[sid] = threading.Event()
            self._save()
        if background:
            threading.Thread(target=self._run, args=(sid, configuration, adapter_factory), daemon=True).start()
        else:
            self._run(sid, configuration, adapter_factory)
        return self.store.get_session(sid)

    def pause(self, session_id):
        sid = check_id(session_id)
        with self._lock:
            require(sid in self._data['jobs'], 'session_not_found')
            if sid in self._running:
                self._running[sid].set()
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
                        budget, count = job['budget_usd'] - prior, len(job['plans'])
                        require(budget > 0, 'budget_exhausted')
                        context, job['context_info'] = surrounding_context(job['plans'], index, job.get('context_chars', 0))
                        self._save()
                    prompt, input_hash = build_request(plan, catalog, context)

                    def validate(result):
                        chunk, recap = parse_response(result.text, plan, catalog, input_hash,
                            provider='openai', model=result.observed_model or 'gpt-6-luna')
                        return {'chunk': chunk, 'recap': recap}

                    stage = {'learning-policy@1': 'learning-generate-v1',
                             'learning-policy@2': 'learning-generate-v2'}.get(plan['policy_version'], 'learning-generate-v3')
                    model_limit = configuration.resolve('translator')[0].capabilities.max_output_tokens or 6000
                    require(job.get('output_tokens', 6000) <= model_limit, 'output_capacity')
                    if plan['policy_version'] == 'learning-policy@1':
                        output_cap = shared_cap = job.get('output_tokens', 6000)
                    else:
                        shared_cap = max(job.get('output_tokens', 6000), max(self._dense_output_cap(p, configuration) for p in job['plans']))
                        output_cap = max(job.get('output_tokens', 6000), self._dense_output_cap(plan, configuration) if plan['review_item_ids'] else 0)
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
                        self._save()
                with self._lock:
                    job = self._data['jobs'][sid]
                    chapter_ids = list(dict.fromkeys(p['chapter_id'] for p in job['plans']))
                    recaps = []
                    for chapter_id in chapter_ids:
                        indices = [i for i,p in enumerate(job['plans']) if p['chapter_id'] == chapter_id]
                        recaps.append(build_chapter_recap(chapter_id, [job['chunks'][i] for i in indices],
                                                         [job['proposals'][i] for i in indices]))
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
                    self._finish_status(sid, 'failed')
        finally:
            with self._lock:
                self._running.pop(sid, None)

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
            return {'session': session, 'title': source['title'], 'chapter_title': chapter['title'],
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
