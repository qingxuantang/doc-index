# Proposal: serve.mode — local / internal-network serving as a first-class option

> Date: 2026-10-27 · Author: maintainer · Status: implemented

## Problem

doc-index's stock flow assumes one deployment target: **nginx + a URL path
prefix + basic auth + a public domain**. `serve.py init` ends by printing an
nginx server block, and the design assumes the generated site is reached at
`https://domain/url_base/`.

But a very common need is simpler: **run a local HTTP server on this machine
(or the LAN) and browse the index from a phone or the same box** — no nginx, no
public domain, no auth. Forcing that need through the nginx-shaped flow requires
three independent workarounds, all reproducible in the current code:

1. **`url_base` won't accept a bare `/`.** `scan.py:validate_url_base` uses
   `^/[a-zA-Z0-9/_.-]*/$`, which requires a leading *and* trailing slash — the
   shortest legal value is `//`. A root-path local serve logically wants
   `url_base: "/"` (no prefix) but has to cheat with `"//"`. (Confirmed by
   dogfooding this repo on itself: `init` printed `Site: //` and `location //`.)

2. **The `docs/` href prefix is hardcoded.** `scan.py:render_file_item` emits
   `href="docs/{path}"`, and `index.html` rebuilds the click target as
   `location.origin + url_base + href`. If `url_base` itself contains a `docs`
   segment you get `docs/docs/` → 404. The `docs/` layer corresponds to the
   `serve.root/docs` symlink, which a pure-local root serve does not inherently
   need.

3. **`serve.root/docs` is a symlink to the repo's absolute path.**
   `serve.py:create_docs_symlink` does `os.symlink(repo_path, …)`. When the site
   is generated in one filesystem/namespace (e.g. a container at
   `/workspace/...`) and served from another (e.g. Windows WSL), the absolute
   target does not resolve → broken links. On the *same* host/filesystem the
   symlink resolves fine, so this bites only across namespaces.

The result: "just serve it locally" is possible but only via
`url_base:"//"` + a symlink that may not travel + (when it doesn't) a manual
`rsync` copy that has to be re-run after every scan. That manual re-sync is an
ongoing operational burden — the copy does not follow the repo the way the
symlink does.

## Proposal

Add a `serve.mode: local | nginx` switch and make local/internal-network
serving a first-class, opt-in target. **Default stays `nginx`** so every
existing config (none of which set `mode`) keeps its current behavior — a
default flip would be a breaking change for deployed sites.

Three root-cause fixes (not workarounds):

1. **Widen `validate_url_base` to accept a bare `/`.** New regex
   `^/([A-Za-z0-9/_.-]*/)?$` — a strict superset: `/`, `/x/`, `/x/y/` all pass;
   `/x` (missing trailing slash) still rejected. Every existing value stays
   valid. `local` mode defaults `url_base: "/"`.

2. **Make the content mount strategy mode-aware** via `serve.content:
   symlink | copy` (defaulted from mode: nginx→symlink, local→copy).
   - `symlink` = today's behavior (auto-follows the repo).
   - `copy` = a real copy of the repo into `serve.root/docs/`, so the site is
     portable across filesystems/namespaces. The `href="docs/…"` prefix is kept
     unchanged, so with `url_base:"/"` the final path is `/docs/…` resolving to
     real files — **no template or viewer changes, no `docs/docs/` risk.**
   - The copy **excludes `repo.ignore`** (`.git`, `.env`, `.venv`,
     `__pycache__`, …), so secrets are not materialized into `serve.root`.

3. **Auto-sync the copy at the end of every `scan.py`** in local/copy mode, so
   `serve.root/docs/` is always current with no manual `rsync` step.

Plus one new entry point:

4. **`serve.py serve <config> [--host H] [--port P]`** — a thin `http.server`
   wrapper rooted at `serve.root`. Defaults `bind_host: 127.0.0.1`,
   `bind_port: 8099`. Prints the access URL and a prominent security banner:
   local mode has no auth; `0.0.0.0` exposes `serve.root` to the whole LAN;
   `http.server` is dev-grade (single-threaded, no TLS). Sensitive content stays
   on `127.0.0.1` or goes through nginx+auth.

And `serve.py init` branches on mode: `local` skips the nginx check, htpasswd,
and server-block print, materializes the copy, runs the first scan, and prints
the local access URL; `nginx` is unchanged byte-for-byte.

## Notes

- **Scope held deliberately:** the `docs/` prefix layer is *kept*. Removing it
  (relative hrefs, no `docs/` layer) is cleaner but touches `render_file_item`,
  `index.html`'s click JS, and four viewers' path assumptions — a larger,
  regression-prone change. Filed as a possible future simplification, not part
  of this proposal.
- **Not doing:** auth/TLS for `http.server` (if you need security, use nginx —
  that is local mode's design boundary).
- **Related, decoupled:** a friendlier error when PyYAML is missing (plus a
  vendoring note) — a separate small change, not bundled here.
- **Blast radius:** `scan.py` (regex widen + mode-gated end-of-scan branch),
  `serve.py` (new `materialize_docs` / `cmd_serve`, mode-branched `cmd_init`
  with the nginx path preserved verbatim), `config.example.yaml` + README. The
  `templates/` are untouched. Regression check: run `init`/`scan` with an
  existing nginx config and diff the generated output — it must not change.
