"""Prepare a release of the runtime files for the public distribution repo.

Dry run by default: prints what would happen. With --execute it exports the
runtime allow-list from the committed tree (HEAD of this repo, which must be
clean for those paths) into a local checkout of the distribution repo, writes
manifest.json and ScholarlyTranslation-Setup.zip into an output folder next to
that checkout, and prints the git / signing / gh commands for the owner. It
never commits, pushes or publishes anything itself.

    python scripts/release/build_release.py --version 1.0.1 --dist-checkout ../scholarly-translation-app
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scholarly_translation.update import manifest as mf  # noqa: E402

SETUP_ZIP_NAME = "ScholarlyTranslation-Setup.zip"
ZIP_TIMESTAMP = (2026, 1, 1, 0, 0, 0)


class ReleaseError(Exception):
    pass


def is_runtime_path(path: str) -> bool:
    """The runtime allow-list. Anything else (audit/, docs/, tests/, outputs/,
    .claude/, scripts/, prompts/, root LICENSE files, ...) is never published."""
    path = path.replace("\\", "/")
    parts = path.split("/")
    if len(parts) == 1:
        return path in mf.RUNTIME_ROOT_FILES
    if parts[0] != mf.RUNTIME_PACKAGE_DIR:
        return False
    return "__pycache__" not in parts and not path.endswith((".pyc", ".pyo"))


def _git(args: list, repo: Path, *, text: bool = True):
    result = subprocess.run(["git", *args], cwd=repo, capture_output=True, check=False)
    if result.returncode != 0:
        raise ReleaseError(f"git {' '.join(args[:2])} failed: {result.stderr.decode('utf-8', 'replace').strip()}")
    return result.stdout.decode("utf-8") if text else result.stdout


def list_runtime_files(repo: Path, ref: str = "HEAD") -> list:
    names = _git(["ls-tree", "-r", "-z", "--name-only", ref], repo).split("\0")
    return sorted(n for n in names if n and is_runtime_path(n))


def assert_clean(repo: Path) -> None:
    """Fail when allow-listed paths are modified, staged or untracked."""
    out = _git(["status", "--porcelain", "-z", "--untracked-files=all"], repo)
    dirty = []
    for entry in out.split("\0"):
        if len(entry) > 3:
            name = entry[3:]
            if is_runtime_path(name) or name == mf.RUNTIME_PACKAGE_DIR or name.startswith(mf.RUNTIME_PACKAGE_DIR + "/"):
                dirty.append(name)
    dirty = [n for n in dirty if is_runtime_path(n)]
    if dirty:
        raise ReleaseError("working tree is dirty for runtime paths: " + ", ".join(sorted(dirty)[:10]))


def read_blob(repo: Path, path: str, ref: str = "HEAD") -> bytes:
    return _git(["show", f"{ref}:{path}"], repo, text=False)


def build_manifest(version: str, blobs: dict, notes_he: str, notes_en: str, min_launcher: int) -> bytes:
    mf.parse_version(version)
    files = {p: {"sha256": hashlib.sha256(b).hexdigest(), "size": len(b)} for p, b in sorted(blobs.items())}
    doc = {
        "schema": mf.SCHEMA,
        "version": version,
        "tag": f"v{version}",
        "min_launcher": min_launcher,
        "requirements_sha256": hashlib.sha256(blobs["requirements.txt"]).hexdigest(),
        "files": files,
        "notes_he": notes_he,
        "notes_en": notes_en,
    }
    data = (json.dumps(doc, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
    mf.parse_manifest(data)  # validate with the same rules the client applies
    return data


def write_setup_zip(path: Path, blobs: dict, version: str) -> None:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        entries = dict(blobs)
        entries["release.json"] = (json.dumps({"version": version}) + "\n").encode("utf-8")
        for name in sorted(entries):
            info = zipfile.ZipInfo(name, ZIP_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, entries[name])


def export_to_checkout(dist: Path, blobs: dict) -> None:
    """Replace the runtime paths in the distribution checkout (leaves .git,
    site/ and anything else alone)."""
    shutil.rmtree(dist / mf.RUNTIME_PACKAGE_DIR, ignore_errors=True)
    for name in mf.RUNTIME_ROOT_FILES:
        (dist / name).unlink(missing_ok=True)
    for path, data in blobs.items():
        target = dist / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)


def owner_commands(version: str, dist: Path, out_dir: Path, dist_repo: str) -> list:
    tag = f"v{version}"
    return [
        f'cd "{dist}"',
        "git add -A",
        f'git commit -m "Release {tag}"',
        f"git tag {tag}",
        f"git push origin HEAD {tag}",
        f'python scripts/release/sign_manifest.py "{out_dir / "manifest.json"}" --key <PATH-TO-PRIVATE-KEY-OUTSIDE-REPO>',
        f'gh release create {tag} --repo {dist_repo} --title "{tag}" --notes-file <NOTES-FILE> '
        f'"{out_dir / SETUP_ZIP_NAME}" "{out_dir / "manifest.json"}" "{out_dir / "manifest.json.sig"}"',
    ]


def _inside(child: Path, parent: Path) -> bool:
    return child.resolve().is_relative_to(parent.resolve())


def run(args, repo: Path = REPO_ROOT, out=print) -> int:
    dist = Path(args.dist_checkout).resolve()
    out_dir = Path(args.out_dir).resolve() if args.out_dir else dist.parent / f"{dist.name}-release-{args.version}"
    if _inside(dist, repo) or _inside(repo, dist):
        raise ReleaseError("the distribution checkout must be a separate folder outside this repository")
    if _inside(out_dir, repo):
        raise ReleaseError("the output folder must be outside this repository")
    mf.parse_version(args.version)
    assert_clean(repo)
    names = list_runtime_files(repo)
    if "requirements.txt" not in names:
        raise ReleaseError("requirements.txt is not part of the committed runtime files")
    blobs = {n: read_blob(repo, n) for n in names}
    notes_he = Path(args.notes_he_file).read_text(encoding="utf-8") if args.notes_he_file else ""
    notes_en = Path(args.notes_en_file).read_text(encoding="utf-8") if args.notes_en_file else ""
    manifest_bytes = build_manifest(args.version, blobs, notes_he, notes_en, args.min_launcher)
    total = sum(len(b) for b in blobs.values())
    out(f"Release v{args.version}: {len(blobs)} runtime files, {total} bytes (from {_git(['rev-parse', '--short', 'HEAD'], repo).strip()})")
    if not args.execute:
        out("Dry run: nothing written. Add --execute to export.")
        out(f"  would export into  {dist}")
        out(f"  would write assets {out_dir}")
    else:
        if not (dist / ".git").exists():
            raise ReleaseError(f"{dist} is not a git checkout of the distribution repo")
        export_to_checkout(dist, blobs)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "manifest.json").write_bytes(manifest_bytes)
        (out_dir / "manifest.json.sig").unlink(missing_ok=True)
        write_setup_zip(out_dir / SETUP_ZIP_NAME, blobs, args.version)
        out(f"Exported to {dist}; assets in {out_dir}")
    out("Commands for the owner (nothing is pushed by this script):")
    for line in owner_commands(args.version, dist, out_dir, args.dist_repo):
        out("  " + line)
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version", required=True, help="release version, e.g. 1.0.1")
    parser.add_argument("--dist-checkout", required=True, help="local checkout of the distribution repo")
    parser.add_argument("--out-dir", help="where manifest.json and the Setup zip go (default: next to the checkout)")
    parser.add_argument("--dist-repo", default=mf.DIST_REPO, help="OWNER/NAME of the distribution repo (for gh)")
    parser.add_argument("--min-launcher", type=int, default=1)
    parser.add_argument("--notes-he-file")
    parser.add_argument("--notes-en-file")
    parser.add_argument("--execute", action="store_true", help="actually write files (default is a dry run)")
    try:
        return run(parser.parse_args(argv))
    except (ReleaseError, mf.ManifestError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
