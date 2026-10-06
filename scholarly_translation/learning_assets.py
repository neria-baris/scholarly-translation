"""Durable immutable EPUB templates, separate from learning text/state."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import uuid

from .learning_contracts import LearningError, check_id, require


def retain_epub(root, source, raw, *, kind='original'):
    require(isinstance(raw, (bytes, bytearray)) and bool(raw), 'invalid_preserved_epub')
    raw = bytes(raw)
    require(kind in ('original', 'translation_template'), 'invalid_preserved_epub')
    metadata = {'version': 1, 'book_id': source['book_id'], 'source_hash': source['source_hash'],
                'sha256': hashlib.sha256(raw).hexdigest(), 'kind': kind}
    parent = Path(root) / 'epub_assets'
    parent.mkdir(parents=True, exist_ok=True)
    target = parent / check_id(source['book_id'])
    if target.exists():
        require(load_epub(root, source) == raw, 'invalid_preserved_epub')
        return
    staging = parent / ('.pending-' + uuid.uuid4().hex)
    staging.mkdir()
    # Publish both files in one directory rename; a crash cannot publish half
    # a template. Unpublished staging directories are never used for exports.
    for name, content in (('original.epub', raw),
                          ('metadata.json', json.dumps(metadata, sort_keys=True).encode('utf-8'))):
        with (staging / name).open('xb') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
    os.rename(staging, target)


def load_epub(root, source):
    target = Path(root) / 'epub_assets' / check_id(source['book_id'])
    if not target.exists():
        return None
    try:
        metadata = json.loads((target / 'metadata.json').read_text(encoding='utf-8'))
        raw = (target / 'original.epub').read_bytes()
        require(metadata.get('version') == 1 and metadata.get('book_id') == source['book_id']
                and metadata.get('source_hash') == source['source_hash']
                and metadata.get('kind') in ('original', 'translation_template')
                and metadata.get('sha256') == hashlib.sha256(raw).hexdigest(), 'invalid_preserved_epub')
        return raw
    except (OSError, ValueError, TypeError, AttributeError) as error:
        raise LearningError('invalid_preserved_epub') from error
