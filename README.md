---
name: doc-index
description: |
  Generate or refresh a project document index PWA. Scans a project repo's filesystem (including untracked files) and produces a mobile-friendly doc browser served via nginx with basic auth (on by default), installable as a PWA. Config-driven — drop into any project on any server.

  **AUTO-INVOKE this skill (do NOT run scan.py directly via Bash) when the user says any of**:
  - 中文触发：更新索引 / 更新文档索引 / 刷新文档站 / 扫一下文档 / 重新扫文档 / 把 X 加到索引 / X 怎么没显示在网页上 / 把这个文档放到索引 / 索引文档更新 / 同步索引 / 文档站再扫一遍 / 索引怎么没看到
  - English triggers: refresh doc index, rebuild doc site, scan project docs, update doc index, regenerate documentation site, why is X missing from the doc site, sync the doc PWA, rescan docs
  - Setup triggers: set up doc index for X project / new project needs a doc PWA

  Also use when adding a NEW project's doc-index config from scratch, or troubleshooting why a file isn't showing up on the existing PWA.
---

# Doc Index — Project Document Index Generator

Generate / maintain a PWA document index website from any project repo's folder structure.

[English README](./README.md) · [简体中文](./README_CN.md) · MIT licensed

> **This is a Claude Code skill.** Drop the repo into `~/.claude/skills/doc-index/` and Claude Code will auto-invoke it whenever you say "更新索引", "refresh doc index", or "set up doc index for X project". Or use the underlying scripts as a plain Python CLI — no Claude Code required.

## Install as a Claude Code skill

```bash
# One-time install
git clone https://github.com/qingxuantang/doc-index.git ~/.claude/skills/doc-index

# Then in Claude Code (or any agent that loads Claude Code-style skills):
#   "set up doc index for my project at ~/projects/foo"
#   "更新索引"           # refresh the most recently active project
#   "把这个加到索引"      # add a doc, then re-scan
```

The skill's [SKILL.md](./SKILL.md) declares auto-invoke triggers so the agent picks it up without you having to remember the script paths.

## Install as a standalone CLI (no Claude Code)

```bash
git clone https://github.com/qingxuantang/doc-index.git
cd doc-index
cp config.example.yaml /path/to/your-project/doc-index.yaml
# edit the yaml
python3 scripts/serve.py init /path/to/your-project/doc-index.yaml
```

Works identically — the Claude Code wrapping is just an auto-invoke convenience, not a functional dependency.

## Project Registry (local)

When you set up a new project's doc-index on this server, add it to the table below. This is your local routing hint — when a user just says "更新索引" without naming a project, resolve via this table.

| Project | Config YAML | Scan command | Public URL | Cron |
|---|---|---|---|---|
| _(none yet — add your first project here after running `serve.py init`)_ | | | | |

If the user names a project that isn't here, ask whether to set up a new doc-index config for it (see Setup section).

## Architecture

- **Config**: `config.yaml` in the project or skill directory — all project-specific settings
- **Scripts**: `scripts/scan.py` (generate index), `scripts/serve.py` (deploy + auth), `scripts/icon.py` (PWA icons)
- **Templates**: HTML/JS/CSS templates in `templates/` (pure `{{PLACEHOLDER}}` style)
- **Output**: Static files served by nginx behind basic auth (on by default), installable as PWA

## Setup (First Time)

### Step 1: Create config.yaml

Copy `config.example.yaml` and customize for the project. **Set `serve.domain` to the public hostname** (required for the full nginx server block):

```bash
cp config.example.yaml /path/to/project/doc-index.yaml
# Edit: project.name, repo.path, serve.root, serve.url_base, serve.domain
```

### Step 2: Initialize deployment

```bash
python3 scripts/serve.py init /path/to/project/doc-index.yaml
```

This will:
1. Check nginx is running
2. Verify the repo exists
3. Create the serve directory
4. Symlink serve dir → repo
5. Generate PWA icons (from `project.color` + `project.short_name`)
6. Copy viewer templates (PDF.js, Markdown viewer, YAML viewer)
7. **Generate basic-auth htpasswd** + persist password back into config.yaml
8. Set up cron if `triggers.cron` configured
9. Run initial scan to generate `index.html`
10. Print the **complete nginx server block** (server + ssl placeholder + auth + location + http→https redirect + certbot hint)

The credentials are printed once — copy them somewhere safe.

