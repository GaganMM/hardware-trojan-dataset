"""
HTBench Duplicate Detector

Detects duplicate RTL files using SHA256 hashes.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Tuple

import pandas as pd

from scripts.dataset.config import DatasetConfig


# ---------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------

logger = logging.getLogger("HTBench.Duplicates")

if not logger.handlers:

    logging.basicConfig(

        level=logging.INFO,

        format="%(levelname)s | %(message)s"

    )


# ---------------------------------------------------------------------
# Duplicate Detector
# ---------------------------------------------------------------------

class DuplicateDetector:

    def __init__(
        self,
        config: DatasetConfig
    ):

        self.config = config

    # -------------------------------------------------------------

    @staticmethod
    def find_duplicate_groups(
        inventory: pd.DataFrame
    ) -> pd.DataFrame:
        """
        Return every RTL file whose SHA256
        appears more than once.
        """

        duplicates = inventory[

            inventory.duplicated(

                subset=["sha256"],

                keep="first"

            )

        ].copy()

        duplicates.sort_values(

            by=[

                "sha256",

                "repository",

                "relative_path"

            ],

            inplace=True

        )

        duplicates.reset_index(

            drop=True,

            inplace=True

        )

        return duplicates

    # -------------------------------------------------------------

    @staticmethod
    def build_unique_inventory(
        inventory: pd.DataFrame
    ) -> pd.DataFrame:
        """
        Keep the first occurrence of each SHA256.
        """

        unique = (

            inventory

            .drop_duplicates(

                subset=["sha256"],

                keep="first"

            )

            .copy()

        )

        unique.sort_values(

            by=[

                "repository",

                "relative_path"

            ],

            inplace=True

        )

        unique.reset_index(

            drop=True,

            inplace=True

        )

        return unique

    # -------------------------------------------------------------

    @staticmethod
    def duplicate_statistics(
        inventory: pd.DataFrame,
        unique: pd.DataFrame,
        duplicates: pd.DataFrame
    ) -> dict:

        duplicate_groups = (

            duplicates["sha256"]

            .nunique()

        )

        duplicate_files = (

            len(inventory)

            -

            len(unique)

        )

        return {

            "total_files": len(inventory),

            "unique_files": len(unique),

            "duplicate_files": duplicate_files,

            "duplicate_groups": duplicate_groups

        }
    
    # -------------------------------------------------------------

    def detect(
        self,
        inventory: pd.DataFrame
    ) -> Tuple[pd.DataFrame, pd.DataFrame, dict]:
        """
        Detect duplicates and build unique inventory.

        Returns
        -------
        unique_inventory
        duplicate_inventory
        statistics
        """

        logger.info("")
        logger.info("=" * 60)
        logger.info("Detecting Duplicate RTL Files")
        logger.info("=" * 60)

        duplicates = self.find_duplicate_groups(
            inventory
        )

        unique = self.build_unique_inventory(
            inventory
        )

        stats = self.duplicate_statistics(
            inventory,
            unique,
            duplicates
        )

        logger.info(
            "Original Files      : %d",
            stats["total_files"]
        )

        logger.info(
            "Unique Files        : %d",
            stats["unique_files"]
        )

        logger.info(
            "Duplicate Files     : %d",
            stats["duplicate_files"]
        )

        logger.info(
            "Duplicate Groups    : %d",
            stats["duplicate_groups"]
        )

        return (
            unique,
            duplicates,
            stats
        )

    # -------------------------------------------------------------

    def save(
        self,
        unique: pd.DataFrame,
        duplicates: pd.DataFrame
    ) -> Tuple[Path, Path]:

        unique_file = (
            self.config.metadata /
            "04_unique_inventory.csv"
        )

        duplicate_file = (
            self.config.metadata /
            "duplicate_report.csv"
        )

        unique.to_csv(
            unique_file,
            index=False
        )

        duplicates.to_csv(
            duplicate_file,
            index=False
        )

        logger.info("")

        logger.info(
            "Unique Inventory  : %s",
            unique_file
        )

        logger.info(
            "Duplicate Report  : %s",
            duplicate_file
        )

        return (
            unique_file,
            duplicate_file
        )
    
# ---------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------

def remove_duplicates(
    config: DatasetConfig,
    inventory: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:

    detector = DuplicateDetector(config)

    unique_df, duplicate_df, stats = detector.detect(
        inventory
    )

    detector.save(
        unique_df,
        duplicate_df
    )

    logger.info("")
    logger.info("=" * 60)
    logger.info("Duplicate Detection Complete")
    logger.info("=" * 60)

    logger.info(
        "Original Files   : %d",
        stats["total_files"]
    )

    logger.info(
        "Unique Files     : %d",
        stats["unique_files"]
    )

    logger.info(
        "Duplicate Files  : %d",
        stats["duplicate_files"]
    )

    logger.info(
        "Duplicate Groups : %d",
        stats["duplicate_groups"]
    )

    logger.info("=" * 60)

    return (
        unique_df,
        duplicate_df
    )


# ---------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------

def print_summary(
    unique_df: pd.DataFrame,
    duplicate_df: pd.DataFrame
) -> None:

    print()
    print("=" * 70)
    print("HTBench Duplicate Summary")
    print("=" * 70)

    print(
        f"Unique RTL Files      : {len(unique_df)}"
    )

    print(
        f"Duplicate RTL Files   : {len(duplicate_df)}"
    )

    duplicate_groups = (
        duplicate_df["sha256"].nunique()
        if not duplicate_df.empty
        else 0
    )

    print(
        f"Duplicate Groups      : {duplicate_groups}"
    )

    if not duplicate_df.empty:

        print()
        print("Top Duplicate Repositories")
        print("-" * 70)

        counts = (
            duplicate_df["repository"]
            .value_counts()
            .head(10)
        )

        for repo, count in counts.items():

            print(
                f"{repo:<35}{count:>8}"
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

    inventory_file = (
        config.metadata /
        "03_enriched_inventory.csv"
    )

    if not inventory_file.exists():

        raise FileNotFoundError(
            inventory_file
        )

    inventory = pd.read_csv(
        inventory_file
    )

    unique_df, duplicate_df = remove_duplicates(

        config,

        inventory

    )

    print_summary(

        unique_df,

        duplicate_df

    )


if __name__ == "__main__":

    main()