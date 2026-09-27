#!/usr/bin/env python3
"""git_publish.py — shared git-publish helper for doc-index.

Low-level building blocks used by `design_doc.publish` to push the canonical
design doc + proposals to a project's own git repo — in two modes:

  * in_place — the artifacts already live inside a checked-out git working tree
    with a writable remote; we do a SCOPED `git add <paths>` + commit + push
    right there (never `git add -A`).
  * remote   — the artifacts must go to a repo that is NOT a local working tree;
    we clone/fetch it into a cache, copy the whitelisted artifacts in, commit,
    and push.

Two safety rails, applied to the exact file set before anything is staged:
  1. secret_guard() — refuses to publish if any file looks like a secret or is
     not a document (extension allowlist + secret-name/keyword blocklist).
  2. every commit is pathspec-scoped to the resolved artifact set.

Tokens embedded in an HTTPS remote URL are redacted from all log output.
Standard library only. Python 3.8+.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from fnmatch import fnmatch
from pathlib import Path

# ── secret guard ────────────────────────────────────────────────────────────
# Document extensions the publish set is allowed to contain. Anything else is a
# violation (a design-doc publish should only ever move .md + diagrams).
DOC_EXTS = {"md", "markdown", "txt", "pdf", "png", "jpg", "jpeg", "gif", "webp", "svg"}

# Hard secret-file shapes — refused regardless of extension.
SECRET_NAME_GLOBS = (
    ".env", ".env.*", "*.env",
    "*.key", "*.pem", "*.p12", "*.pfx", "*.jks", "*.keystore",
    "*.db", "*.sqlite", "*.sqlite3",
    "id_rsa*", "id_dsa*", "id_ecdsa*", "id_ed25519*",
    "*.htpasswd", ".netrc", ".git-credentials*",
)
# Secret keywords — a violation when they appear in a NON-markdown filename
# (so a proposal like PROPOSAL_token-pricing.md is fine, but tokens.txt is not).
SECRET_KEYWORDS = ("token", "secret", "credential", "password", "passwd", "apikey", "api_key")


def _ext(name: str) -> str:
    n = name.lower()
    return n.rsplit(".", 1)[-1] if "." in n else ""


def secret_guard(abs_files):
    """Return a list of (path, reason) for any file that must not be published.
    Empty list == safe to publish."""
    viol = []
    for f in abs_files:
        name = Path(f).name.lower()
        ext = _ext(name)
        if any(fnmatch(name, g) for g in SECRET_NAME_GLOBS):
            viol.append((str(f), "matches secret-file pattern"))
            continue
        if ext not in DOC_EXTS:
            viol.append((str(f), f"unexpected non-document extension .{ext or '(none)'}"))
            continue
        if ext not in ("md", "markdown") and any(k in name for k in SECRET_KEYWORDS):
            viol.append((str(f), "secret keyword in filename"))
    return viol


# ── url redaction ─────────────────────────────────────────────────────────────
def redact(url: str) -> str:
    """Hide any user:token@ credentials embedded in an HTTPS git URL."""
    if url and "://" in url and "@" in url:
        scheme, rest = url.split("://", 1)
        if "@" in rest:
            return f"{scheme}://<redacted>@{rest.split('@', 1)[1]}"
    return url


# ── low-level git ─────────────────────────────────────────────────────────────
def run(cmd, cwd=None, check=True):
    return subprocess.run(cmd, cwd=cwd, check=check, capture_output=True, text=True)


def detect_worktree(path):
    """Return (is_repo, toplevel, origin_url, branch) for a path.
    is_repo is False when path is not inside a git working tree."""
    p = str(path)
    r = run(["git", "-C", p, "rev-parse", "--show-toplevel"], check=False)
    if r.returncode != 0:
        return (False, None, None, None)
    toplevel = r.stdout.strip()
    origin = run(["git", "-C", p, "remote", "get-url", "origin"], check=False)
    origin_url = origin.stdout.strip() if origin.returncode == 0 else None
    br = run(["git", "-C", p, "rev-parse", "--abbrev-ref", "HEAD"], check=False)
    branch = br.stdout.strip() if br.returncode == 0 else None
    return (True, toplevel, origin_url, branch)


def _set_identity(repo_dir, author_name, author_email):
    """Set a LOCAL (per-clone) git identity only when explicitly configured.
    Empty name/email -> leave the repo's own git identity in place."""
    if author_name:
        run(["git", "-C", repo_dir, "config", "user.name", author_name])
    if author_email:
        run(["git", "-C", repo_dir, "config", "user.email", author_email])


