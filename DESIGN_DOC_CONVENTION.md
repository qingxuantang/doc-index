# Design Doc Gate — Convention

doc-index treats a project **design doc** as a first-class citizen: a single
`docs/DESIGN.md` that holds the project's intent, and a **Proposal Ledger** that
gates change. This doc explains the convention; the mechanics live in
`scripts/design_doc.py` and the `design_doc:` block of `config.example.yaml`.

## Why

A design doc that only exists when someone remembers to write one rots quietly —
and its absence produces no signal. This gate makes the doc **mandatory on first
deploy**, **checked on every scan**, and **visible on the PWA**, so a missing or
stale design doc turns into a red badge instead of silence.

It also gives every project one enforced path for change:

> **Proposal → Approved → Landed → Implemented.** Nothing ships before it lands
> in the design doc.

## What happens on first deploy

`serve.py init` runs a design-doc preflight that detects what the project
already has and takes one of three branches:

| Branch | Condition | Action |
|--------|-----------|--------|
| **Adopt** | `docs/DESIGN.md` already exists | Keep it. Append only *missing* scaffolding (Proposal Ledger, AUTO markers). Never touches your prose. |
| **Incorporate** | Design content exists elsewhere (`ARCHITECTURE.md`, `docs/20-design/`, `*design*.md`) | Generate the canonical `docs/DESIGN.md` that **links to those files in place** — originals are not moved or edited. |
| **Generate** | No design doc anywhere | Write a seed from the template for you to fill in. |

This is **non-blocking** (`required_on_init: true` means "ensure one exists",
not "refuse to deploy"): init always tries to leave a doc in place and reports
`FAIL` only on a genuine IO error. A freshly generated seed is marked
**unfilled** until you replace its placeholder sections.

## The Proposal Ledger

The table at the bottom of `DESIGN.md`. One row per change, with a status:

| status | meaning |
|--------|---------|
| `proposed` | written up (`docs/10-next/PROPOSAL_<slug>.md`), awaiting review |
| `approved` | signed off by a human; ready to land |
| `landed` | its essence merged into the design doc's sections |
| `implemented` | code shipped; detail file moved to `docs/90-archive/` |
| `superseded` | replaced by a later proposal (row kept for history) |

doc-index reads these statuses and shows open counts on the PWA card
(e.g. `3 proposed · 1 approved awaiting land`).

### Proposal file format (fixed)

Each proposal is one file, `docs/10-next/PROPOSAL_<slug>.md` (moved to
`docs/90-archive/` once implemented), with this fixed header:

```
# Proposal: <title>
> Date: YYYY-MM-DD · Author: <name> · Status: <proposed|approved|landed|implemented|superseded>
```

`templates/PROPOSAL.template.md` is a ready-to-copy starting point.

### Automatic ledger sync

Every scan syncs these files into the ledger (when `proposal_ledger` is on):

- a proposal with no ledger row yet gets one **appended**;
- an existing row's status is **advanced forward** to match its file (never
  backward);
- once a proposal is `landed` or `implemented`, its row's **Approved by** is
  auto-filled from the proposal's **Author** and **Landed** from its **Date**.

The sync is idempotent and safe: it edits only the ledger table, rebuilds each
row from parsed cells, and does nothing if it cannot find or parse the table.
Both `docs/10-next/` and `docs/90-archive/` are scanned, so an already-archived
proposal still backfills correctly.

### Enforcement is advisory, by design

The gate is enforced by **convention + PWA visibility**, not by a pre-commit
hook that blocks commits. A guard that silently refuses to run is its own
failure mode (it stops the pipeline and nobody is told). If you want a harder
check, add an *advisory* lint that warns on un-landed changes — but keep it a
warning, not a block.

## Live config snapshot (optional)

If a project's config drifts from its doc, enable `auto_snapshot`: a
project-specific generator rewrites the `<!-- AUTO:START -->…<!-- AUTO:END -->`
block with live facts (and stamps `last-generated:`). The freshness check goes
red when that stamp ages past `max_age_h`. The generic splice/stamp lives in
doc-index; project-specific content is supplied by your own generator.

## Surfacing on the PWA

Every scan renders a pinned **Design Doc** card at the top of the index, above
the status board, showing a freshness badge (`fresh` / `unfilled` / `stale` /
`missing`) and the open-proposal count. Tap it to open the doc in the markdown
viewer.

## Onboarding an existing project

New projects get the gate by default. For a project already deployed before this
existed, the same preflight runs the next time you `serve.py init` it; nothing is
overwritten (Adopt/Incorporate are non-destructive). Set `design_doc.enabled:
false` to opt a project out entirely.
