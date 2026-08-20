"""
HTBench Inventory Builder

Scans all downloaded repositories and generates an RTL inventory.

Author: HTBench
"""

from __future__ import annotations

import os
import logging
from dataclasses import dataclass
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict

import pandas as pd

from scripts.dataset.config import DatasetConfig

# ---------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------

logger = logging.getLogger("HTBench.Inventory")

if not logger.handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s | %(message)s"
    )


# ---------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------

RTL_EXTENSIONS = {
    ".v",
    ".sv",
}

IGNORE_DIRS = {
    ".git",
    ".github",
    "__pycache__",
    ".venv",
    "venv",
    "env",
    "docs",
    "doc",
    "images",
    "image",
    "img",
    "png",
    "jpg",
    "jpeg",
    "pdf",
    "build",
    "out",
    "obj",
    "bin",
}


# ---------------------------------------------------------------------
# RTL Record
# ---------------------------------------------------------------------

@dataclass
class RTLRecord:

    repository: str
    file_name: str
    module_name: str
    extension: str
    relative_path: str
    language: str
    size_kb: float


# ---------------------------------------------------------------------
# Inventory Scanner
# ---------------------------------------------------------------------

class InventoryScanner:

    def __init__(self, config: DatasetConfig):

        self.config = config

    # -------------------------------------------------------------

    def discover_repositories(self) -> List[Path]:
        """
        Return every repository under downloads/.
        """

        repos = []

        for item in sorted(self.config.downloads.iterdir()):

            if item.is_dir():

                repos.append(item)

        logger.info(
            "Repositories discovered : %d",
            len(repos)
        )

        return repos

    # -------------------------------------------------------------

    @staticmethod
    def language_from_suffix(suffix: str) -> str:

        suffix = suffix.lower()

        if suffix == ".sv":
            return "SystemVerilog"

        return "Verilog"

    # -------------------------------------------------------------

    def scan_repository(
        self,
        repository: Path
    ) -> List[RTLRecord]:
        """
        Scan a single repository.

        Returns
        -------
        list[RTLRecord]
        """

        logger.info("Scanning %s", repository.name)

        records: List[RTLRecord] = []

        for root, dirs, files in os.walk(repository):

            # Skip ignored folders
            dirs[:] = [
                d
                for d in dirs
                if d not in IGNORE_DIRS
            ]

            root_path = Path(root)

            for file in files:

                suffix = Path(file).suffix.lower()

                if suffix not in RTL_EXTENSIONS:
                    continue

                full_path = root_path / file

                try:

                    relative_path = (
                        full_path
                        .relative_to(repository)
                        .as_posix()
                    )

                    size_kb = round(
                        full_path.stat().st_size / 1024,
                        2
                    )

                    record = RTLRecord(

                        repository=repository.name,

                        file_name=file,

                        module_name=full_path.stem,

                        extension=suffix,

                        relative_path=relative_path,

                        language=self.language_from_suffix(
                            suffix
                        ),

                        size_kb=size_kb,
                    )

                    records.append(record)

                except Exception as exc:

                    logger.warning(
                        "Skipping %s (%s)",
                        full_path,
                        exc
                    )

        logger.info(
            "%-35s %6d RTL",
            repository.name,
            len(records)
        )

        return records
    
# ---------------------------------------------------------------------
# Parallel Repository Scan
# ---------------------------------------------------------------------

    def scan_all_repositories(
        self,
        repositories: List[Path],
    ) -> List[RTLRecord]:
        """
        Scan all repositories in parallel.
        """

        all_records: List[RTLRecord] = []

        workers = min(16, os.cpu_count() or 4)

        logger.info("")
        logger.info("=" * 60)
        logger.info("Starting Parallel Repository Scan")
        logger.info("Workers : %d", workers)
        logger.info("=" * 60)

        with ThreadPoolExecutor(max_workers=workers) as executor:

            future_map = {
                executor.submit(
                    self.scan_repository,
                    repo
                ): repo
                for repo in repositories
            }

            completed = 0

            for future in as_completed(future_map):

                repo = future_map[future]

                completed += 1

                try:

                    repo_records = future.result()

                    all_records.extend(repo_records)

                    logger.info(
                        "[%3d/%3d] %-35s %6d RTL",
                        completed,
                        len(repositories),
                        repo.name,
                        len(repo_records),
                    )

                except Exception as exc:

                    logger.error(
                        "Repository failed : %s (%s)",
                        repo.name,
                        exc,
                    )

        logger.info("")
        logger.info(
            "Total RTL discovered : %d",
            len(all_records),
        )

        return all_records


