# Gate 1 offline skeleton

Standard library only, Python 3.9+. No network calls, no dependency installation.

Current records use schema 2: document/page/region/segment IDs, source URI/language,
processing stage/version, input-file SHA-256, status and warnings. Schema 1 remains
readable with an explicit legacy warning when an input hash was never recorded.
The demo is synthetic software evidence; it establishes no PDF/OCR or translation quality.

## Run the demo

```
python -B -m scholarly_translation demo --output outputs/gate1
```

Writes `outputs/gate1/source.txt` (synthetic multilingual text), `outputs/gate1/document.json`
(persisted document/page/segment records), and appends a mock-provider usage event to
`outputs/gate1/usage.jsonl`. Rerunning demo reuses the same deterministic IDs and appends
another usage record.

## Inspect a document

```
python -B -m scholarly_translation inspect outputs/gate1/document.json
```

Prints schema/document version, source locator, and page/segment IDs, offsets and text.
Exits nonzero if the file is missing or invalid.

## Run tests

```
python -B -m unittest discover -s tests -v
```

## Provider configuration

See `config.example.json`. Only the `mock` provider (model `mock-echo-1`) is supported in
this gate; any other provider or model name is rejected before any call. Mock output is
always prefixed with `[MOCK-PLACEHOLDER]` and is never a real translation. No secrets are
used or logged.

Pass `--config path/to/config.json` to `demo` to override the target language (or explicitly
select mock/`mock-echo-1`):

```
python -B -m scholarly_translation demo --output outputs/gate1 --config config.example.json
```

The config is loaded and strictly validated (object shape, known fields only, correct field
types) before anything is written or any provider is invoked. Unknown fields (including
credential-like ones) are rejected by name only — their values are never printed or logged.
Omitting `--config` uses the built-in mock defaults.
