"""Deterministic local token counting with explicitly labelled uncertainty.

Never presents an unverified heuristic (e.g. a word-count multiple) as an
exact or "guaranteed conservative" token count. tiktoken's published model
mapping (https://github.com/openai/tiktoken, checked 2026-10-05) has no
entry for GPT-6: any model this project cannot map to a real tokenizer falls
back to the ``o200k_base`` encoding and is labelled an estimate, never
``exact``. ``tiktoken`` is imported lazily so this module (and every caller)
loads even when the dependency, or its encoding-file cache, is unavailable;
no fallback path makes a network call.
"""
from __future__ import annotations

import base64
import hashlib
import math
import os
import tempfile
import types
from pathlib import Path

_ENCODING_CACHE = {}

# Models this project targets that tiktoken has never published a mapping
# for; forcing the fallback encoding instead of attempting (and silently
# mis-resolving against) ``encoding_for_model``.
_NO_TIKTOKEN_MAPPING = {"gpt-6-luna", "gpt-6.1-sol"}
_FALLBACK_ENCODING = "o200k_base"

# Planning bound for byte/subword text tokenizers, plus explicit margin.
# An arbitrary custom provider's tokenizer is not mathematically constrained
# by this assumption; its limits and resulting estimates remain provisional.
_DEFAULT_MARGIN = 1.15


class TokenCountingError(ValueError):
    """Invalid input to the counter; never includes the text itself."""


def byte_upper_bound(text, margin=_DEFAULT_MARGIN):
    """Deterministic, dependency-free upper bound on ``text``'s token count."""
    if not isinstance(text, str):
        raise TokenCountingError("text must be a string")
    if type(margin) not in (int, float) or not math.isfinite(margin) or margin < 1:
        raise TokenCountingError('planning margin must be finite and at least one')
    byte_length = len(text.encode("utf-8"))
    return int(byte_length * margin) + 1


def _load_encoding(name):
    if name not in {'o200k_base', 'o200k_harmony', 'cl100k_base'}:
        return None
    if name in _ENCODING_CACHE:
        return _ENCODING_CACHE[name]
    try:
        import tiktoken
        from tiktoken_ext.openai_public import ENCODING_CONSTRUCTORS
    except ImportError:
        return None
    try:
        constructor = ENCODING_CONSTRUCTORS.get(name)
        if constructor is None:
            return None
        # Copy the constructor globals: never patch the SDK's global loader,
        # change the process environment or invoke its network-capable cache.
        namespace = dict(constructor.__globals__)
        namespace['load_tiktoken_bpe'] = _read_local_bpe
        namespace['o200k_base'] = lambda: _encoding_arguments('o200k_base')
        offline = types.FunctionType(constructor.__code__, namespace,
                                     constructor.__name__, constructor.__defaults__, constructor.__closure__)
        encoding = tiktoken.Encoding(**offline())
        _ENCODING_CACHE[name] = encoding
        return encoding
    except Exception:
        return None


def _encoding_arguments(name):
    encoding = _load_encoding(name)
    if encoding is None:
        raise ValueError('local encoding unavailable')
    return dict(name=name, pat_str=encoding._pat_str,
                mergeable_ranks=encoding._mergeable_ranks, special_tokens=encoding._special_tokens)


def _read_local_bpe(url, expected_hash=None):
    if not expected_hash or not url.startswith('https://openaipublic.blob.core.windows.net/encodings/'):
        raise ValueError('unsupported local encoding')
    locations = [Path(__file__).resolve().parent.parent / 'cache' / 'tokenizers']
    for variable in ('TIKTOKEN_CACHE_DIR', 'DATA_GYM_CACHE_DIR'):
        if os.environ.get(variable):
            locations.append(Path(os.environ[variable]))
    locations.append(Path(tempfile.gettempdir()) / 'data-gym-cache')
    filename = hashlib.sha1(url.encode()).hexdigest()
    for directory in locations:
        try:
            data = (directory / filename).read_bytes()
        except OSError:
            continue
        if hashlib.sha256(data).hexdigest() != expected_hash:
            continue
        return {base64.b64decode(token, validate=True): int(rank)
                for token, rank in (line.split() for line in data.splitlines() if line)}
    raise ValueError('verified local encoding unavailable')


def _load_encoding_for_model(model):
    try:
        import tiktoken
    except ImportError:
        return None
    try:
        return _load_encoding(tiktoken.encoding_name_for_model(model))
    except Exception:
        return None


def count_tokens(text, model=None):
    """Count ``text``'s tokens for ``model``, or a deterministic estimate.

    Returns a dict:

    - ``count``: best available integer token count.
    - ``method``: ``"tiktoken_exact"`` (an official mapped encoding for
      ``model``), ``"tiktoken_estimate_<encoding>"`` (fallback encoding, an
      explicitly labelled estimate -- not exact model counting), or
      ``"byte_upper_bound_estimate"`` if no tiktoken encoding is loadable at
      all (dependency/cache unavailable).
    - ``exact``: ``True`` only for ``"tiktoken_exact"``.
    - ``upper_bound``: a safe ceiling for fit/reservation sizing. When exact,
      this equals ``count``; otherwise it is the deterministic
      ``byte_upper_bound``, never the (possibly optimistic) fallback-encoding
      count.
    """
    if not isinstance(text, str):
        raise TokenCountingError("text must be a string")

    encoding = None
    if model and model not in _NO_TIKTOKEN_MAPPING:
        encoding = _load_encoding_for_model(model)
    if encoding is not None:
        count = len(encoding.encode(text, disallowed_special=()))
        return {"count": count, "method": "tiktoken_exact", "exact": True, "upper_bound": count}

    bound = byte_upper_bound(text)
    encoding = _load_encoding(_FALLBACK_ENCODING)
    if encoding is None:
        return {"count": bound, "method": "byte_upper_bound_estimate", "exact": False, "upper_bound": bound}

    count = len(encoding.encode(text, disallowed_special=()))
    return {"count": count, "method": f"tiktoken_estimate_{_FALLBACK_ENCODING}",
            "exact": False, "upper_bound": bound}


def fits_within(text, limit_tokens, model=None):
    """``True`` iff ``text``'s conservative ``upper_bound`` fits ``limit_tokens``.

    Always uses ``upper_bound`` (never the possibly-optimistic ``count``), so
    a fit decision is never wrong in the unsafe direction.
    """
    if type(limit_tokens) is not int or limit_tokens < 0:
        raise TokenCountingError("limit_tokens must be a nonnegative integer")
    return count_tokens(text, model=model)["upper_bound"] <= limit_tokens
