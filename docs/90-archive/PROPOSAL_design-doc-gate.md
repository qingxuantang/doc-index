# Proposal: Design Doc Gate (v1)

- **Status:** implemented
- **Proposed:** 2026-09-14
- **Approved by:** maintainer · 2026-09-14
- **Landed:** yes — into `docs/DESIGN.md` + `DESIGN_DOC_CONVENTION.md`

## Problem

doc-index has no concept of a design doc. The `DESIGN.md` convention (hand-
written intent + an auto-refreshed live-config snapshot) lived only in one
downstream deployment. Whether a project had a design doc, kept it fresh, or
routed changes through it was entirely manual — and a project with no design
doc produced no signal.

## What v1 ships

1. **`design_doc:` config block** (on by default; `enabled: false` opts out).
2. **First-deploy preflight** in `serve.py init` — detect existing design docs,
   then one of three branches:
   - **Adopt** — canonical `docs/DESIGN.md` exists → keep it, append only
     missing scaffolding (Proposal Ledger / AUTO markers), never touch prose.
   - **Incorporate** — design content elsewhere (`ARCHITECTURE.md`,
     `docs/20-design/`, `*design*.md`) → generate the canonical doc that **links
     to them in place**; originals untouched.
   - **Generate** — none → write a seed from `templates/DESIGN.template.md`.
   Non-blocking (auto-seeds); fails loud only on a real IO error.
3. **Freshness check** (`design_doc.freshness`) — missing / unfilled / stale
   snapshot → reported by `scan.py` and reusable by a health digest.
4. **Pinned PWA card** — top of the index, freshness badge + open-proposal count.
5. **Proposal Ledger** — the `Proposal → Approved → Landed → Implemented` gate,
   machine-readable via the status column.
6. **Docs** — `DESIGN_DOC_CONVENTION.md` + SKILL.md section.

## Decisions (as approved)

- **D1** — auto-seed, non-blocking (unfilled seed flagged, not a hard stop).
- **D2** — enforce by convention + PWA visibility + optional advisory lint; no
  hard pre-commit block (a silently-refusing guard is its own failure mode).
- **D3** — incorporate = reference in place; never move/rewrite originals.
- **D4** — ship v1 (config + preflight + template + freshness + PWA card) first.

## v2 backlog (not in this cut)

- Generic AUTO-snapshot helper (`gen_design_snapshot.py`) with a pluggable
  project generator; migrate the downstream generator onto it.
- `serve.py proposal new|approve|land` helpers + `design-doc adopt`.
- Advisory lint for un-landed changes; wire freshness into the daily health
  digest.

## Verification

- 21/21 module unit checks (three branches, freshness states, ledger parse,
  card render).
- End-to-end `scan.py` run: seed generated, `🟡 unfilled` surfaced, card
  rendered with correct badge, no leftover placeholder, clean imports.
