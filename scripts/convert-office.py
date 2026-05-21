#!/usr/bin/env python3
"""Office → PDF converter for doc-index PWA.

Pre-converts .docx / .doc / .xlsx / .xls / .pptx / .ppt files to PDF so the
PWA can serve them through its existing PDF.js viewer instead of relying on
Microsoft Office Online (which can't fetch documents behind basic auth).

Usage:
    python3 convert-office.py <config.yaml>           # batch all Office files
    python3 convert-office.py <config.yaml> --file <path>
    python3 convert-office.py <config.yaml> --dry-run

Output layout (under serve.root):
    pdf-cache/
        index.json                      # path → {hash, mtime, size, sha256}
        <hash>.pdf                      # converted PDF, hash = sha256[:16]

Caching: a source file is re-converted only when its mtime or sha256 changes.

Requires: libreoffice (writer + impress + calc). Optional soft dependencies
python-pptx / python-docx for repairing files LibreOffice refuses to open.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    sys.stderr.write("PyYAML not installed. `pip3 install pyyaml`\n")
    sys.exit(1)

# Soft deps — only used to repair files LibreOffice can't read directly.
try:
    from pptx import Presentation as _Pptx
    HAVE_PPTX = True
except ImportError:
    HAVE_PPTX = False

try:
    from docx import Document as _Docx
    HAVE_DOCX = True
except ImportError:
    HAVE_DOCX = False


OFFICE_EXTS = {".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx"}
CACHE_DIRNAME = "pdf-cache"
INDEX_FILENAME = "index.json"
LIBREOFFICE_TIMEOUT_SEC = 120


# ── Config loading ──────────────────────────────────────────────────────────


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    cfg["repo"]["path"] = str(Path(cfg["repo"]["path"]).expanduser())
    cfg["serve"]["root"] = str(Path(cfg["serve"]["root"]).expanduser())
    return cfg


def should_ignore(name: str, patterns: list[str]) -> bool:
    """Match scan.py's ignore semantics: glob-style patterns."""
    from fnmatch import fnmatch
    for pat in patterns:
        if fnmatch(name, pat):
            return True
    return False


# ── File discovery ──────────────────────────────────────────────────────────


def iter_office_files(repo_root: Path, ignore_patterns: list[str]):
    """Walk repo_root, follow symlinks, yield Office files."""
    # Use os.walk with followlinks=True; pathlib.rglob doesn't expose that
    # flag.
    import os
    seen: set[Path] = set()
    for dirpath, dirnames, filenames in os.walk(repo_root, followlinks=True):
        dirnames[:] = [d for d in dirnames if not should_ignore(d, ignore_patterns)]
        for fname in filenames:
            if should_ignore(fname, ignore_patterns):
                continue
            p = Path(dirpath) / fname
            if p.suffix.lower() not in OFFICE_EXTS:
                continue
            # Resolve to canonical path to dedupe across symlinks
            try:
                canonical = p.resolve()
            except OSError:
                continue
            if canonical in seen:
                continue
            seen.add(canonical)
            yield p


# ── Hashing / cache key ─────────────────────────────────────────────────────


def file_sha256(path: Path, chunk: int = 65536) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            data = f.read(chunk)
            if not data:
                break
            h.update(data)
    return h.hexdigest()


def cache_key(src_sha256: str) -> str:
    """Short stable id derived from source content hash."""
    return src_sha256[:16]


# ── LibreOffice driver ──────────────────────────────────────────────────────


def libreoffice_bin() -> str | None:
    """Locate the libreoffice / soffice binary."""
    for name in ("libreoffice", "soffice"):
        bin_path = shutil.which(name)
        if bin_path:
            return bin_path
    return None


