"""Serve the real web UI from this checkout against a throwaway data folder, for design checks.

Isolated: SCHOLARLY_DATA_ROOT points at the given folder, keys stay in memory (no Windows
Credential Manager), no browser is opened and no update check runs. Auto mode costs nothing.

    python scripts/design/serve_ui_sandbox.py --data outputs/ux/ui-redesign/data --port 8840
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True, help="throwaway data folder (created if missing)")
    parser.add_argument("--port", type=int, default=8840)
    parser.add_argument("--token", default="sandbox-token")
    args = parser.parse_args()
    data = Path(args.data).resolve()
    data.mkdir(parents=True, exist_ok=True)
    os.environ["SCHOLARLY_DATA_ROOT"] = str(data)  # must be set before the UI module computes its paths
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from http.server import ThreadingHTTPServer
    from scholarly_translation.ui import web_ui

    server = ThreadingHTTPServer(("127.0.0.1", args.port), web_ui.make_handler(args.token, None, key_store=None))
    print(f"Sandbox UI: http://127.0.0.1:{args.port}/  (data: {data})", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
