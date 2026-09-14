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
installable PWA document browser served by nginx behind basic auth. It is
deliberately a **documentation** browser, not a code browser: a positive
whitelist (`repo.file_types`) surfaces plans, specs, diagrams and notes, and
skips source code. Config-driven — one `doc-index.yaml` per project, drop it on
any server.

## Architecture / how it works

- **`scripts/scan.py`** — walks the repo, builds a section tree from the folder
  structure (`sections.promote` lifts status folders to the top), tags new/
  updated files from git timestamps, and renders `index.html` + `manifest.json`
  from `templates/`.
- **`scripts/serve.py`** — first-time deploy: nginx check, serve dir + `docs`
  symlink, PWA icons, viewer templates, basic auth, cron, the Design Doc Gate
  preflight, and the initial scan. Prints the nginx server block.
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
- **Basic auth is ON by default.**
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

<!--
Status values (in order):
  proposed → approved → landed → implemented → superseded
-->
