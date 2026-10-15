"""Sign manifest.json with the owner's offline Ed25519 key, or create a key.

    python scripts/release/sign_manifest.py MANIFEST --key PRIVATE_KEY_FILE
    python scripts/release/sign_manifest.py --generate-key OUT_PATH

The private key (base64 of the 32-byte seed) must live outside this repository
and is never printed. --generate-key refuses any path inside the repo, writes
OUT_PATH (private) and OUT_PATH.pub, and prints the public-key constant to
paste into scholarly_translation/update/manifest.py (PUBLIC_KEY_B64).
"""

from __future__ import annotations

import argparse
import base64
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


class SigningError(Exception):
    pass


def _inside_repo(path: Path, repo_root: Path) -> bool:
    return Path(os.path.abspath(path)).resolve().is_relative_to(Path(repo_root).resolve())


def generate_key(out: Path, repo_root: Path = REPO_ROOT) -> str:
    """Write a new keypair outside the repo; return the public key (base64)."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    out = Path(out)
    if _inside_repo(out, repo_root):
        raise SigningError("refusing to write a private key inside the repository")
    if out.exists() or Path(str(out) + ".pub").exists():
        raise SigningError(f"refusing to overwrite an existing key: {out}")
    key = Ed25519PrivateKey.generate()
    seed = key.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
                             serialization.NoEncryption())
    public = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    public_b64 = base64.b64encode(public).decode("ascii")
    out.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="ascii") as handle:
        handle.write(base64.b64encode(seed).decode("ascii") + "\n")
    Path(str(out) + ".pub").write_text(public_b64 + "\n", encoding="ascii")
    return public_b64


def sign_file(manifest: Path, key_path: Path, repo_root: Path = REPO_ROOT) -> Path:
    """Write ``<manifest>.sig`` (base64 Ed25519 signature of the exact bytes)."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    if _inside_repo(Path(key_path), repo_root):
        raise SigningError("the private key must be stored outside the repository")
    try:
        seed = base64.b64decode(Path(key_path).read_text(encoding="ascii").strip(), validate=True)
        key = Ed25519PrivateKey.from_private_bytes(seed)
    except (OSError, ValueError) as exc:
        raise SigningError(f"cannot read the private key: {exc}") from exc
    manifest = Path(manifest)
    signature = key.sign(manifest.read_bytes())
    sig_path = manifest.with_name(manifest.name + ".sig")
    sig_path.write_text(base64.b64encode(signature).decode("ascii") + "\n", encoding="ascii")
    return sig_path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("manifest", nargs="?", help="path to manifest.json")
    parser.add_argument("--key", help="path to the private key file (outside the repo)")
    parser.add_argument("--generate-key", metavar="OUT", help="create a new keypair at OUT (+ OUT.pub)")
    args = parser.parse_args(argv)
    try:
        if args.generate_key:
            public_b64 = generate_key(Path(args.generate_key))
            print(f"Private key written to {args.generate_key} (keep it offline; never commit it).")
            print("Paste this into scholarly_translation/update/manifest.py:")
            print(f'PUBLIC_KEY_B64 = "{public_b64}"')
            return 0
        if not args.manifest or not args.key:
            parser.error("MANIFEST and --key are required (or use --generate-key OUT)")
        print(f"Wrote {sign_file(Path(args.manifest), Path(args.key))}")
        return 0
    except SigningError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
