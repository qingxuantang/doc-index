#!/usr/bin/env python3
"""
Doc Index Scanner — Scans a project repo and generates a PWA document index.

Usage:
  python3 scan.py <config.yaml>
  python3 scan.py <config.yaml> --dry-run    # Preview without writing
"""

import json
import os
import re
import subprocess
import sys
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from fnmatch import fnmatch
from pathlib import Path
from urllib.parse import quote

import yaml


# ── Helpers ──────────────────────────────────────────────────────────────────

def validate_hex_color(value, field_name="color"):
    """Validate a CSS hex color string."""
    if not re.match(r'^#[0-9a-fA-F]{6}$', value):
        raise ValueError(f"Invalid {field_name}: {value!r} (must be #RRGGBB hex)")
    return value


def validate_url_base(value):
    """Validate url_base is a safe path prefix."""
    if not re.match(r'^/[a-zA-Z0-9/_.-]*/$', value):
        raise ValueError(
            f"Invalid url_base: {value!r} (must match /path/ with only alphanumeric, /, _, ., -)")
    return value


def load_config(path):
    with open(path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    # Expand ~ in paths
    cfg["repo"]["path"] = str(Path(cfg["repo"]["path"]).expanduser())
    cfg["serve"]["root"] = str(Path(cfg["serve"]["root"]).expanduser())

    # Validate safety-sensitive fields
    validate_hex_color(cfg["project"].get("color", "#2d5f8a"), "project.color")
    validate_url_base(cfg["serve"].get("url_base", "/docs/"))
    for c in cfg.get("sections", {}).get("color_cycle", []):
        validate_hex_color(c, "sections.color_cycle entry")
    for key, ov in cfg.get("sections", {}).get("overrides", {}).items():
        if "color" in ov:
            validate_hex_color(ov["color"], f"sections.overrides.{key}.color")

    return cfg


def should_ignore(name, patterns):
    """Check if a file/folder name matches any ignore pattern."""
    for pat in patterns:
        if fnmatch(name, pat):
            return True
    return False


def get_file_type(ext):
    """Map file extension to display type.

    Doc-index only surfaces *document-style* artifacts that help the reader
    understand the project — never source code. Any extension that is NOT in
    this mapping (and not in the config's `repo.file_types` whitelist) is
    skipped during the scan. So `.py` / `.js` / `.ts` / `.go` / etc. never
    appear on the site even if they happen to live alongside the docs.
    """
    ext = ext.lower().lstrip(".")
    mapping = {
        # PDF + text-style docs
        "pdf":   ("PDF", "pdf"),
        "md":    ("MD",  "pdf"),
        "txt":   ("TXT", "pdf"),
        "html":  ("HTM", "pdf"),
        "htm":   ("HTM", "pdf"),
        "ipynb": ("IPY", "pdf"),
        "yaml":  ("YML", "pdf"),
        "yml":   ("YML", "pdf"),
        # Office
        "xlsx":  ("XLS", "xlsx"),
        "xls":   ("XLS", "xlsx"),
        "csv":   ("CSV", "xlsx"),
        "docx":  ("DOC", "xlsx"),
        "doc":   ("DOC", "xlsx"),
        "pptx":  ("PPT", "pptx"),
        "ppt":   ("PPT", "pptx"),
        # Images / diagrams
        "png":   ("IMG", "png"),
        "jpg":   ("IMG", "png"),
        "jpeg":  ("IMG", "png"),
        "gif":   ("IMG", "png"),
        "webp":  ("IMG", "png"),
        "svg":   ("SVG", "png"),
    }
    return mapping.get(ext, ("FILE", "pdf"))


def git_file_dates(repo_path):
    """Get git add/modify dates for all tracked files."""
    dates = {}
    try:
        # Get last commit date for each file
        result = subprocess.run(
            ["git", "log", "--format=%H %aI", "--name-only", "--diff-filter=ACMR"],
            capture_output=True, text=True, cwd=repo_path, timeout=30
        )
        current_date = None
        current_hash = None
        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue
            parts = line.split(" ", 2)
            if len(parts) >= 2 and len(parts[0]) == 40:
                current_hash = parts[0]
                current_date = parts[1]
            elif current_date and line.strip():
                filepath = line.strip()
                if filepath not in dates:
                    dates[filepath] = {"modified": current_date}
                # Keep looking for the earliest (added) date
                dates.setdefault(filepath, {})
                dates[filepath]["added"] = current_date

        # Second pass: get the first commit for each file (added date)
        result2 = subprocess.run(
            ["git", "log", "--format=%aI", "--name-only", "--diff-filter=A", "--reverse"],
            capture_output=True, text=True, cwd=repo_path, timeout=30
        )
        current_date = None
        for line in result2.stdout.strip().split("\n"):
            if not line.strip():
                continue
            # Try to parse as date
            if re.match(r"\d{4}-\d{2}-\d{2}T", line.strip()):
                current_date = line.strip()
            elif current_date and line.strip():
                filepath = line.strip()
                if filepath in dates:
                    dates[filepath]["added"] = current_date
    except Exception:
        pass
    return dates


def compute_tag(filepath, git_dates, tag_cfg):
    """Determine tag for a file based on git timestamps."""
    if not tag_cfg.get("auto", False):
        return None

    info = git_dates.get(filepath)
    if not info:
        return None

    now = datetime.now(timezone.utc)
    labels = tag_cfg.get("labels", {})
    new_days = tag_cfg.get("new_days", 7)
    updated_days = tag_cfg.get("updated_days", 3)

    # Check "added" date
    added = info.get("added")
    if added:
        try:
            added_dt = datetime.fromisoformat(added)
            if (now - added_dt) < timedelta(days=new_days):
                return labels.get("new", "New")
        except (ValueError, TypeError):
            pass

    # Check "modified" date
    modified = info.get("modified")
    if modified:
        try:
            mod_dt = datetime.fromisoformat(modified)
            if (now - mod_dt) < timedelta(days=updated_days):
                return labels.get("updated", "Updated")
        except (ValueError, TypeError):
            pass

    return None


# ── Scanner ──────────────────────────────────────────────────────────────────

def scan_repo(cfg):
    """Walk repo and build a section tree."""
    repo_path = cfg["repo"]["path"]
    file_types = set(cfg["repo"].get("file_types", []))
    ignore_patterns = cfg["repo"].get("ignore", [])
    section_cfg = cfg.get("sections", {})
    tag_cfg = cfg.get("tags", {})
    overrides = section_cfg.get("overrides", {})
    root_section_name = section_cfg.get("root_files_section", "Project Root")
    colors = section_cfg.get("color_cycle", ["#2d5f8a", "#27ae60", "#e67e22", "#8e44ad", "#95a5a6"])

    # Get git dates for tagging
    git_dates = git_file_dates(repo_path)

    sections = OrderedDict()
    promoted_sections = OrderedDict()  # rendered FIRST, in declaration order
    root_files = []
    color_idx = 0

    repo_resolved = Path(repo_path).resolve()

    # Walk the repo
    for entry in sorted(Path(repo_path).iterdir()):
        if should_ignore(entry.name, ignore_patterns):
            continue

        # Skip symlinks pointing outside the repo
        if entry.is_symlink():
            try:
                if not entry.resolve().is_relative_to(repo_resolved):
                    continue
            except (OSError, ValueError):
                continue

        if entry.is_file():
            ext = entry.suffix.lstrip(".")
            if ext.lower() in file_types:
                rel = str(entry.relative_to(repo_path))
                tag = compute_tag(rel, git_dates, tag_cfg)
                root_files.append({
                    "name": entry.name,
                    "path": rel,
                    "ext": ext,
                    "tag": tag,
                })

        elif entry.is_dir():
            section = scan_folder(
                entry, repo_path, file_types, ignore_patterns,
                git_dates, tag_cfg, overrides
            )
            if section["files"] or section["subsections"]:
                # Determine color
                override_key = str(entry.relative_to(repo_path))
                if override_key in overrides and "color" in overrides[override_key]:
                    section["color"] = overrides[override_key]["color"]
                else:
                    section["color"] = colors[color_idx % len(colors)]
                    color_idx += 1

                # Check for title override
                if override_key in overrides and "title" in overrides[override_key]:
                    section["title"] = overrides[override_key]["title"]

                # Check for collapsed override
                if override_key in overrides and overrides[override_key].get("collapsed"):
                    section["collapsed"] = True

                # Promote selected subsections to top-level sections.
                # Promoted sections are rendered FIRST, in the order they appear
                # in `sections.promote`. Useful for status folders (NOW / NEXT
                # / etc.) that should be the most visible thing on the page.
                promote_list = list(section_cfg.get("promote", []))
                promote_set = set(promote_list)
                if promote_set:
                    # Build a per-promoted-path order index for stable sorting
                    order_index = {p: i for i, p in enumerate(promote_list)}
                    keys_to_promote = [
                        sub_key for sub_key in list(section["subsections"].keys())
                        if f"{override_key}/{sub_key}" in promote_set
                    ]
                    # Sort by declared order in `sections.promote`
                    keys_to_promote.sort(
                        key=lambda k: order_index.get(f"{override_key}/{k}", 999)
                    )
                    for sub_key in keys_to_promote:
                        sub = section["subsections"].pop(sub_key)
                        sub_override_key = f"{override_key}/{sub_key}"
                        if sub_override_key in overrides:
                            ov = overrides[sub_override_key]
                            if "color" in ov:
                                sub["color"] = ov["color"]
                            else:
                                sub["color"] = colors[color_idx % len(colors)]
                                color_idx += 1
                            if "title" in ov:
                                sub["title"] = ov["title"]
                            if ov.get("collapsed"):
                                sub["collapsed"] = True
                        else:
                            sub["color"] = colors[color_idx % len(colors)]
                            color_idx += 1
                        promoted_sections[f"{entry.name}__{sub_key}"] = sub

                if section["files"] or section["subsections"]:
                    sections[entry.name] = section

    # Add root files as a section if any
    if root_files:
        sections["__root__"] = {
            "title": root_section_name,
            "color": colors[color_idx % len(colors)] if colors else "#95a5a6",
            "files": root_files,
            "subsections": OrderedDict(),
            "collapsed": False,
        }

    # Promoted sections are rendered first
    final = OrderedDict()
    for k, v in promoted_sections.items():
        final[k] = v
    for k, v in sections.items():
        final[k] = v
    return final


def scan_folder(folder, repo_root, file_types, ignore_patterns, git_dates, tag_cfg, overrides):
    """Scan a folder into a section dict."""
    files = []
    subsections = OrderedDict()
    repo_resolved = Path(repo_root).resolve()

    for entry in sorted(folder.iterdir()):
        if should_ignore(entry.name, ignore_patterns):
            continue

        # Skip symlinks pointing outside the repo
        if entry.is_symlink():
            try:
                if not entry.resolve().is_relative_to(repo_resolved):
                    continue
            except (OSError, ValueError):
                continue

        if entry.is_file():
            ext = entry.suffix.lstrip(".")
            if ext.lower() in file_types:
                rel = str(entry.relative_to(repo_root))
                tag = compute_tag(rel, git_dates, tag_cfg)
                files.append({
                    "name": entry.name,
                    "path": rel,
                    "ext": ext,
                    "tag": tag,
                })

        elif entry.is_dir():
            sub = scan_folder(entry, repo_root, file_types, ignore_patterns, git_dates, tag_cfg, overrides)
            if sub["files"] or sub["subsections"]:
                subsections[entry.name] = sub

    return {
        "title": folder.name,
        "files": files,
        "subsections": subsections,
        "collapsed": False,
    }


# ── HTML Renderer ────────────────────────────────────────────────────────────

def render_file_item(f, url_base):
    """Render a single file-item <a> tag."""
    display_label, icon_class = get_file_type(f["ext"])
    encoded_path = quote(f["path"], safe="/")
    href = f'docs/{encoded_path}'

    tag_html = ""
    if f.get("tag"):
        tag_html = f'<span class="file-tag latest">{esc(f["tag"])}</span>'

    display_name = f["name"]
    # Strip common extensions for cleaner display
    for ext in [".pdf", ".md", ".html", ".htm"]:
        if display_name.lower().endswith(ext):
            display_name = display_name[:-len(ext)]
            break

    return (
        f'<a class="file-item" href="{href}" target="_blank">'
        f'<span class="file-icon {icon_class}">{display_label}</span>'
        f'<span class="file-name">{esc(display_name)}</span>'
        f'{tag_html}'
        f'</a>'
    )


def render_section(name, section, url_base, indent=0):
    """Render a section block."""
    pad = "    " * indent
    title = section.get("title", name)
    color = section.get("color", "#2d5f8a")
    collapsed = section.get("collapsed", False)
    arrow = "▶" if collapsed else "▼"
    body_class = ' class="section-body collapsed"' if collapsed else ' class="section-body"'

    lines = [
        f'{pad}<div class="section" style="--section-color: {color}">',
        f'{pad}    <div class="section-title" style="background: {color}" onclick="toggle(this)">',
        f'{pad}        {esc(title)}',
        f'{pad}        <span class="toggle">{arrow}</span>',
        f'{pad}    </div>',
        f'{pad}    <div{body_class}>',
    ]

    # Render files at this level
    for f in section.get("files", []):
        lines.append(f'{pad}        {render_file_item(f, url_base)}')

    # Render subsections
    for sub_name, sub in section.get("subsections", {}).items():
        sub_title = sub.get("title", sub_name)
        lines.append(f'{pad}        <div class="subsection">')
        lines.append(f'{pad}            <div class="subsection-title">{esc(sub_title)}</div>')

        for f in sub.get("files", []):
            lines.append(f'{pad}            {render_file_item(f, url_base)}')

        # Nested subsections (3rd level) — flatten into the parent subsection
        for nested_name, nested in sub.get("subsections", {}).items():
            nested_title = nested.get("title", nested_name)
            lines.append(f'{pad}            <div class="subsection-title" style="font-size:12px;color:#888">{esc(nested_title)}</div>')
            for f in nested.get("files", []):
                lines.append(f'{pad}            {render_file_item(f, url_base)}')

        lines.append(f'{pad}        </div>')

    lines.append(f'{pad}    </div>')
    lines.append(f'{pad}</div>')
    return "\n".join(lines)


def esc(text):
    """Escape HTML special chars."""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def render_quick_links(links):
    """Render the quick links section."""
    if not links:
        return ""
    items = []
    for link in links:
        icon = link.get("icon", "🔗")
        label = link.get("label", "Link")
        url = link.get("url", "#")
        items.append(
            f'    <a href="{esc(url)}" target="_blank">'
            f'<span class="ql-icon">{icon}</span>'
            f'<span class="ql-label">{esc(label)}</span>'
            f'<span class="ql-arrow">›</span>'
            f'</a>'
        )
    return (
        '<div class="quick-links">\n'
        '    <div class="ql-title">Quick Links</div>\n'
        + "\n".join(items) + "\n"
        '</div>'
    )


def render_index(cfg, sections):
    """Render complete index.html."""
    p = cfg["project"]
    color = p.get("color", "#2d5f8a")
    lang = p.get("lang", "en")
    name = p.get("name", "Document Index")
    short_name = p.get("short_name", name[:10])
    subtitle = p.get("subtitle", "Document Index")
    url_base = cfg["serve"].get("url_base", "/")

    # Quick links
    quick_links_html = render_quick_links(cfg.get("quick_links", []))

    # Sections
    section_blocks = []
    for sec_name, sec in sections.items():
        section_blocks.append(render_section(sec_name, sec, url_base))

    sections_html = "\n\n".join(section_blocks)

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Derive gradient colors
    import colorsys
    try:
        # Parse hex color
        c = color.lstrip("#")
        r, g, b = int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
        # Lighter variant for gradient
        h, l, s = colorsys.rgb_to_hls(r/255, g/255, b/255)
        l2 = min(1.0, l * 1.3)
        r2, g2, b2 = colorsys.hls_to_rgb(h, l2, s)
        color2 = f"#{int(r2*255):02x}{int(g2*255):02x}{int(b2*255):02x}"
    except Exception:
        color2 = color

    # Load the HTML template
    template_dir = Path(__file__).parent.parent / "templates"
    template_path = template_dir / "index.html"
    with open(template_path, "r", encoding="utf-8") as f:
        template = f.read()

    # Replace placeholders
    html = template.replace("{{LANG}}", lang)
    html = html.replace("{{PROJECT_NAME}}", esc(name))
    html = html.replace("{{SHORT_NAME}}", esc(short_name))
    html = html.replace("{{SUBTITLE}}", esc(subtitle))
    html = html.replace("{{COLOR}}", color)
    html = html.replace("{{COLOR2}}", color2)
    html = html.replace("{{QUICK_LINKS}}", quick_links_html)
    html = html.replace("{{SECTIONS}}", sections_html)
    html = html.replace("{{UPDATED}}", now_str)
    html = html.replace("{{URL_BASE}}", url_base)

    return html


def render_manifest(cfg):
    """Generate manifest.json content."""
    p = cfg["project"]
    return json.dumps({
        "name": p.get("name", "Document Index"),
        "short_name": p.get("short_name", "Docs"),
        "description": p.get("description", "Project document index"),
        "start_url": cfg["serve"].get("url_base", "/"),
        "scope": cfg["serve"].get("url_base", "/"),
        "display": "standalone",
        "background_color": p.get("color", "#1a3a5c"),
        "theme_color": p.get("color", "#1a3a5c"),
        "orientation": "any",
        "icons": [
            {"src": "icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "icon-512.png", "sizes": "512x512", "type": "image/png"},
        ]
    }, ensure_ascii=False, indent=2)


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 scan.py <config.yaml> [--dry-run]")
        sys.exit(1)

    config_path = sys.argv[1]
    dry_run = "--dry-run" in sys.argv

    cfg = load_config(config_path)
    repo_path = cfg["repo"]["path"]
    serve_root = cfg["serve"]["root"]

    if not Path(repo_path).is_dir():
        print(f"ERROR: Repo path not found: {repo_path}")
        sys.exit(1)

    print(f"Scanning: {repo_path}")
    sections = scan_repo(cfg)

    # Count files
    total_files = 0
    for sec in sections.values():
        total_files += len(sec.get("files", []))
        for sub in sec.get("subsections", {}).values():
            total_files += len(sub.get("files", []))
            for nested in sub.get("subsections", {}).values():
                total_files += len(nested.get("files", []))

    print(f"Found: {len(sections)} sections, {total_files} files")

    if dry_run:
        print("\n[DRY RUN] Would generate:")
        print(f"  {serve_root}/index.html")
        print(f"  {serve_root}/manifest.json")
        for sec_name, sec in sections.items():
            title = sec.get("title", sec_name)
            n = len(sec.get("files", []))
            nsub = len(sec.get("subsections", {}))
            print(f"  Section: {title} ({n} files, {nsub} subsections)")
        return

    # Generate HTML
    html = render_index(cfg, sections)
    manifest = render_manifest(cfg)

    # Write output
    out_dir = Path(serve_root)
    out_dir.mkdir(parents=True, exist_ok=True)

    index_path = out_dir / "index.html"
    manifest_path = out_dir / "manifest.json"

    with open(index_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Written: {index_path}")

    with open(manifest_path, "w", encoding="utf-8") as f:
        f.write(manifest)
    print(f"Written: {manifest_path}")

    # Copy service worker
    template_dir = Path(__file__).parent.parent / "templates"
    sw_src = template_dir / "sw.js"
    sw_dst = out_dir / "sw.js"
    if sw_src.exists():
        import shutil
        shutil.copy2(sw_src, sw_dst)
        print(f"Copied: {sw_dst}")

    # Copy viewers
    for viewer in ["viewer.html", "md-viewer.html", "yaml-viewer.html"]:
        src = template_dir / viewer
        dst = out_dir / viewer
        if src.exists():
            import shutil
            shutil.copy2(src, dst)
            print(f"Copied: {dst}")

    # Check if docs symlink exists
    docs_link = out_dir / "docs"
    if not docs_link.exists():
        print(f"\nWARNING: {docs_link} does not exist.")
        print(f"  Run: ln -s {repo_path} {docs_link}")
        print(f"  Or run: python3 serve.py init {config_path}")

    print(f"\nDone. Updated at {datetime.now().strftime('%Y-%m-%d %H:%M')}")


if __name__ == "__main__":
    main()
