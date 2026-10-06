"""Read-only installation check; never creates a service or contacts providers."""
from pathlib import Path


def verify_learning_assets():
    from .learning_catalog import load_catalog
    from .learning_generation import _load_instructions
    from .learning_contracts import SUPPORTED_LANGUAGE_CODES
    package = Path(__file__).resolve().parent
    for name in ('learning.html', 'learning.js', 'learning.css', 'learning_help.html'):
        if not (package / name).is_file():
            raise FileNotFoundError('Missing learning asset: ' + name)
    for language in SUPPORTED_LANGUAGE_CODES:
        catalog = load_catalog(language)
        if len(catalog['frequency_seed']) < 500:
            raise ValueError('Incomplete learning vocabulary: ' + language)
    for policy in ('learning-policy@1', 'learning-policy@2', 'learning-policy@3'):
        if not _load_instructions({'policy_version': policy}):
            raise ValueError('Missing learning generation instructions')
