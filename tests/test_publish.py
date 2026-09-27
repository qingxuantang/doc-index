#!/usr/bin/env python3
"""Tests for design_doc.publish + git_publish (in_place + remote + secret guard).

Self-contained: builds throwaway git repos in a temp dir. No network.
Run: python3 tests/test_publish.py
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import design_doc  # noqa: E402
import git_publish as gp  # noqa: E402

PASS, FAIL = 0, 0


def check(name, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok  {name}")
    else:
        FAIL += 1
        print(f"  XX  {name}")


def git(args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)


def make_project(root):
    """A git working tree with a design doc + one proposal, wired to a bare remote."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "docs" / "90-archive").mkdir(parents=True)
    (root / "docs" / "DESIGN.md").write_text(
        "# X · Design Doc\n\n## Proposal Ledger\n\n"
        "| # | Date | Title | Status | Approved by | Landed | Detail |\n"
        "|---|------|-------|--------|-------------|--------|--------|\n"
        "| 1 | 2026-01-01 | seed | implemented | a | 2026-01-01 | `docs/90-archive/PROPOSAL_seed.md` |\n",
        encoding="utf-8")
    (root / "docs" / "90-archive" / "PROPOSAL_seed.md").write_text(
        "# Proposal: seed\n> Date: 2026-01-01 · Author: a · Status: implemented\n\nbody\n",
        encoding="utf-8")
    # non-doc / secret files that must NEVER be published
    (root / "docs" / "notes.md").write_text("# notes\n", encoding="utf-8")
    git(["init", "-q", "-b", "main"], root)
    git(["config", "user.email", "t@t"], root); git(["config", "user.name", "t"], root)
    git(["add", "-A"], root); git(["commit", "-qm", "init"], root)


def make_bare_remote(path):
    path.mkdir(parents=True, exist_ok=True)
    git(["init", "-q", "--bare", "-b", "main"], path)
    return path


def cfg_for(pub):
    return {"project": {"name": "X", "short_name": "X"},
            "design_doc": {"enabled": True, "path": "docs/DESIGN.md",
                           "proposal_ledger": True, "publish": pub}}


