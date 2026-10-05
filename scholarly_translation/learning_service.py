"""Isolated learning orchestration; the translation worker is never invoked."""
from __future__ import annotations

from copy import deepcopy
import json
import math
import os
from pathlib import Path
import secrets
import threading

from .learning_contracts import LearningError, POLICY_VERSION, check_id, require, validate_source
from .learning_catalog import load_catalog
from .learning_import import import_hebrew_epub, import_translation_job
from .learning_planner import plan_book, replan_chunk
from .learning_generation import build_request, parse_response, build_chapter_recap
from .learning_render import render_chunk
from .learning_store import LearningStore


class LearningService:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.store = LearningStore(self.root / 'state')
        self._lock = threading.RLock()
        self._running = {}
        self._path = self.root / 'service.json'
        self._data = json.loads(self._path.read_text(encoding='utf-8')) if self._path.exists() else {'version': 1, 'books': {}, 'jobs': {}}
        require(self._data.get('version') == 1, 'unsupported_schema')
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
                    'plans': plan_book(source, learner, load_catalog(session['language'])),
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

    def _add_source(self, source):
        validate_source(source)
        with self._lock:
            self.store.save_source(source)
            self._data['books'][source['book_id']] = {'book_id': source['book_id'], 'title': source['title'], 'origin': source['origin']['kind']}
            self._save()
        return deepcopy(self._data['books'][source['book_id']])

    def import_epub(self, content, title=None):
        return self._add_source(import_hebrew_epub(content, book_id='book-' + secrets.token_hex(12), title=title))

    def import_translation(self, snapshot):
        return self._add_source(import_translation_job(snapshot, book_id='book-' + secrets.token_hex(12)))

    def summary(self):
        with self._lock:
            sessions = self.store.list_sessions()
            jobs = {sid: {'accepted_chunks': len(j['chunks']), 'total_chunks': len(j['plans']),
                          'error_code': j.get('error_code'), 'status': j['status'], 'budget_usd': j['budget_usd'],
                          'usage': self._usage(sid)}
                    for sid, j in self._data['jobs'].items()}
            return {'books': deepcopy(list(self._data['books'].values())), 'sessions': sessions,
                    'learner': self.store.get_learner('fr'), 'jobs': jobs,
                    'languages': [{'id': code, 'available': code == 'fr'} for code in ('fr', 'de', 'es', 'yi', 'it')],
                    'levels': load_catalog('fr')['levels'], 'model': 'gpt-6-luna'}

    def _usage(self, sid):
        from .runtime_controls import ControlStore, RuntimeControlsError
        path = self.root / 'calls' / sid / 'controls.sqlite3'
        if not path.exists():
            return None
        try:
            with ControlStore(path, create=False) as controls:
                status = controls.status(sid)
            return {key: status[key] for key in ('attempted_calls', 'list_estimated_spent_usd', 'held_usd', 'stopped')}
        except RuntimeControlsError:
            return None

    def set_effort(self, level_id):
        with self._lock:
            learner = self.store.get_learner('fr')
            require(learner['active_book_id'] is None, 'active_book_conflict')
            level = next((x for x in load_catalog('fr')['levels'] if x['level_id'] == level_id), None)
            require(level is not None, 'unavailable_level')
            learner['level_id'], learner['support_mode'] = level_id, level['support_mode']
            # Version prevents stale plans from surviving an effort change.
            learner['revision'] += 1
            self.store.save_learner(learner)
            return learner

    def start(self, book_id, budget_usd, configuration, adapter_factory, *, background=True):
        require(isinstance(budget_usd, (int, float)) and not isinstance(budget_usd, bool)
                and math.isfinite(budget_usd) and 0 < budget_usd <= 100, 'invalid_budget')
        with self._lock:
            source = self.store.get_source(check_id(book_id))
            learner, catalog = self.store.get_learner('fr'), load_catalog('fr')
            plans = plan_book(source, learner, catalog, policy_version=POLICY_VERSION)
            session = self.store.create_session(source, learner)
            sid = session['session_id']
            self._data['jobs'][sid] = {'session_id': sid, 'status': 'paused', 'budget_usd': budget_usd,
                'configuration': configuration.to_dict(), 'plans': plans, 'current_plan': None,
                'chunks': [], 'proposals': [], 'projected': learner, 'error_code': None}
            self._save()
        self.resume(sid, adapter_factory, background=background)
        return self.store.get_session(sid)

    def resume(self, session_id, adapter_factory, *, background=True, budget_usd=None):
        from .model_config import ModelConfiguration
        sid = check_id(session_id)
        with self._lock:
            require(sid in self._data['jobs'], 'session_not_found')
            require(sid not in self._running, 'already_running')
            session = self.store.get_session(sid)
            require(session['status'] in ('imported', 'preparing', 'paused', 'failed'), 'invalid_status')
            require(self.store.get_learner(session['language'])['revision'] == session['base_learner_revision'], 'stale_learner')
            job = self._data['jobs'][sid]
            if job['budget_usd'] is None:
                require(type(budget_usd) in (int, float) and math.isfinite(budget_usd) and 0 < budget_usd <= 100, 'invalid_budget')
                job['budget_usd'] = budget_usd
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
            with ControlStore(directory / 'controls.sqlite3') as controls, WorkJournal(directory / 'journal.sqlite3') as journal:
                journal.resume(sid)
                while True:
                    with self._lock:
                        job = self._data['jobs'][sid]
                        if self._running[sid].is_set():
                            self._finish_status(sid, 'paused')
                            return
                        index = len(job['chunks'])
                        if index == len(job['plans']):
                            break
                        catalog = load_catalog('fr')
                        if job['current_plan'] is None:
                            job['current_plan'] = replan_chunk(job['plans'][index], job['projected'], catalog)
                            self._save()  # Dispatch identity must survive a crash.
                        plan = deepcopy(job['current_plan'])
                        budget, count = job['budget_usd'], len(job['plans'])
                    prompt, input_hash = build_request(plan, catalog)

                    def validate(result):
                        chunk, recap = parse_response(result.text, plan, catalog, input_hash,
                            provider='openai', model=result.observed_model or 'gpt-6-luna')
                        return {'chunk': chunk, 'recap': recap}

                    parsed, _replay = _controlled(sid, 'translator', 'learning-generate-v1', prompt,
                        configuration, 6000, controls, journal, budget, count, 6000, validate,
                        {'plan': plan, 'catalog_version': catalog['version']}, adapter_factory)
                    with self._lock:
                        job = self._data['jobs'][sid]
                        job['chunks'].append(parsed['chunk'])
                        job['proposals'].append({'chunk_id': parsed['chunk']['plan_id'], 'recap': parsed['recap']})
                        # Exposure projects choices within this book, without mastery or durable advancement.
                        for item_id in parsed['chunk']['coverage_item_ids']:
                            existing = next((x for x in job['projected']['items'] if x['item_id'] == item_id), None)
                            if existing:
                                existing['introduced_count'] += 1
                            else:
                                job['projected']['items'].append({'item_id': item_id, 'introduced_count': 1,
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
                self._data['jobs'][sid]['error_code'] = exc.code if isinstance(exc, LearningError) else 'preparation_stopped'
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

    def reader(self, session_id, chapter_index=0):
        require(type(chapter_index) is int and chapter_index >= 0, 'invalid_cursor')
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
                    rendered.append(render_chunk(plan['units'], chunk, session['support_mode']))
            recap = next(r for r in prepared['recaps'] if r['chapter_id'] == chapter['chapter_id'])
            return {'session': session, 'title': source['title'], 'chapter_title': chapter['title'],
                    'chapter_index': chapter_index, 'chapter_count': len(source['chapters']),
                    'html': ''.join(rendered), 'recap': recap,
                    'items': {item['item_id']: {'lemma': item['lemma'], 'sense_he': item['sense_he']}
                              for item in load_catalog(session['language'])['items']}}

    def cursor(self, session_id, chapter_index):
        self.reader(session_id, chapter_index)  # Validate against this immutable source.
        self.store.save_cursor(session_id, {'chapter_index': chapter_index})
        return {'saved': True}

    def complete(self, session_id, expected_prepared_hash, completion_id):
        with self._lock:
            receipt = self.store.complete_book(check_id(session_id), expected_prepared_hash, check_id(completion_id))
            if session_id in self._data['jobs']:
                self._data['jobs'][session_id]['status'] = 'completed'
                self._save()
            return receipt
