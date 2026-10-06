"""User-adjustable learning preparation limits and explicit context accounting."""
import math

from .learning_contracts import require


def validate_options(budget, context_chars, output_tokens):
    require(type(budget) in (int, float) and math.isfinite(budget) and budget > 0, 'invalid_budget')
    require(type(context_chars) is int and 0 <= context_chars <= 2000000, 'invalid_context')
    require(type(output_tokens) is int and output_tokens >= 1, 'invalid_output_limit')


def surrounding_context(plans, index, requested):
    before = '\n'.join(unit['text'] for plan in plans[:index] for unit in plan['units'])
    after = '\n'.join(unit['text'] for plan in plans[index + 1:] for unit in plan['units'])
    available = len(before) + len(after)
    left = min(len(before), requested // 2)
    right = min(len(after), requested - left)
    left = min(len(before), requested - right)
    before = before[-left:] if left else ''
    after = after[:right]
    # Context boundaries are explicit excerpts; source chunks remain complete.
    text = ('PREVIOUS PASSAGE:\n' + before if before else '')
    if after:
        text += ('\n\n' if text else '') + 'FOLLOWING PASSAGE:\n' + after
    return text, {'requested_chars': requested, 'provided_chars': left + right,
                  'available_chars': available, 'limited': left + right < available}
