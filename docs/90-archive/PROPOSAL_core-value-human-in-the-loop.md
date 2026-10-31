# Proposal: Foreground the human-in-the-loop proposal ledger as doc-index's core value

> Date: 2026-10-31 · Author: maintainer · Status: implemented

## Problem

doc-index's public description sold it as "a document index PWA" — a viewer. That
undersells what actually makes it different. doc-index is the reference
implementation of its own [Design Doc Gate](../../DESIGN_DOC_CONVENTION.md): **every
AI-made optimization or upgrade is written up as a proposal** and moves
Proposal → Approved → Landed → Implemented before it ships. That governance loop —
keeping a human in the loop over what an AI changes — is the main value, and the
old description never said so. A reader scanning the tagline could not tell this
apart from any other folder-to-HTML doc browser.

## Proposal

Reposition the project's description to lead with the governance loop, consistently
across the docs that carry the description:

- **`SKILL.md`** / **`README.md`** frontmatter `description`: lead with "human-friendly
  documentation index" + "every AI optimization and upgrade a logged proposal
  (Proposal → Approved → Landed → Implemented), so development stays
  human-in-the-loop". Keep the auto-invoke trigger block unchanged.
- **`README.md`** tagline and **`README_CN.md`** intro: same message, inline
  "Markdown / Office / PDF open inline".
- **`docs/DESIGN.md`** "What this project is": state the proposal-logged,
  human-in-the-loop loop as the **core value** up front.
- The external platform listing (WorkBuddy) description is updated to match the
  approved copy.

Messaging only — no code or behavior changes.

## Notes

- English copy mirrors the approved Chinese description.
- Alternative considered: leave the description as-is and only change the platform
  listing. Rejected — the repo's own docs should be the source of truth for how the
  project is described, not diverge from the listing.
- Scope of the git push for this change: only the description-bearing docs above
  plus this proposal and the ledger row.
