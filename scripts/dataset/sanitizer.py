"""
HTBench RTL Inventory Sanitizer

Filters out unwanted RTL files before metadata extraction.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Tuple

import pandas as pd
import yaml

from scripts.dataset.config import DatasetConfig

logger = logging.getLogger("HTBench.Sanitizer")

if not logger.handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s | %(message)s"
    )


class Sanitizer:

    def __init__(self, config: DatasetConfig):

        self.config = config

        self.rules = self.load_rules()

    # ---------------------------------------------------------

    def load_rules(self) -> dict:

        rule_file = (
            self.config.knowledge /
            "sanitizer_rules.yaml"
        )

        if not rule_file.exists():

            logger.warning(
                "sanitizer_rules.yaml not found. Using defaults."
            )

            return {

                "ignore_directories": [
                    ".git",
                    ".github",
                    "docs",
                    "doc",
                    "uvm",
                    "verification",
                    "verif",
                    "sim",
                    "simulation",
                    "vendor",
                    "third_party",
                    "__pycache__"
                ],

                "testbench_patterns": [
                    r"(^tb_)",
                    r"(_tb$)",
                    r"(testbench)",
                    r"(_test$)",
                    r"(^test_)",
                    r"(tb)"
                ],

                "minimum_size_kb": 0.08

            }

        with open(
            rule_file,
            "r",
            encoding="utf-8"
        ) as fp:

            return yaml.safe_load(fp)

    # ---------------------------------------------------------

    def reject_directory(
        self,
        relative_path: str
    ) -> bool:

        folders = Path(relative_path).parts

        ignore_dirs = set(
            self.rules["ignore_directories"]
        )

        for folder in folders:

            if folder.lower() in {

                x.lower()
                for x in ignore_dirs
            }:

                return True

        return False

    # ---------------------------------------------------------

    def reject_testbench(
        self,
        filename: str,
        module: str
    ) -> bool:

        patterns = self.rules[
            "testbench_patterns"
        ]

        text = (
            filename.lower() +
            " " +
            module.lower()
        )

        for pattern in patterns:

            if re.search(
                pattern,
                text,
                re.IGNORECASE
            ):

                return True

        return False

    # ---------------------------------------------------------

    def reject_small_file(
        self,
        size_kb: float
    ) -> bool:

        return (
            size_kb <
            self.rules[
                "minimum_size_kb"
            ]
        )

    # ---------------------------------------------------------

    def evaluate_row(
        self,
        row: pd.Series
    ) -> Tuple[bool, str]:

        if self.reject_directory(
            row.relative_path
        ):

            return (
                False,
                "ignored_directory"
            )

        if self.reject_testbench(

            row.file_name,

            row.module_name

        ):

            return (
                False,
                "testbench"
            )

        if self.reject_small_file(
            row.size_kb
        ):

            return (
                False,
                "too_small"
            )

        return (
            True,
            ""
        )

    # ---------------------------------------------------------

    def sanitize(
        self,
        inventory: pd.DataFrame
    ) -> tuple[pd.DataFrame, pd.DataFrame]:

        logger.info("")
        logger.info("=" * 60)
        logger.info("Sanitizing Inventory")
        logger.info("=" * 60)

        accepted = []
        rejected = []

        for _, row in inventory.iterrows():

            keep, reason = self.evaluate_row(row)

            record = row.to_dict()

            record["is_valid"] = keep
            record["reject_reason"] = reason

            if keep:
                accepted.append(record)
            else:
                rejected.append(record)

        clean_df = pd.DataFrame(accepted)
        rejected_df = pd.DataFrame(rejected)

        logger.info(
            "Accepted : %d",
            len(clean_df)
        )

        logger.info(
            "Rejected : %d",
            len(rejected_df)
        )

        return (
            clean_df,
            rejected_df
        )

    # ---------------------------------------------------------

    def save_results(
        self,
        clean_df: pd.DataFrame,
        rejected_df: pd.DataFrame
    ) -> tuple[Path, Path]:

        clean_file = (
            self.config.metadata /
            "clean_inventory.csv"
        )

        rejected_file = (
            self.config.metadata /
            "rejected_inventory.csv"
        )

        clean_df.to_csv(
            clean_file,
            index=False
        )

        rejected_df.to_csv(
            rejected_file,
            index=False
        )

        logger.info("")
        logger.info(
            "Clean Inventory     : %s",
            clean_file
        )

        logger.info(
            "Rejected Inventory  : %s",
            rejected_file
        )

        return (
            clean_file,
            rejected_file
        )


# ---------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------

def sanitize_inventory(
    config: DatasetConfig,
    inventory: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:

    sanitizer = Sanitizer(config)

    clean_df, rejected_df = sanitizer.sanitize(
        inventory
    )

    sanitizer.save_results(
        clean_df,
        rejected_df
    )

    return (
        clean_df,
        rejected_df
    )

# ---------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------

def print_summary(
    clean_df: pd.DataFrame,
    rejected_df: pd.DataFrame
) -> None:

    print()
    print("=" * 70)
    print("HTBench Sanitizer Summary")
    print("=" * 70)

    print(f"Accepted RTL Files : {len(clean_df)}")
    print(f"Rejected RTL Files : {len(rejected_df)}")

    if not rejected_df.empty:

        print()
        print("Reject Reasons")
        print("-" * 70)

        counts = (
            rejected_df["reject_reason"]
            .value_counts()
            .sort_index()
        )

        for reason, count in counts.items():

            print(
                f"{reason:<25} {count:>6}"
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
        "rtl_inventory.csv"
    )

    if not inventory_file.exists():

        raise FileNotFoundError(
            inventory_file
        )

    inventory = pd.read_csv(
        inventory_file
    )

    clean_df, rejected_df = sanitize_inventory(

        config,

        inventory

    )

    print_summary(

        clean_df,

        rejected_df

    )


if __name__ == "__main__":

    main()