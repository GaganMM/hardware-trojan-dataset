"""
HTBench Manifest Builder

Builds the final dataset manifest consumed by
the preprocessing pipeline.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from scripts.dataset.config import DatasetConfig


logger = logging.getLogger("HTBench.Manifest")

if not logger.handlers:

    logging.basicConfig(

        level=logging.INFO,

        format="%(levelname)s | %(message)s"

    )


REQUIRED_COLUMNS = [

    "rtl_id",

    "repository",

    "file_name",

    "relative_path",

    "extension",

    "language",

    "size_kb",

    "sha256",

    "family",

    "application",

    "source",

    "binary_label",

    "trojan_type",

    "trigger_type",

    "payload_type",

    "confidence",

    "verified",

    "loc",

    "modules",

    "inputs",

    "outputs",

    "wires",

    "regs",

    "parameters",

    "assigns",

    "always_blocks",

    "instances",

]


class ManifestBuilder:

    def __init__(

        self,

        config: DatasetConfig

    ):

        self.config = config

    # ---------------------------------------------------------

    @staticmethod
    def validate_schema(
        df: pd.DataFrame
    ) -> None:

        missing = [

            column

            for column in REQUIRED_COLUMNS

            if column not in df.columns

        ]

        if missing:

            raise ValueError(

                "Missing required columns:\n"

                + "\n".join(missing)

            )

        logger.info(

            "Schema validation passed."

        )
    
        # ---------------------------------------------------------

    @staticmethod
    def reorder_columns(
        df: pd.DataFrame
    ) -> pd.DataFrame:
        """
        Reorder columns into the canonical HTBench schema.
        """

        ordered = df[REQUIRED_COLUMNS].copy()

        return ordered

    # ---------------------------------------------------------

    @staticmethod
    def append_manifest_metadata(
        df: pd.DataFrame
    ) -> pd.DataFrame:
        """
        Add dataset metadata columns.
        """

        manifest = df.copy()

        manifest.insert(
            0,
            "dataset",
            "HTBench"
        )

        manifest.insert(
            1,
            "version",
            "1.0"
        )

        manifest.insert(
            2,
            "split",
            "unassigned"
        )

        manifest.insert(
            3,
            "graph_status",
            "pending"
        )

        manifest.insert(
            4,
            "preprocessed",
            False
        )

        return manifest

    # ---------------------------------------------------------

    def build(
        self,
        inventory: pd.DataFrame
    ) -> pd.DataFrame:

        logger.info("")
        logger.info("=" * 60)
        logger.info("Building Final Manifest")
        logger.info("=" * 60)

        self.validate_schema(
            inventory
        )

        manifest = self.reorder_columns(
            inventory
        )

        manifest = self.append_manifest_metadata(
            manifest
        )

        manifest.sort_values(

            by=[

                "repository",

                "relative_path"

            ],

            inplace=True

        )

        manifest.reset_index(

            drop=True,

            inplace=True

        )

        logger.info(
            "Manifest rows : %d",
            len(manifest)
        )

        return manifest

    # ---------------------------------------------------------

    def save(
        self,
        manifest: pd.DataFrame
    ) -> Path:

        output = (
            self.config.metadata /
            "06_manifest.csv"
        )

        manifest.to_csv(
            output,
            index=False
        )

        logger.info(
            "Saved : %s",
            output
        )

        return output
    
    # ---------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------

def build_manifest(
    config: DatasetConfig,
    inventory: pd.DataFrame
) -> pd.DataFrame:

    builder = ManifestBuilder(
        config
    )

    manifest = builder.build(
        inventory
    )

    builder.save(
        manifest
    )

    return manifest


# ---------------------------------------------------------------------
# Console Summary
# ---------------------------------------------------------------------

def print_summary(
    manifest: pd.DataFrame
) -> None:

    print()
    print("=" * 70)
    print("HTBench Manifest Summary")
    print("=" * 70)

    print(f"Dataset           : HTBench")
    print(f"Version           : 1.0")
    print(f"RTL Files         : {len(manifest)}")
    print(f"Repositories      : {manifest['repository'].nunique()}")

    print()

    print("Families")
    print("-" * 70)

    print(
        manifest["family"]
        .value_counts()
        .to_string()
    )

    print()

    print("Applications")
    print("-" * 70)

    print(
        manifest["application"]
        .value_counts()
        .to_string()
    )

    print()

    print("Binary Labels")
    print("-" * 70)

    print(
        manifest["binary_label"]
        .value_counts()
        .to_string()
    )

    print()

    print("Languages")
    print("-" * 70)

    print(
        manifest["language"]
        .value_counts()
        .to_string()
    )

    print()

    print("Graph Status")
    print("-" * 70)

    print(
        manifest["graph_status"]
        .value_counts()
        .to_string()
    )

    print()

    print("Preprocessed")
    print("-" * 70)

    print(
        manifest["preprocessed"]
        .value_counts()
        .to_string()
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
        "05_labeled_inventory.csv"
    )

    if not inventory_file.exists():

        raise FileNotFoundError(
            inventory_file
        )

    inventory = pd.read_csv(
        inventory_file
    )

    logger.info("")
    logger.info("=" * 60)
    logger.info("Generating HTBench Manifest")
    logger.info("=" * 60)

    manifest = build_manifest(

        config,

        inventory

    )

    logger.info("")
    logger.info(
        "Manifest generation completed successfully."
    )

    print_summary(
        manifest
    )


if __name__ == "__main__":

    main()    