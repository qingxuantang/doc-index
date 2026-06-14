#!/usr/bin/env python3
"""Doc Index Sync — mirror the generated index + source docs to a shared git repo.

Optional post-scan step. When `sync.enabled: true` in `doc-index.yaml`,
`scan.py` calls this script to publish the project's docs into a target
subfolder of a shared git repo.

Why this exists: doc-index runs on one device, but the docs it indexes may
need to be readable from other devices that don't have direct filesystem
access. Sync provides eventual consistency via git so any device can
`git pull` the shared repo and read the latest snapshot.

Behavior:
- Reads the `sync:` block from `doc-index.yaml`
- Clones (first run) or fetches + hard-resets (subsequent runs) the configured
  remote repo into `local_clone_dir`
- Recreates `<target_subdir>/` inside the clone and populates it with:
    - source docs matching `repo.file_types` / `repo.ignore`
    - generated `_index.html` (from `serve.root/index.html`)
    - generated `_manifest.json` (from `serve.root/manifest.json`) if present
- Commits + pushes if there are changes
- **Soft-fails** — sync errors do NOT break `scan.py`. Local PWA keeps working.

Usage:
    python3 sync.py <config.yaml>             # invoked by scan.py
    python3 sync.py <config.yaml> --dry-run   # show what would change
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from datetime import datetime
from fnmatch import fnmatch
from pathlib import Path

import yaml


def _run(cmd, cwd=None, check=True):
    """Run subprocess, capture stdout/stderr, raise on nonzero if check."""
    return subprocess.run(
        cmd, cwd=cwd, check=check,
        capture_output=True, text=True,
    )


def load_config(path):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def normalize_paths(cfg):
    cfg["repo"]["path"] = str(Path(cfg["repo"]["path"]).expanduser())
    if "serve" in cfg and "root" in cfg["serve"]:
        cfg["serve"]["root"] = str(Path(cfg["serve"]["root"]).expanduser())
    return cfg


def should_ignore(name, patterns):
    return any(fnmatch(name, p) or p in name for p in patterns)


def collect_source_docs(repo_path, file_types, ignore_patterns):
    """Walk repo_path, return list of (relative_path, absolute_path) for files
    matching `file_types` and not matching `ignore_patterns`."""
    repo = Path(repo_path)
    exts = tuple(f".{ft.lower().lstrip('.')}" for ft in file_types)
    docs = []
    for root, dirs, files in os.walk(repo):
        dirs[:] = [d for d in dirs if not should_ignore(d, ignore_patterns)]
        for f in files:
            if should_ignore(f, ignore_patterns):
                continue
            if f.lower().endswith(exts):
                abs_p = Path(root) / f
                rel_p = abs_p.relative_to(repo)
                docs.append((rel_p, abs_p))
    return docs


def ensure_local_clone(remote_url, branch, local_dir, author_name=None, author_email=None):
    """Ensure local_dir contains a git clone of remote_url@branch.

    Also configures a local git identity inside the clone (NOT globally) so
    sync commits work even when the host root user has no global git identity
    set. Defaults are a generic bot identity; override via sync.author_name /
    sync.author_email in config.yaml.
    """
    local_dir = Path(local_dir).expanduser()
    if (local_dir / ".git").exists():
        _run(["git", "-C", str(local_dir), "fetch", "origin", branch])
        # Checkout target branch and hard-reset to remote head to avoid stale
        # local state from a previous interrupted sync.
        _run(["git", "-C", str(local_dir), "checkout", branch], check=False)
        _run(["git", "-C", str(local_dir), "reset", "--hard", f"origin/{branch}"])
    else:
        local_dir.parent.mkdir(parents=True, exist_ok=True)
        _run(["git", "clone", "--depth", "1", "--branch", branch, remote_url, str(local_dir)])

    # Set local identity inside the clone. Safe to call repeatedly — git just
    # overwrites. Local-only (not --global), scoped to this clone.
    _run(["git", "-C", str(local_dir), "config", "user.name",
          author_name or "doc-index-sync"])
    _run(["git", "-C", str(local_dir), "config", "user.email",
          author_email or "noreply@doc-index.local"])
    return local_dir


def populate_target(clone_dir, target_subdir, source_pairs, index_html=None, manifest_json=None):
    """Recreate <clone_dir>/<target_subdir>/ with a fresh doc tree."""
    target = clone_dir / target_subdir
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)

    # Source docs
    for rel_p, abs_p in source_pairs:
        dest = target / rel_p
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(abs_p, dest)

    # Generated artifacts — prefixed with `_` to keep them visually separate
    # from source docs when receivers browse the shared repo.
    if index_html and Path(index_html).exists():
        shutil.copy2(index_html, target / "_index.html")
    if manifest_json and Path(manifest_json).exists():
        shutil.copy2(manifest_json, target / "_manifest.json")

    return target


def commit_and_push(clone_dir, branch, commit_msg, dry_run=False):
    """git add + commit (only if there are staged changes) + push.

    Returns True if a commit was actually pushed; False if nothing changed.
    Retries once on push rejection by pulling --rebase first.
    """
    _run(["git", "-C", str(clone_dir), "add", "-A"])
    r = _run(["git", "-C", str(clone_dir), "diff", "--cached", "--quiet"], check=False)
    if r.returncode == 0:
        print("  No changes to sync — already up to date")
        return False
    if dry_run:
        stat = _run(["git", "-C", str(clone_dir), "diff", "--cached", "--stat"]).stdout
        print(f"  [dry-run] would commit + push:\n{stat}")
        return False

    _run(["git", "-C", str(clone_dir), "commit", "-m", commit_msg])
    push_r = _run(["git", "-C", str(clone_dir), "push", "origin", branch], check=False)
    if push_r.returncode != 0:
        msg = (push_r.stderr or push_r.stdout or "").strip()[:300]
        print(f"  Push rejected — retrying after pull --rebase. ({msg})")
        _run(["git", "-C", str(clone_dir), "pull", "--rebase", "origin", branch])
        _run(["git", "-C", str(clone_dir), "push", "origin", branch])
    return True


def main(argv):
    dry_run = "--dry-run" in argv
    args = [a for a in argv if a != "--dry-run"]
    if len(args) < 1:
        print("Usage: sync.py <config.yaml> [--dry-run]", file=sys.stderr)
        return 2
    config_path = args[0]

    cfg = normalize_paths(load_config(config_path))
    sync_cfg = cfg.get("sync") or {}

    if not sync_cfg.get("enabled", False):
        print("  Sync disabled (set sync.enabled: true to enable)")
        return 0

    remote_url = (sync_cfg.get("remote_url") or "").strip()
    if not remote_url or remote_url.startswith("<"):
        print(f"  ✗ sync.remote_url not configured (got {remote_url!r}); skipping")
        return 0

    branch = sync_cfg.get("remote_branch", "main")
    target_subdir = (sync_cfg.get("target_subdir") or "").strip()
    if not target_subdir or target_subdir.startswith("<"):
        print(f"  ✗ sync.target_subdir not configured (got {target_subdir!r}); skipping")
        return 0

    short_name = cfg["project"].get("short_name", "doc-index")
    default_clone = Path.home() / ".cache" / "doc-index-sync" / short_name
    local_clone_dir = (sync_cfg.get("local_clone_dir") or "").strip() or str(default_clone)

    include_docs = sync_cfg.get("include_docs", True)
    include_html = sync_cfg.get("include_html", True)

    commit_template = sync_cfg.get(
        "commit_message_template",
        "doc-index sync: {project} @ {timestamp}",
    )
    commit_msg = commit_template.format(
        project=cfg["project"].get("name", short_name),
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M"),
    )

    # Redact token from display so logs don't leak credentials embedded in URL
    display_remote = remote_url
    if "@" in display_remote and "://" in display_remote:
        scheme, rest = display_remote.split("://", 1)
        if "@" in rest:
            display_remote = f"{scheme}://<redacted>@{rest.split('@', 1)[1]}"

    author_name = sync_cfg.get("author_name")
    author_email = sync_cfg.get("author_email")

    print("→ Sync to shared repo …")
    print(f"  Remote: {display_remote}  (branch: {branch})")
    print(f"  Target subdir: {target_subdir}")
    print(f"  Local clone: {local_clone_dir}")

    try:
        clone_dir = ensure_local_clone(
            remote_url, branch, local_clone_dir,
            author_name=author_name, author_email=author_email,
        )

        source_pairs = []
        if include_docs:
            source_pairs = collect_source_docs(
                cfg["repo"]["path"],
                cfg["repo"].get("file_types", []),
                cfg["repo"].get("ignore", []),
            )
            print(f"  Collected {len(source_pairs)} source docs to publish")

        index_html = manifest_json = None
        if include_html and "serve" in cfg:
            serve_root = Path(cfg["serve"]["root"])
            if (serve_root / "index.html").exists():
                index_html = serve_root / "index.html"
            if (serve_root / "manifest.json").exists():
                manifest_json = serve_root / "manifest.json"

        populate_target(
            clone_dir, target_subdir, source_pairs,
            index_html=index_html, manifest_json=manifest_json,
        )

        pushed = commit_and_push(clone_dir, branch, commit_msg, dry_run=dry_run)
        if pushed:
            print(f"  ✓ Pushed to {display_remote} {branch}")
        return 0

    except subprocess.CalledProcessError as e:
        print(f"  ✗ sync failed: {e.cmd!r} returned {e.returncode}", file=sys.stderr)
        if e.stderr:
            print(f"     stderr: {e.stderr[:500]}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"  ✗ sync failed: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