def convert_with_libreoffice(src: Path, out_dir: Path) -> Path | None:
    """Run libreoffice --headless --convert-to pdf. Return PDF path on success."""
    bin_path = libreoffice_bin()
    if not bin_path:
        return None
    # LibreOffice profile must be writable + unique per call to avoid the
    # "another instance already running" race.
    with tempfile.TemporaryDirectory(prefix="lo-profile-") as profile_dir:
        cmd = [
            bin_path,
            "--headless",
            "--nologo",
            "--nofirststartwizard",
            "--norestore",
            f"-env:UserInstallation=file://{profile_dir}",
            "--convert-to", "pdf",
            "--outdir", str(out_dir),
            str(src),
        ]
        try:
            r = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=LIBREOFFICE_TIMEOUT_SEC,
            )
        except subprocess.TimeoutExpired:
            return None
        if r.returncode != 0:
            return None
        # LibreOffice writes <stem>.pdf in out_dir.
        candidate = out_dir / (src.stem + ".pdf")
        if candidate.is_file():
            return candidate
        # Some LO versions slugify the name; fall back to "any newest pdf".
        pdfs = sorted(out_dir.glob("*.pdf"), key=lambda p: p.stat().st_mtime, reverse=True)
        return pdfs[0] if pdfs else None


def repair_pptx_via_python(src: Path, out_dir: Path) -> Path | None:
    """Re-save a pptx via python-pptx, then retry LibreOffice."""
    if not HAVE_PPTX:
        return None
    try:
        prs = _Pptx(str(src))
    except Exception:
        return None
    fixed = out_dir / (src.stem + "__repaired.pptx")
    try:
        prs.save(str(fixed))
    except Exception:
        return None
    pdf = convert_with_libreoffice(fixed, out_dir)
    fixed.unlink(missing_ok=True)
    return pdf


def repair_docx_via_python(src: Path, out_dir: Path) -> Path | None:
    """Re-save a docx via python-docx, then retry LibreOffice."""
    if not HAVE_DOCX:
        return None
    try:
        doc = _Docx(str(src))
    except Exception:
        return None
    fixed = out_dir / (src.stem + "__repaired.docx")
    try:
        doc.save(str(fixed))
    except Exception:
        return None
    pdf = convert_with_libreoffice(fixed, out_dir)
    fixed.unlink(missing_ok=True)
    return pdf


def convert_one(src: Path, dest_dir: Path) -> Path | None:
    """Try LibreOffice direct; fall back to repair-then-LibreOffice."""
    pdf = convert_with_libreoffice(src, dest_dir)
    if pdf:
        return pdf
    ext = src.suffix.lower()
    if ext == ".pptx":
        return repair_pptx_via_python(src, dest_dir)
    if ext == ".docx":
        return repair_docx_via_python(src, dest_dir)
    return None


# ── Cache index ─────────────────────────────────────────────────────────────


def load_index(index_path: Path) -> dict[str, Any]:
    if not index_path.is_file():
        return {}
    try:
        return json.loads(index_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_index(index_path: Path, data: dict[str, Any]) -> None:
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


# ── Driver ──────────────────────────────────────────────────────────────────


def process(
    src: Path,
    repo_root: Path,
    cache_dir: Path,
    index: dict[str, Any],
    dry_run: bool = False,
) -> tuple[str, str]:
    """Return (status, message). Status ∈ {converted, cached, failed, skipped-dry}."""
    try:
        rel = str(src.relative_to(repo_root))
    except ValueError:
        rel = str(src)
    try:
        stat = src.stat()
    except OSError as e:
        return "failed", f"stat failed: {e}"

    existing = index.get(rel)
    if existing:
        # Quick check: mtime+size match → trust it.
        if existing.get("mtime") == stat.st_mtime and existing.get("size") == stat.st_size:
            key = existing.get("key")
            if key and (cache_dir / f"{key}.pdf").is_file():
                return "cached", key
        # mtime/size mismatch: verify by hash before doing the expensive conversion.
        new_sha = file_sha256(src)
        if existing.get("sha256") == new_sha:
            key = existing.get("key")
            if key and (cache_dir / f"{key}.pdf").is_file():
                # Refresh stat snapshot so next run hits the fast path.
                existing["mtime"] = stat.st_mtime
                existing["size"] = stat.st_size
                index[rel] = existing
                return "cached", key
        sha = new_sha
    else:
        sha = file_sha256(src)

    key = cache_key(sha)
    if dry_run:
        return "skipped-dry", key

    cache_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="office-convert-") as work_dir:
        pdf = convert_one(src, Path(work_dir))
        if pdf is None:
            return "failed", "LibreOffice could not produce a PDF"
        target = cache_dir / f"{key}.pdf"
        shutil.move(str(pdf), str(target))

    index[rel] = {
        "key": key,
        "mtime": stat.st_mtime,
        "size": stat.st_size,
        "sha256": sha,
    }
    return "converted", key


