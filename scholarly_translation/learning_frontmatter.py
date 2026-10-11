"""Local pass-through for a pinned prefix; original source remains intact."""
from .learning_contracts import fingerprint, require, validate_generated


def validate_skip(source, count):
    require(type(count) is int and 0 <= count < len(source['chapters']),
            'invalid_learning_request', 'invalid initial chapter count')
    return count


def passthrough(plan, language):
    require(plan.get('learning_excluded') is True, 'invalid_plan')
    chunk = {'schema_version': 1, 'plan_id': plan['plan_id'], 'response_version': 1,
             'provider': 'local', 'model': 'none', 'prompt_version': 'frontmatter@1',
             'input_hash': fingerprint(plan), 'edits': [], 'warnings': [],
             'coverage_item_ids': [], 'language': language}
    chunk['content_hash'] = fingerprint({key: chunk[key] for key in
        ('plan_id', 'input_hash', 'edits', 'coverage_item_ids')})
    recap = {'schema_version': 1, 'chapter_id': plan['chapter_id'],
             'chunk_hashes': [chunk['content_hash']], 'vocabulary': [], 'grammar': [], 'warnings': []}
    return validate_generated(chunk), recap
