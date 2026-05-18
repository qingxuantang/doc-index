# Recommended `docs/` Layout — Status-Board Convention

This is the layout doc-index's `sections.promote` was built around. Adopt it
as-is for a new project, or take the pieces you like and adapt.

The goal: when you open the PWA on your phone, **you see at a glance what's
in flight and what's next**. Architecture references and old archives are
present but collapsed by default so they don't fight for attention.

---

## The 6 folders

```
docs/
├── 00-now/         ← currently in flight (usually 1-3 files)
├── 10-next/        ← designed / planned but not started
├── 20-design/      ← architecture, long-term reference
├── 30-guide/       ← API, deployment, how-to
├── 40-business/    ← pitch, mockups, interviews, one-off context
└── 90-archive/     ← completed, superseded, deprecated
```

The 2-digit prefix is for **sort order on disk** — doc-index reads the
folders in alphabetical order when generating sections (before `promote`
reorders them), so this prefix keeps things predictable when you `ls
docs/`.

The 90- prefix on archive is intentionally far from the active folders so
new categories you add later (50-research, 60-experiments, etc.) slot in
naturally without renaming.

---

## What goes where

### `00-now/` — currently in flight

The folder you check first thing in the morning. Should hold the smallest
set of docs that answer "what is the team / I working on right now?"

Good fits:
- The sprint plan for the active sprint
- A live design doc that's actively being implemented
- A version-history / changelog doc that captures the in-progress milestone

Bad fits:
- Backlog items (those belong in `10-next/`)
- Docs you finished last month (move to `90-archive/`)
- Project vision / mission statements (those are `20-design/`)

**Rule of thumb**: if you haven't touched a file in `00-now/` for more
than a week, move it. Empty is better than stale.

### `10-next/` — designed, awaiting sprint

Plans you've written but haven't started. Each file here is something
you've thought through enough to write down but haven't carved out the
time to build.

Good fits:
- PLAN_*.md docs describing a sprint scope
- A feature design doc that's been reviewed but not scheduled
- A roadmap doc

Bad fits:
- Half-finished thoughts (keep those in a private notes app until they're
  worth committing)
- Things that are blocked indefinitely (those probably go to `90-archive/`
  with a "deprecated" prefix)

### `20-design/` — architecture, long-term reference

Docs that describe **how the system works** rather than what's being built.
These age more slowly. They get updated when architecture changes, but
they're not "tasks."

Good fits:
- Architecture docs (system diagrams, module breakdowns)
- Product vision / strategy docs
- Domain model documentation
- Data spec / API contracts

This folder will accumulate over time. That's fine — it should be
collapsed by default in the PWA so it doesn't visually overwhelm the
`now / next` content.

### `30-guide/` — API, deployment, how-to

Operational reference docs. The "here's how to use this thing" content
that other people / future-you needs.

Good fits:
- API reference
- Deployment instructions
- Setup / quickstart guides
- Troubleshooting / runbook docs
- Security audit summaries

### `40-business/` — pitch, mockups, interviews, one-off context

Non-engineering context that's still useful to have indexed and viewable
on mobile.

Good fits:
- Pitch decks (PowerPoint / PDF)
- Customer interview templates
- Sales / GTM mockups
- One-off meeting notes that captured an important decision

This folder protects the engineering folders from getting cluttered with
business content while still keeping the business content indexable.

### `90-archive/` — completed, superseded, deprecated

Where docs go to retire. Keep the history (useful for "why did we decide
X") but get them out of the active layout.

Good fits:
- Sprint plans for completed sprints
- Architecture docs for deprecated versions (e.g. `ARCHITECTURE_V1.md`
  after V2 ships)
- Deprecated plans (e.g. a plan you started writing but pivoted away from)
- Old security audits, past meeting notes

---

## Lifecycle of a doc

A typical sprint-plan doc moves like this:

```
[write plan]
       │
       ▼
   10-next/PLAN_FOO.md
       │  (you decide it's time to start)
       ▼
   00-now/PLAN_FOO.md
       │  (sprint completes)
       ▼
   90-archive/PLAN_FOO.md  (or delete if it added nothing learning-wise)
```

Architecture docs typically live in `20-design/` long-term. They might
briefly visit `00-now/` if they're being actively rewritten, then move
back.

Reference docs in `30-guide/` rarely move — they're updated in place.

---

## `doc-index.yaml` configuration

Pair the folder structure with `sections.promote` + `overrides`:

```yaml
sections:
  auto: true
  promote:
    - "docs/00-now"
    - "docs/10-next"
    - "docs/20-design"
    - "docs/30-guide"
    - "docs/40-business"
    - "docs/90-archive"
  overrides:
    "docs/00-now":
      title: "🟢 NOW — currently in flight"
      color: "#27ae60"
    "docs/10-next":
      title: "🟡 NEXT — designed, awaiting sprint"
      color: "#e67e22"
    "docs/20-design":
      title: "📐 DESIGN — architecture + reference"
      color: "#2d5f8a"
      collapsed: true
    "docs/30-guide":
      title: "📖 GUIDE — API / how-to"
      color: "#8e44ad"
      collapsed: true
    "docs/40-business":
      title: "💼 BUSINESS"
      color: "#95a5a6"
      collapsed: true
    "docs/90-archive":
      title: "📦 ARCHIVE"
      color: "#7f8c8d"
      collapsed: true
```

Result on the PWA:

```
🟢 NOW                       (expanded)
🟡 NEXT                      (expanded)
📐 DESIGN                    (collapsed — click to open)
📖 GUIDE                     (collapsed)
💼 BUSINESS                  (collapsed)
📦 ARCHIVE                   (collapsed)
... your code folders below
```

The green + orange folders compete for attention. The grey ones don't.

---

## When NOT to use this layout

- **Single-purpose repos** with only docs (no source) — the status split
  is overkill; just use `auto: true` and let folders be folders.
- **External-facing OSS docs** (think a library's `docs/` for users) — that
  audience wants topic organization (Getting Started / API / Examples /
  Tutorials), not workflow-state. Use the conventional `docs/` layout
  there instead.
- **Strict documentation systems** with versioning (Sphinx, MkDocs,
  Docusaurus) — those tools manage their own structure. Doc-index pairs
  with them, doesn't replace them.

The status-board layout is for **the project owner's own dashboard view of
the project**. It's most valuable when one person (or a small team) needs
to keep multiple in-flight projects' state quickly accessible from a phone.

---

## Migration tip

If you have an existing flat `docs/` folder with 20+ files, here's a
quick way to migrate:

```bash
cd /path/to/your/project
mkdir -p docs/{00-now,10-next,20-design,30-guide,40-business,90-archive}

# Move tracked files with git so history follows
git mv docs/SPRINT_NOTES.md       docs/00-now/
git mv docs/PLAN_FEATURE_X.md     docs/10-next/
git mv docs/ARCHITECTURE.md       docs/20-design/
git mv docs/API_REFERENCE.md      docs/30-guide/
git mv docs/PITCH_DECK.pdf        docs/40-business/

# Old archive folder → renamed
git mv docs/archive               docs/90-archive

# Untracked files (new files since last commit) just need plain mv
mv docs/NEW_NOTES.md docs/10-next/

# Then update doc-index.yaml with the promote + overrides config above
# Then rescan
python3 scripts/scan.py /path/to/project/doc-index.yaml
```

30 minutes from a flat folder to a status board. Empty `00-now/` is fine
— start there.
