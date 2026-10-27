# doc-index · Design Doc

> Single source of intent for doc-index. Hand-written sections say **why** it
> exists and **how** it works; the Proposal Ledger gates every change.
>
> **Governance:** every optimization or upgrade goes
> **Proposal → Approved → Landed here → Implemented**. Nothing ships before it is
> landed in this doc. This repo is the reference implementation of its own
> [Design Doc Gate](../DESIGN_DOC_CONVENTION.md).

## What this project is

doc-index turns any project repo's folder of documents into a mobile-friendly,
installable PWA document browser. It serves two ways (`serve.mode`): **nginx**
behind basic auth on a public domain (default), or **local** — a plain
`http.server` bound to this box or the LAN, no nginx/domain/auth. It is
deliberately a **documentation** browser, not a code browser: a positive
whitelist (`repo.file_types`) surfaces plans, specs, diagrams and notes, and
skips source code. Config-driven — one `doc-index.yaml` per project, drop it on
any server.

## Architecture / how it works

- **`scripts/scan.py`** — walks the repo, builds a section tree from the folder
  structure (`sections.promote` lifts status folders to the top), tags new/
  updated files from git timestamps, and renders `index.html` + `manifest.json`
  from `templates/`.
- **`scripts/serve.py`** — first-time deploy, branched on `serve.mode`. **nginx**
  (default): nginx check, `docs` symlink, basic auth, cron, Design Doc Gate,
  initial scan, prints the nginx server block. **local**: skips nginx/auth,
  materializes `docs` as a real copy (`materialize_docs` → `scan.sync_docs_copy`,
  portable + re-synced each scan), and `serve.py serve` binds an `http.server`
  (`bind_host`/`bind_port`) with a security banner.
- **`scripts/design_doc.py`** — the Design Doc Gate (see ledger below).
- **`scripts/sync.py`** — optional post-scan mirror to a shared git repo.
- **`scripts/convert-office.py`** — pre-converts Office files to PDF for preview.
- **`templates/`** — pure `{{PLACEHOLDER}}` HTML/JS; viewers for PDF / MD / YAML
  / Office, service worker, and the seed `DESIGN.template.md`.

## Key decisions & constraints

- **Doc-only filter is core.** Adding source-code extensions to
  `repo.file_types` is a misuse — use a code tool for that.
- **Config drives everything.** No project-specific values hardcoded in
  templates or scripts.
- **scan.py is idempotent; serve.py init is non-destructive.** Safe to re-run;
  checks before overwriting.
- **Basic auth is ON by default.** It is an nginx-mode guarantee; `local` mode
  has no auth by design (its boundary: want security → use nginx).
- **`serve.mode` defaults to `nginx`.** Local is opt-in — flipping the default
  would silently change every existing deployment. The `content: copy` strategy
  (local's default, also usable in nginx mode when the repo isn't nginx-readable,
  e.g. under `/root`) re-syncs on every scan and excludes `repo.ignore`, so
  `.git`/`.env` are never materialized into `serve.root`.
- **Sync soft-fails.** A shared-repo push failure never breaks the local PWA.
- **Absence is a signal.** Missing/stale artifacts (design doc, snapshot) are
  reported, never silently green.

## Live config snapshot

<!-- AUTO:START -->
<!-- auto_snapshot is off for this repo; block intentionally empty. -->
<!-- AUTO:END -->

## Proposal Ledger

Every change lands here before it is built. Active detail files live in
`docs/10-next/PROPOSAL_<slug>.md`; implemented ones move to `docs/90-archive/`.

| # | Date | Title | Status | Approved by | Landed | Detail |
|---|------|-------|--------|-------------|--------|--------|
| 1 | 2026-09-14 | Design Doc Gate (v1) | implemented | maintainer | yes | [PROPOSAL](90-archive/PROPOSAL_design-doc-gate.md) |
| 2 | 2026-09-27 | design_doc.publish — auto-push design doc + proposals to the project's git repo | implemented | maintainer | 2026-09-27 | `docs/90-archive/PROPOSAL_git-publish-design-docs.md` |
| 3 | 2026-10-27 | serve.mode — local / internal-network serving as a first-class option | implemented | maintainer | 2026-10-27 | `docs/90-archive/PROPOSAL_local-serve-mode.md` |

<!--
Status values (in order):
  proposed → approved → landed → implemented → superseded
-->
