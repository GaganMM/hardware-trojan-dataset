"""
HTBench Dataset Statistics Generator
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict

import pandas as pd

from scripts.dataset.config import DatasetConfig

logger = logging.getLogger("HTBench.Statistics")

if not logger.handlers:

    logging.basicConfig(

        level=logging.INFO,

        format="%(levelname)s | %(message)s"

    )


class StatisticsGenerator:

    def __init__(
        self,
        config: DatasetConfig
    ):

        self.config = config

    # ---------------------------------------------------------

    def compute(
        self,
        inventory: pd.DataFrame
    ) -> Dict:

        stats = {}

        stats["rtl_files"] = len(inventory)

        stats["repositories"] = int(
            inventory["repository"].nunique()
        )

        stats["languages"] = (
            inventory["language"]
            .value_counts()
            .to_dict()
        )

        stats["families"] = (
            inventory["family"]
            .value_counts()
            .to_dict()
        )

        stats["applications"] = (
            inventory["application"]
            .value_counts()
            .to_dict()
        )

        stats["binary_labels"] = (
            inventory["binary_label"]
            .value_counts()
            .to_dict()
        )

        stats["sources"] = (
            inventory["source"]
            .value_counts()
            .to_dict()
        )

        stats["confidence"] = (
            inventory["confidence"]
            .value_counts()
            .to_dict()
        )

        stats["average_loc"] = round(

            inventory["loc"].mean(),

            2

        )

        stats["average_instances"] = round(

            inventory["instances"].mean(),

            2

        )

        stats["average_inputs"] = round(

            inventory["inputs"].mean(),

            2

        )

        stats["average_outputs"] = round(

            inventory["outputs"].mean(),

            2

        )

        return stats
    
        # ---------------------------------------------------------

    def save_json(
        self,
        stats: Dict
    ) -> Path:

        output = (
            self.config.metadata /
            "dataset_stats.json"
        )

        with open(
            output,
            "w",
            encoding="utf-8"
        ) as fp:

            json.dump(

                stats,

                fp,

                indent=4,

                sort_keys=True

            )

        logger.info(
            "Saved JSON : %s",
            output
        )

        return output

    # ---------------------------------------------------------

    def save_markdown(
        self,
        inventory: pd.DataFrame,
        stats: Dict
    ) -> Path:

        output = (
            self.config.metadata /
            "dataset_summary.md"
        )

        with open(
            output,
            "w",
            encoding="utf-8"
        ) as fp:

            fp.write("# HTBench Dataset Summary\n\n")

            fp.write(
                f"**RTL Files:** {stats['rtl_files']}\n\n"
            )

            fp.write(
                f"**Repositories:** {stats['repositories']}\n\n"
            )

            fp.write(
                f"**Average LOC:** {stats['average_loc']}\n\n"
            )

            fp.write(
                f"**Average Instances:** {stats['average_instances']}\n\n"
            )

            fp.write("## Languages\n\n")

            for k, v in stats["languages"].items():

                fp.write(
                    f"- **{k}** : {v}\n"
                )

            fp.write("\n## Families\n\n")

            for k, v in stats["families"].items():

                fp.write(
                    f"- **{k}** : {v}\n"
                )

            fp.write("\n## Applications\n\n")

            for k, v in stats["applications"].items():

                fp.write(
                    f"- **{k}** : {v}\n"
                )

            fp.write("\n## Binary Labels\n\n")

            for k, v in stats["binary_labels"].items():

                fp.write(
                    f"- **{k}** : {v}\n"
                )

            fp.write("\n## Sources\n\n")

            for k, v in stats["sources"].items():

                fp.write(
                    f"- **{k}** : {v}\n"
                )

            fp.write("\n## Confidence\n\n")

            for k, v in stats["confidence"].items():

                fp.write(
                    f"- **{k}** : {v}\n"
                )

            fp.write("\n## Largest Repositories\n\n")

            largest = (

                inventory["repository"]

                .value_counts()

                .head(15)

            )

            for repo, count in largest.items():

                fp.write(

                    f"- **{repo}** : {count}\n"

                )

        logger.info(
            "Saved Markdown : %s",
            output
        )

        return output
    
    # ---------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------

def generate_statistics(
    config: DatasetConfig,
    inventory: pd.DataFrame
) -> Dict:

    generator = StatisticsGenerator(config)

    stats = generator.compute(
        inventory
    )

    generator.save_json(
        stats
    )

    generator.save_markdown(
        inventory,
        stats
    )

    return stats


# ---------------------------------------------------------------------
# Console Summary
# ---------------------------------------------------------------------

def print_summary(
    stats: Dict
) -> None:

    print()
    print("=" * 70)
    print("HTBench Dataset Statistics")
    print("=" * 70)

    print(f"RTL Files        : {stats['rtl_files']}")
    print(f"Repositories     : {stats['repositories']}")

    print()

    print(f"Average LOC      : {stats['average_loc']}")
    print(f"Average Inputs   : {stats['average_inputs']}")
    print(f"Average Outputs  : {stats['average_outputs']}")
    print(f"Average Instances: {stats['average_instances']}")

    print()

    print("Families")
    print("-" * 70)

    for family, count in sorted(
        stats["families"].items(),
        key=lambda x: x[1],
        reverse=True
    ):

        print(f"{family:<20}{count:>8}")

    print()

    print("Applications")
    print("-" * 70)

    for app, count in sorted(
        stats["applications"].items(),
        key=lambda x: x[1],
        reverse=True
    ):

        print(f"{app:<20}{count:>8}")

    print()

    print("Binary Labels")
    print("-" * 70)

    for label, count in sorted(
        stats["binary_labels"].items(),
        key=lambda x: x[1],
        reverse=True
    ):

        print(f"{label:<20}{count:>8}")

    print()

    print("Sources")
    print("-" * 70)

    for source, count in sorted(
        stats["sources"].items(),
        key=lambda x: x[1],
        reverse=True
    ):

        print(f"{source:<20}{count:>8}")

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
    logger.info("Generating Dataset Statistics")
    logger.info("=" * 60)

    stats = generate_statistics(

        config,

        inventory

    )

    logger.info("")
    logger.info("Dataset statistics generated successfully.")

    print_summary(
        stats
    )


if __name__ == "__main__":

    main()  