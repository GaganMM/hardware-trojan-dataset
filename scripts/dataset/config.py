"""
HTBench Dataset Configuration

Central configuration shared by all dataset modules.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DatasetConfig:
    """
    Global dataset configuration.
    """

    root: Path
    downloads: Path
    metadata: Path
    knowledge: Path
    logs: Path

    @classmethod
    def from_project_root(cls, root: Path) -> "DatasetConfig":
        root = root.resolve()

        return cls(
            root=root,
            downloads=root / "downloads",
            metadata=root / "metadata",
            knowledge=root / "knowledge",
            logs=root / "logs",
        )

    def validate(self) -> None:
        """
        Ensure required project folders exist.
        """

        required = [
            self.downloads,
            self.metadata,
            self.knowledge,
            self.logs,
        ]

        missing = [p for p in required if not p.exists()]

        if missing:
            raise FileNotFoundError(
                "\n".join(str(p) for p in missing)
            )