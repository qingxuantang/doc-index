"""
Base adapter for external document sources.

To create a new adapter:
1. Create a new .py file in adapters/
2. Subclass BaseAdapter
3. Implement fetch()
4. Reference the adapter name in config.yaml external_sources
"""

from abc import ABC, abstractmethod
from pathlib import Path


class BaseAdapter(ABC):
    """Base class for external document source adapters."""

    def __init__(self, name: str, config: dict):
        self.name = name
        self.config = config

    @abstractmethod
    def fetch(self, target_dir: str) -> list:
        """
        Fetch documents from external source and save to target_dir.

        Returns a list of dicts:
        [
            {
                "filename": "document.pdf",
                "title": "Human-readable title",
                "is_new": True,          # New since last fetch
                "is_updated": False,      # Updated since last fetch
            }
        ]
        """
        pass

    def get_state_file(self, target_dir: str) -> Path:
        """Path to adapter state file for tracking changes."""
        return Path(target_dir) / f".{self.name}_state.json"