def main():
    tmp = Path(tempfile.mkdtemp(prefix="ditest_"))
    try:
        # ---- secret guard unit ----
        v = gp.secret_guard(["/x/DESIGN.md", "/x/PROPOSAL_token-pricing.md"])
        check("secret_guard: .md incl. 'token' in name is allowed", v == [])
        v = gp.secret_guard(["/x/.env"]); check("secret_guard: .env blocked", len(v) == 1)
        v = gp.secret_guard(["/x/oauth_tokens.json"]); check("secret_guard: *_tokens.json blocked", len(v) == 1)
        v = gp.secret_guard(["/x/creds.key"]); check("secret_guard: .key blocked", len(v) == 1)
        v = gp.secret_guard(["/x/data.db"]); check("secret_guard: .db blocked", len(v) == 1)
        check("redact hides token", gp.redact("https://u:tok@github.com/a/b.git") == "https://<redacted>@github.com/a/b.git")

        # ---- in_place: clone a bare remote, publish, verify pushed ----
        remote = make_bare_remote(tmp / "remote_inplace.git")
        work = tmp / "work"
        git(["clone", "-q", str(remote), str(work)], tmp)
        make_project_in_clone(work)
        cfg = cfg_for({"enabled": True, "mode": "in_place", "branch": "main"})
        r = design_doc.publish(cfg, str(work), "scan")
        check("in_place: pushed", r["pushed"] and r["mode"] == "in_place" and not r["error"])
        # verify remote HEAD contains DESIGN.md + proposal but NOT notes.md/secret
        ls = git(["ls-tree", "-r", "--name-only", "main"], remote).stdout.splitlines()
        check("in_place: DESIGN.md on remote", "docs/DESIGN.md" in ls)
        check("in_place: proposal on remote", "docs/90-archive/PROPOSAL_seed.md" in ls)
        check("in_place: notes.md NOT published (not in include)", "docs/notes.md" not in ls)
        check("in_place: .env NOT on remote", not any(".env" in x for x in ls))

        # ---- idempotency: second publish is a no-op ----
        r2 = design_doc.publish(cfg, str(work), "scan")
        check("in_place: idempotent no-op", (not r2["pushed"]) and r2["skipped"] == "no changes")

        # ---- new proposal shows up on next publish ----
        (work / "docs" / "10-next").mkdir(parents=True, exist_ok=True)
        (work / "docs" / "10-next" / "PROPOSAL_new.md").write_text(
            "# Proposal: new\n> Date: 2026-02-02 · Author: b · Status: proposed\n", encoding="utf-8")
        r3 = design_doc.publish(cfg, str(work), "scan")
        ls = git(["ls-tree", "-r", "--name-only", "main"], remote).stdout.splitlines()
        check("in_place: new proposal published", r3["pushed"] and "docs/10-next/PROPOSAL_new.md" in ls)

        # ---- secret guard hard-fail: a token file caught by include stops everything ----
        (work / "docs" / "10-next" / "leaked_tokens.json").write_text("{}", encoding="utf-8")
        cfg_leak = cfg_for({"enabled": True, "mode": "in_place",
                            "include": ["docs/DESIGN.md", "docs/10-next/**/*"]})
        r4 = design_doc.publish(cfg_leak, str(work), "scan")
        check("secret guard: hard-fail on token file", (not r4["pushed"]) and r4["error"] and "secret guard" in r4["error"])
        (work / "docs" / "10-next" / "leaked_tokens.json").unlink()

        # ---- push_on gating ----
        cfg_initonly = cfg_for({"enabled": True, "mode": "in_place", "push_on": ["init"]})
        r5 = design_doc.publish(cfg_initonly, str(work), "scan")
        check("push_on: scan skipped when only init", r5["skipped"] and "push_on" in r5["skipped"])

        # ---- disabled ----
        r6 = design_doc.publish(cfg_for({"enabled": False}), str(work), "scan")
        check("disabled: skipped", r6["skipped"] == "disabled")

        # ---- remote mode ----
        remote2 = make_bare_remote(tmp / "remote_remote.git")
        # seed remote2 with an initial main commit so clone --branch main works
        seed = tmp / "seed"; git(["clone", "-q", str(remote2), str(seed)], tmp)
        (seed / "README.md").write_text("x\n", encoding="utf-8")
        git(["config", "user.email", "t@t"], seed); git(["config", "user.name", "t"], seed)
        git(["add", "-A"], seed); git(["commit", "-qm", "seed"], seed); git(["push", "-q", "origin", "main"], seed)
        src = tmp / "srcdocs"; make_project(src)  # a git tree, but we publish REMOTE from it
        cfg_remote = cfg_for({"enabled": True, "mode": "remote", "branch": "main",
                              "remote_url": str(remote2), "target_dir": "design",
                              "local_clone_dir": str(tmp / "clone_cache")})
        r7 = design_doc.publish(cfg_remote, str(src), "scan")
        ls2 = git(["ls-tree", "-r", "--name-only", "main"], remote2).stdout.splitlines()
        check("remote: pushed", r7["pushed"] and r7["mode"] == "remote")
        check("remote: DESIGN under target_dir", "design/docs/DESIGN.md" in ls2)
        check("remote: notes.md excluded", "design/docs/notes.md" not in ls2)

        # ---- dry-run pushes nothing ----
        (work / "docs" / "DESIGN.md").write_text("# X · Design Doc\n\nchanged\n", encoding="utf-8")
        before = git(["rev-parse", "main"], remote).stdout.strip()
        rd = design_doc.publish(cfg, str(work), "scan", dry_run=True)
        after = git(["rev-parse", "main"], remote).stdout.strip()
        check("dry-run: nothing pushed", (not rd["pushed"]) and before == after)

    finally:
        subprocess.run(["rm", "-rf", str(tmp)])

    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


def make_project_in_clone(work):
    """Like make_project but in an already-cloned working tree (has origin)."""
    (work / "docs" / "90-archive").mkdir(parents=True)
    (work / "docs" / "DESIGN.md").write_text("# X · Design Doc\n\nintent\n", encoding="utf-8")
    (work / "docs" / "90-archive" / "PROPOSAL_seed.md").write_text(
        "# Proposal: seed\n> Date: 2026-01-01 · Author: a · Status: implemented\n", encoding="utf-8")
    (work / "docs" / "notes.md").write_text("# notes\n", encoding="utf-8")
    (work / "docs" / ".env").write_text("SECRET=1\n", encoding="utf-8")
    git(["config", "user.email", "t@t"], work); git(["config", "user.name", "t"], work)


if __name__ == "__main__":
    sys.exit(main())