# ---------------------------------------------------------------------
# DataFrame Conversion
# ---------------------------------------------------------------------

    @staticmethod
    def records_to_dataframe(
        records: List[RTLRecord],
    ) -> pd.DataFrame:
        """
        Convert RTLRecord objects into a DataFrame.
        """

        rows: List[Dict] = []

        for record in records:

            rows.append({

                "repository": record.repository,

                "file_name": record.file_name,

                "module_name": record.module_name,

                "extension": record.extension,

                "relative_path": record.relative_path,

                "language": record.language,

                "size_kb": record.size_kb,
            })

        df = pd.DataFrame(rows)

        return df


# ---------------------------------------------------------------------
# RTL ID Generator
# ---------------------------------------------------------------------

    @staticmethod
    def assign_ids(
        df: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        Add sequential RTL IDs.
        """

        rtl_ids = []

        for index in range(len(df)):

            rtl_ids.append(
                f"RTL{index + 1:06d}"
            )

        df.insert(
            0,
            "rtl_id",
            rtl_ids,
        )

        return df


# ---------------------------------------------------------------------
# Sort Inventory
# ---------------------------------------------------------------------

    @staticmethod
    def sort_inventory(
        df: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        Stable sorting.
        """

        if df.empty:
            return df

        return (
            df.sort_values(
                by=[
                    "repository",
                    "relative_path",
                ]
            )
            .reset_index(drop=True)
        )


# ---------------------------------------------------------------------
# Save Inventory
# ---------------------------------------------------------------------

    def save_inventory(
        self,
        df: pd.DataFrame,
    ) -> Path:
        """
        Save inventory CSV.
        """

        output = (
            self.config.metadata
            / "rtl_inventory.csv"
        )

        df.to_csv(
            output,
            index=False,
        )

        logger.info("")
        logger.info(
            "Inventory written : %s",
            output,
        )

        return output

# ---------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------

def build_inventory(
    config: DatasetConfig,
) -> pd.DataFrame:
    """
    Build RTL inventory.

    Parameters
    ----------
    config : DatasetConfig

    Returns
    -------
    pd.DataFrame
    """

    logger.info("")
    logger.info("=" * 70)
    logger.info("HTBench RTL Inventory Builder")
    logger.info("=" * 70)

    config.validate()

    scanner = InventoryScanner(config)

    repositories = scanner.discover_repositories()

    if not repositories:
        raise RuntimeError(
            "No repositories found inside downloads/."
        )

    records = scanner.scan_all_repositories(
        repositories
    )

    if not records:
        raise RuntimeError(
            "No RTL files were discovered."
        )

    df = scanner.records_to_dataframe(records)

    df = scanner.sort_inventory(df)

    df = scanner.assign_ids(df)

    scanner.save_inventory(df)

    logger.info("")
    logger.info("=" * 70)
    logger.info("Inventory Build Completed")
    logger.info("=" * 70)

    logger.info(
        "Repositories Scanned : %d",
        len(repositories),
    )

    logger.info(
        "RTL Files Discovered : %d",
        len(df),
    )

    logger.info(
        "Inventory CSV : %s",
        config.metadata / "rtl_inventory.csv",
    )

    logger.info("=" * 70)
    logger.info("")

    return df


# ---------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------

def print_inventory_summary(
    df: pd.DataFrame,
) -> None:
    """
    Print inventory statistics.
    """

    print()
    print("=" * 70)
    print("Inventory Summary")
    print("=" * 70)

    print(f"RTL Files           : {len(df)}")

    print(
        f"Repositories        : {df['repository'].nunique()}"
    )

    print()

    print("Languages")

    print("-" * 70)

    language_counts = (
        df["language"]
        .value_counts()
        .sort_index()
    )

    for language, count in language_counts.items():

        print(
            f"{language:<20} {count:>8}"
        )

    print()

    print("Largest Repositories")

    print("-" * 70)

    repository_counts = (
        df.groupby("repository")
        .size()
        .sort_values(ascending=False)
        .head(10)
    )

    for repository, count in repository_counts.items():

        print(
            f"{repository:<40} {count:>6}"
        )

    print("=" * 70)
    print()


# ---------------------------------------------------------------------
# Command Line Entry
# ---------------------------------------------------------------------

def main() -> None:

    root = (
        Path(__file__)
        .resolve()
        .parents[2]
    )

    config = DatasetConfig.from_project_root(
        root
    )

    inventory = build_inventory(config)

    print_inventory_summary(inventory)


if __name__ == "__main__":

    main()