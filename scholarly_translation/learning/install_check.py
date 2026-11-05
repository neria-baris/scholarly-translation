"""Read-only installation check; never creates a service or contacts providers."""
from pathlib import Path


def verify_learning_assets():
    from .catalog import WORDLIST_DIR, load_catalog
    from .generation import _load_instructions
    from .contracts import SUPPORTED_LANGUAGE_CODES
    ui_dir = Path(__file__).resolve().parents[1] / 'ui'
    for name in ('learning.html', 'learning.js', 'learning.css', 'learning_help.html'):
        if not (ui_dir / name).is_file():
            raise FileNotFoundError('Missing learning asset: ' + name)
    for language in SUPPORTED_LANGUAGE_CODES:
        catalog = load_catalog(language)
        minimum = 50 if language == 'ar' else 500
        if len(catalog['frequency_seed']) < minimum:
            raise ValueError('Incomplete learning vocabulary: ' + language)
        wordlist = 'ar_starter.md' if language == 'ar' else language + '_500.md'
        if not (WORDLIST_DIR / wordlist).is_file():
            raise FileNotFoundError('Missing learning wordlist: ' + language)
    for policy in ('learning-policy@1', 'learning-policy@2', 'learning-policy@3'):
        if not _load_instructions({'policy_version': policy}):
            raise ValueError('Missing learning generation instructions')
