"""
GitHub Releases Adapter — Downloads release assets from a GitHub repo.

Config example in config.yaml:
  external_sources:
    - name: "releases"
      adapter: "github_releases"
      config:
        repo: "owner/repo"
        token_env: "GITHUB_TOKEN"    # Optional: env var name for auth token
        download_to: "releases/"     # Subfolder in repo to save assets
        include_prerelease: false
        max_releases: 5
"""

import json
import os
import re
from pathlib import Path
from urllib.request import Request, urlopen

from .base import BaseAdapter

_REPO_PATTERN = re.compile(r'^[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+$')


class GitHubReleasesAdapter(BaseAdapter):

    def fetch(self, target_dir: str) -> list:
        repo = self.config["repo"]
        if not _REPO_PATTERN.match(repo):
            raise ValueError(f"Invalid repo format: {repo!r} (expected 'owner/repo')")
        token = os.environ.get(self.config.get("token_env", ""), "")
        download_to = self.config.get("download_to", "releases")
        include_pre = self.config.get("include_prerelease", False)
        max_releases = self.config.get("max_releases", 5)

        save_dir = Path(target_dir) / download_to
        save_dir.mkdir(parents=True, exist_ok=True)

        # Load previous state
        state_file = self.get_state_file(target_dir)
        prev_state = {}
        if state_file.exists():
            with open(state_file) as f:
                prev_state = json.load(f)

        # Fetch releases from GitHub API
        url = f"https://api.github.com/repos/{repo}/releases?per_page={max_releases}"
        headers = {"Accept": "application/vnd.github.v3+json"}
        if token:
            headers["Authorization"] = f"token {token}"

        req = Request(url, headers=headers)
        with urlopen(req, timeout=30) as resp:
            releases = json.loads(resp.read())

        results = []
        new_state = {}

        for release in releases:
            if release.get("prerelease") and not include_pre:
                continue

            for asset in release.get("assets", []):
                filename = asset["name"]
                download_url = asset["browser_download_url"]
                updated_at = asset["updated_at"]
                new_state[filename] = updated_at

                filepath = save_dir / filename
                is_new = filename not in prev_state
                is_updated = not is_new and prev_state.get(filename) != updated_at

                if is_new or is_updated or not filepath.exists():
                    # Download
                    req = Request(download_url, headers=headers)
                    with urlopen(req, timeout=120) as resp:
                        with open(filepath, "wb") as f:
                            f.write(resp.read())

                results.append({
                    "filename": str(Path(download_to) / filename),
                    "title": f"{release['tag_name']} — {filename}",
                    "is_new": is_new,
                    "is_updated": is_updated,
                })

        # Save state
        with open(state_file, "w") as f:
            json.dump(new_state, f, indent=2)

        return results