def _push_with_retry(repo_dir, branch):
    push = run(["git", "-C", repo_dir, "push", "origin", branch], check=False)
    if push.returncode != 0:
        # Non-fast-forward or transient — rebase onto remote and retry once.
        run(["git", "-C", repo_dir, "pull", "--rebase", "--autostash", "origin", branch])
        run(["git", "-C", repo_dir, "push", "origin", branch])


# ── mode: in_place ────────────────────────────────────────────────────────────
def publish_in_place(repo_dir, abs_files, branch, commit_msg,
                     author_name="", author_email="", dry_run=False):
    """Scoped commit + push of abs_files, which must live inside repo_dir's tree.
    Returns {'pushed': bool, 'skipped': str|None}."""
    repo_dir = str(Path(repo_dir).resolve())
    rels = []
    for f in abs_files:
        fp = Path(f).resolve()
        try:
            rels.append(str(fp.relative_to(repo_dir)))
        except ValueError:
            return {"pushed": False, "skipped": f"file outside repo_dir: {fp}"}
    if not rels:
        return {"pushed": False, "skipped": "no files"}

    run(["git", "-C", repo_dir, "add", "--"] + rels)
    staged = run(["git", "-C", repo_dir, "diff", "--cached", "--quiet", "--"] + rels, check=False)
    if staged.returncode == 0:
        # Nothing staged in our paths — leave the index as we found it.
        run(["git", "-C", repo_dir, "reset", "-q", "--"] + rels, check=False)
        return {"pushed": False, "skipped": "no changes"}
    if dry_run:
        run(["git", "-C", repo_dir, "reset", "-q", "--"] + rels, check=False)
        return {"pushed": False, "skipped": "dry-run"}

    _set_identity(repo_dir, author_name, author_email)
    run(["git", "-C", repo_dir, "commit", "-q", "-m", commit_msg, "--"] + rels)
    _push_with_retry(repo_dir, branch)
    return {"pushed": True, "skipped": None}


# ── mode: remote ──────────────────────────────────────────────────────────────
def _ensure_clone(remote_url, branch, clone_dir):
    clone_dir = Path(clone_dir).expanduser()
    if (clone_dir / ".git").exists():
        run(["git", "-C", str(clone_dir), "fetch", "origin", branch])
        run(["git", "-C", str(clone_dir), "checkout", branch], check=False)
        run(["git", "-C", str(clone_dir), "reset", "--hard", f"origin/{branch}"])
    else:
        clone_dir.parent.mkdir(parents=True, exist_ok=True)
        run(["git", "clone", "--depth", "1", "--branch", branch, remote_url, str(clone_dir)])
    return clone_dir


def publish_remote(remote_url, branch, target_dir, pairs, commit_msg,
                   author_name="", author_email="", clone_dir=None, dry_run=False):
    """Copy pairs [(rel_path, abs_path)] into <clone>/<target_dir>, commit, push.
    Returns {'pushed': bool, 'skipped': str|None}."""
    if not remote_url or remote_url.startswith("<"):
        return {"pushed": False, "skipped": "remote_url not configured"}
    clone = _ensure_clone(remote_url, branch, clone_dir)
    dest_root = clone / target_dir if target_dir else clone

    # Recreate the target subtree from scratch so removed docs don't linger.
    if target_dir and dest_root.exists():
        shutil.rmtree(dest_root)
    dest_root.mkdir(parents=True, exist_ok=True)
    for rel_p, abs_p in pairs:
        dest = dest_root / rel_p
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(abs_p, dest)

    add_path = target_dir if target_dir else "."
    run(["git", "-C", str(clone), "add", "--", add_path])
    staged = run(["git", "-C", str(clone), "diff", "--cached", "--quiet"], check=False)
    if staged.returncode == 0:
        return {"pushed": False, "skipped": "no changes"}
    if dry_run:
        return {"pushed": False, "skipped": "dry-run"}

    _set_identity(str(clone), author_name, author_email)
    run(["git", "-C", str(clone), "commit", "-q", "-m", commit_msg])
    _push_with_retry(str(clone), branch)
    return {"pushed": True, "skipped": None}