### Step 3: Wire up nginx

Save the printed server block to `/etc/nginx/conf.d/<project>.conf`, then:

```bash
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d docs.example.com     # SSL
```

### Step 4: Verify + register

Open the configured URL on your phone/tablet (login with auth credentials), install as PWA.
Add a row to the **Project Registry** above so this skill can route `更新索引` to it later.

## Daily Usage

### Manual update
```bash
python3 scripts/scan.py /path/to/project/doc-index.yaml
```

### Check what changed
The scan script prints a summary of new/updated/removed files.

### Rotate auth password
```bash
python3 scripts/serve.py reset-auth /path/to/project/doc-index.yaml
```
Regenerates htpasswd + writes new password to config. Reload nginx after.

### Print just the nginx block
```bash
python3 scripts/serve.py nginx /path/to/project/doc-index.yaml
```

### Status check
```bash
python3 scripts/serve.py status /path/to/project/doc-index.yaml
```

### Cron (automatic)
If `triggers.cron` is set, `serve.py init` adds it to crontab. Logs go to `<serve.root>/scan.log`.

### Git hook (optional)
```bash
#!/bin/bash
# .git/hooks/post-merge
python3 /path/to/doc-index/scripts/scan.py /path/to/project/doc-index.yaml
```

## What gets indexed (doc-only)

Doc-index is **deliberately a documentation browser, not a code browser**. Its job: help someone glance at a project and understand the plan / spec / diagrams / notes — without ever opening source code.

The indexer is a positive whitelist driven by `repo.file_types` in config:

| Category | Default-included extensions |
|---|---|
| Text docs | `pdf`, `md`, `txt`, `html`, `ipynb`, `yaml`, `yml` |
| Office | `xlsx`, `xls`, `csv`, `docx`, `doc`, `pptx`, `ppt` |
| Images / diagrams | `png`, `jpg`, `jpeg`, `gif`, `webp`, **`svg`** |

Anything outside this list — `.py`, `.js`, `.ts`, `.go`, `.rs`, `.toml`, `.lock`, dotfiles, etc. — is silently skipped during scan. If you need a project-specific carve-out, edit `repo.file_types` in that project's `doc-index.yaml`.

The viewers handle each type appropriately:
- PDF / images / SVG → inline preview
- MD → built-in markdown viewer
- YAML → built-in YAML viewer (browsable, filterable)
- IPYNB → opened in new tab (browser renders)
- Office (xlsx/docx/pptx) → routed through Microsoft Office web viewer

## Config Reference

See `config.example.yaml` for all fields. Key fields:

- `project.*` — name, color, language, subtitle
- `repo.path` — path to the project repo
- `repo.file_types` / `repo.ignore` — what to index, what to skip
- `serve.root` / `serve.url_base` — where the static site lives + URL prefix
- `serve.domain` — public hostname (required for full server block)
- `serve.auth.*` — basic-auth on by default; user `admin`, auto-generated password
- `quick_links` — top-of-page shortcuts
- `sections.*` — auto-generate from folders + optional per-folder overrides
- `tags.*` — auto-tag new/updated files based on git timestamps
- `triggers.cron` — cron schedule (5-field expression)
- `external_sources` — adapter configs for pulling from APIs

## Adapters (External Sources)

Pull documents from external APIs by adding an adapter in `adapters/`:

```yaml
external_sources:
  - name: "GitHub Releases"
    adapter: "github_releases"
    config:
      repo: "owner/repo"
      token_env: "GITHUB_TOKEN"
      download_to: "releases/"
```

Reference implementation: `adapters/github_releases.py`.

## Critical Rules

- **Doc-only filter is core to the product** — adding source-code extensions to `repo.file_types` is almost always a misuse. Use a separate tool for code search.
- Config drives everything — never hardcode project-specific values in templates or scripts
- scan.py is idempotent — safe to run repeatedly
- serve.py init is non-destructive — checks before overwriting
- All paths in HTML are URL-encoded for non-ASCII filenames
- Basic auth is ON by default; disable with `serve.auth.enabled: false` only if you have another protection layer

## Dependencies

- Python 3.8+
- PyYAML (`pip install pyyaml`)
- nginx (running, with permission to read serve root)
- Either `htpasswd` (apache2-utils) OR `openssl` — needed for auth setup
- Pillow (optional, for `icon.py` PWA icon generation)
