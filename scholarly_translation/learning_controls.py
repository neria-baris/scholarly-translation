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


DEFAULT_LEARNING_MODEL = 'gpt-6-luna'


def learning_model_options():
    """Catalogue models for learning preparation, cheapest output first, with
    their reasoning levels (first is the model's default; none for models
    that take no effort setting)."""
    from .model_settings import catalogue
    entries = [{'provider': entry['provider'], 'model': entry['model'],
                'reasoning_values': entry['reasoning_values'], 'default_reasoning': entry['default_reasoning'],
                'rates_per_million': entry['rates_per_million']}
               for entry in catalogue() if entry['provider'] in ('openai', 'anthropic')]
    return sorted(entries, key=lambda entry: (entry['rates_per_million']['output'], entry['model']))


def learning_model_selection(model=None, reasoning=None):
    """Validated translator-role selection for a learning preparation."""
    model = DEFAULT_LEARNING_MODEL if model in (None, '') else model
    options = {entry['model']: entry for entry in learning_model_options()}
    require(model in options, 'invalid_model')
    selection = {'source': 'catalog', 'provider': options[model]['provider'], 'model': model}
    if reasoning not in (None, ''):
        require(reasoning in options[model]['reasoning_values'], 'invalid_model')
        selection['reasoning'] = reasoning
    return selection


AUTO_CONTEXT_MIN_CHARS, AUTO_CONTEXT_MAX_CHARS = 1500, 6000


def auto_context_chars(plan):
    """Surrounding text for one passage, sized like the passage itself: enough
    for local continuity without paying for long context on every call."""
    size = sum(len(unit['text']) for unit in plan['units'])
    return max(AUTO_CONTEXT_MIN_CHARS, min(AUTO_CONTEXT_MAX_CHARS, size))