def cleanup_orphans(index: dict[str, Any], cache_dir: Path) -> int:
    """Remove cached PDFs whose source file is no longer indexed."""
    keep = {entry["key"] for entry in index.values() if "key" in entry}
    removed = 0
    if not cache_dir.is_dir():
        return 0
    for pdf in cache_dir.glob("*.pdf"):
        if pdf.stem not in keep:
            try:
                pdf.unlink()
                removed += 1
            except OSError:
                pass
    return removed


def main() -> int:
    ap = argparse.ArgumentParser(description="Convert Office files to PDF for the doc-index PWA")
    ap.add_argument("config", help="path to doc-index.yaml")
    ap.add_argument("--file", help="convert a single file (must be inside repo.path)")
    ap.add_argument("--dry-run", action="store_true", help="list work without converting")
    ap.add_argument("--no-cleanup", action="store_true", help="skip orphan-PDF cleanup")
    args = ap.parse_args()

    cfg = load_config(Path(args.config))
    repo_root = Path(cfg["repo"]["path"])
    serve_root = Path(cfg["serve"]["root"])
    ignore_patterns = cfg["repo"].get("ignore", []) or []
    cache_dir = serve_root / CACHE_DIRNAME
    index_path = cache_dir / INDEX_FILENAME

    if not repo_root.is_dir():
        sys.stderr.write(f"repo.path does not exist: {repo_root}\n")
        return 1

    if not libreoffice_bin():
        sys.stderr.write(
            "LibreOffice not found in PATH. Install libreoffice-writer / "
            "libreoffice-impress / libreoffice-calc (or skip Office conversion).\n"
        )
        # Soft-fail: scan.py invokes us best-effort. Exit 0 so the scan as a
        # whole still succeeds; the .pdf-cache just stays empty.
        return 0

    index = load_index(index_path)

    # Build the list of files to process.
    if args.file:
        single = Path(args.file).resolve()
        try:
            single.relative_to(repo_root.resolve())
        except ValueError:
            sys.stderr.write(f"{single} is not under repo.path {repo_root}\n")
            return 1
        if single.suffix.lower() not in OFFICE_EXTS:
            sys.stderr.write(f"{single} is not a known Office extension\n")
            return 1
        sources = [single]
    else:
        sources = list(iter_office_files(repo_root, ignore_patterns))

    print(f"Found {len(sources)} Office file(s)")

    converted = cached = failed = 0
    for src in sources:
        status, msg = process(src, repo_root, cache_dir, index, dry_run=args.dry_run)
        try:
            label = str(src.relative_to(repo_root))
        except ValueError:
            label = str(src)
        if status == "converted":
            converted += 1
            print(f"  ✓ {label}")
        elif status == "cached":
            cached += 1
            print(f"  · {label} (cached)")
        elif status == "skipped-dry":
            print(f"  ? {label} (would convert; key={msg})")
        else:
            failed += 1
            print(f"  ✗ {label} — {msg}", file=sys.stderr)

    if not args.dry_run:
        save_index(index_path, index)
        if not args.no_cleanup:
            n = cleanup_orphans(index, cache_dir)
            if n:
                print(f"Cleaned up {n} orphan PDF(s)")

    print(f"\nDone: {converted} converted, {cached} cached, {failed} failed")
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
