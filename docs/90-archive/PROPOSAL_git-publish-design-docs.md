# Proposal: design_doc.publish — auto-push design doc + proposals to the project's git repo
> Date: 2026-09-27 · Author: maintainer · Status: implemented

## Problem

When doc-index deploys for a project, the design doc (`docs/DESIGN.md`) and its
proposals (`docs/10-next/` + `docs/90-archive/PROPOSAL_*.md`) currently live in
two places only: (a) the local PWA, and (b) wherever the operator *manually*
commits them. That manual push is ad-hoc — every operator/agent does it
differently, with no standard. Two failure modes follow:

1. If the PWA host is lost, the design intent + full proposal history may not
   exist in the project's own GitHub repo — the record dies with the server.
2. Nothing guarantees the repo copy is *current* — it drifts from the doc the
   Gate actually maintains.

## Goal

Make "the canonical design doc + all proposals also live in the project's own
git repo, on the main branch, kept current automatically" a first-class,
config-driven capability of doc-index — not a per-operator ritual. So anyone can
open the GitHub repo and read the design + every proposal, PWA or no PWA.

## Design

New block under `design_doc:` (off by default; opt-in per project):

```yaml
design_doc:
  enabled: true
  path: docs/DESIGN.md
  proposal_ledger: true
  publish:
    enabled: true
    mode: in_place              # in_place | remote
    branch: main
    include:                    # WHITELIST — only these artifacts are published
      - docs/DESIGN.md
      - docs/10-next/**/*.md
      - docs/90-archive/**/*.md
    # in_place mode (artifacts already live inside a git working tree):
    repo_dir: ""                # git tree to commit in   (default: repo.path)
    source_root: ""             # where artifacts live    (default: repo.path)
    # remote mode (push to a separate repo / doc-index host has no git tree):
    remote_url: ""              # https://USER:TOKEN@github.com/org/proj.git  (token redacted in logs)
    target_dir: "docs"          # path inside the target repo to place artifacts
    local_clone_dir: ""         # default ~/.cache/doc-index-publish/<short_name>
    # common:
    push_on: [init, scan]       # when to publish
    commit_message_template: "doc-index: design doc + proposals ({project} @ {timestamp})"
    author_name: "doc-index-publish"
    author_email: "noreply@doc-index.local"
    soft_fail: true             # publish errors never break scan/PWA
```

### Two modes

**in_place** — the artifacts already sit inside a git repo with a writable
remote (e.g. the project repo itself). doc-index does a *scoped*
`git add <include> && git commit -- <include> && git push origin <branch>` in
`repo_dir`. `source_root`/`repo_dir` decouple the two when `repo.path` is not the
git tree — e.g. a safe-serving staging root: `repo_dir` + `source_root` point at
the real repo while `repo.path` stays the staging root.

**remote** — the artifacts must go to a *different* repo, or doc-index runs where
the docs are not in a git tree. doc-index clones/fetches `remote_url` into a
cache, copies the `include`-matched files into `target_dir`, commits, pushes.
Reuses the machinery already proven by the existing `sync:` feature.

### When it runs

- `serve.py init` → initial publish, so the repo has the design doc from day one.
- `scan.py` (after ledger sync) → re-publish if changed. This is the "every
  rebuild stays current" guarantee. Idempotent: no empty commits.

### Safety (non-negotiable)

- **Whitelist only.** Publish exactly the `include` globs — never `repo.path`
  wholesale (would leak secrets/corpus). Default include = the Gate's own
  artifacts.
- **Secret guard.** Before staging, refuse any file matching secret patterns
  (`*token*`, `*secret*`, `*credential*`, `.env*`, `*.key/.pem`, `*.db/.sqlite`)
  even if an `include` glob caught it — fail loud, publish nothing.
- **Scoped commit** (pathspec) — never touches files outside `include`.
- **soft_fail** — a push failure logs and returns; the PWA keeps working.
- Token redacted in all logs. Respect the target repo's `.gitignore`.

### Relationship to existing `sync:`

`sync:` publishes the whole generated INDEX + all source docs to a *shared hub*
repo under a subdir (team mesh / snapshot mirror). `design_doc.publish:`
publishes *only* the canonical design doc + proposals to the *project's own*
repo main, so design lives beside code. Different intent, overlapping mechanics
→ factor a shared `git_publish` helper both call (clone/fetch, scoped commit,
push-with-rebase-retry, token redaction).

## Open decisions (for review)

1. **Default `push_on`** — both `init` + `scan` (recommend: yes; `scan` = every
   rebuild is what keeps the repo current).
2. **Primary mode** — auto-pick `in_place` when `repo.path` is inside a git repo
   with a remote, else `remote`? Or always explicit in config? (recommend
   auto-detect with explicit override.)
3. **Commit identity** — bot identity default vs. maintainer's git identity?
   (recommend configurable, bot default.)
4. **Secret guard severity** — hard-fail the whole publish on any secret match
   (recommend), vs. skip the offending file and continue.
5. **Scope** — ship `in_place` first (covers most single-repo projects), add
   `remote` in a second pass? Or both at once?

## Implementation sketch

- `scripts/git_publish.py` — shared helper (clone/fetch, scoped stage+commit,
  push w/ rebase retry, redaction, secret guard).
- `design_doc.publish(cfg, repo_path, phase)` in `design_doc.py` — resolves mode,
  gathers `include`, calls the helper. Soft-fail.
- Hook points: `serve.py init` (phase=init) + `scan.py` end (phase=scan), gated
  on `publish.enabled` and `phase in push_on`.
- Docs: `DESIGN_DOC_CONVENTION.md` + `config.example.yaml` + SKILL.md.
- Tests: whitelist scoping, secret-guard hard-fail, idempotent no-op, in_place
  vs remote, soft-fail on unreachable remote.
