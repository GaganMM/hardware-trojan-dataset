"""
HTBench Semantic Labeler

Reads:
    metadata/07_enriched_inventory.csv

Uses:
    knowledge/trusthub/*.yaml

Produces:
    metadata/08_labeled_inventory.csv
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Dict, Any

import pandas as pd
import yaml

from scripts.dataset.config import DatasetConfig


# ---------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------

logger = logging.getLogger("HTBench.Labeler")

if not logger.handlers:

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s | %(message)s",
    )


# ---------------------------------------------------------------------
# Labeler
# ---------------------------------------------------------------------

class Labeler:

    def __init__(
        self,
        config: DatasetConfig,
    ) -> None:

        self.config = config

        logger.info("")
        logger.info("=" * 60)
        logger.info("Loading Knowledge Base")
        logger.info("=" * 60)

        # Generic knowledge
        self.aliases = {}
        self.family_rules = {}
        self.source_rules = {}

        # Benchmark knowledge
        self.trojan_rules = {}

        # Load all YAML files
        self.load_knowledge()

        logger.info("")
        logger.info("Knowledge Base Ready")
        logger.info("Families   : %d", len(self.family_rules))
        logger.info("Benchmarks : %d", len(self.trojan_rules))
        logger.info("=" * 60)

    # ---------------------------------------------------------------------
# YAML Loaders
# ---------------------------------------------------------------------

    def load_yaml(
        self,
        filename: str,
    ) -> Dict[str, Any]:
        """
        Load a YAML file from the knowledge directory.
        """

        path = self.config.knowledge / filename

        if not path.exists():

            logger.warning(
                "Knowledge file not found: %s",
                filename,
            )

            return {}

        with open(
            path,
            "r",
            encoding="utf-8",
        ) as fp:

            return yaml.safe_load(fp) or {}


    # ---------------------------------------------------------------------

    def load_knowledge(self) -> None:
        """
        Load all knowledge required by the labeler.
        """

        # Generic YAML files

        self.aliases = self.load_yaml(
            "aliases.yaml"
        )

        self.family_rules = self.load_yaml(
            "family_rules.yaml"
        )

        self.source_rules = self.load_yaml(
            "source_rules.yaml"
        )

        # TrustHub benchmark knowledge
        self.load_trusthub_rules()
        
        # Generated LLM/Rule engine knowledge
        self.load_generated_rules()


    # ---------------------------------------------------------------------

    def load_trusthub_rules(self) -> None:
        """
        Read every YAML inside:

            knowledge/trusthub/

        and build

            self.trojan_rules

        Example:

        {
            "AES-T100": {...},
            "AES-T200": {...},
            "MC8051-T100": {...}
        }
        """

        trusthub_dir = (
            self.config.knowledge /
            "trusthub"
        )

        if not trusthub_dir.exists():

            logger.warning(
                "TrustHub knowledge directory not found: %s",
                trusthub_dir,
            )

            return

        loaded = 0

        for yaml_file in sorted(
            trusthub_dir.glob("*.yaml")
        ):

            logger.info(
                "Loading %s",
                yaml_file.name,
            )

            with open(
                yaml_file,
                "r",
                encoding="utf-8",
            ) as fp:

                data = yaml.safe_load(fp) or {}

            variants = data.get(
                "variants",
                {}
            )

            if not variants:
                continue

            for variant_name, info in variants.items():

                benchmark = info.get(
                    "benchmark"
                )

                if benchmark is None:
                    continue

                benchmark = benchmark.strip()

                self.trojan_rules[
                    benchmark
                ] = info

                loaded += 1

        logger.info(
            "Loaded %d TrustHub benchmark variants.",
            loaded,
        )

    # ---------------------------------------------------------------------

    def load_generated_rules(self) -> None:
        """
        Read every YAML inside:
            knowledge/generated/
        and update self.trojan_rules
        """
        generated_dir = (
            self.config.knowledge /
            "generated"
        )

        if not generated_dir.exists():
            logger.info("Generated knowledge directory not found: %s", generated_dir)
            return

        loaded = 0
        for yaml_file in sorted(generated_dir.glob("*.yaml")):
            logger.info("Loading %s", yaml_file.name)
            
            with open(yaml_file, "r", encoding="utf-8") as fp:
                data = yaml.safe_load(fp) or {}
                
            # Generated YAMLs are structured as field -> {value, confidence, source, evidence}
            # Or if they are formatted like TrustHub rules, we parse accordingly.
            # Let's assume they map to the same dictionary format for the labeler
            benchmark_name = yaml_file.stem
            
            # Map rule_engine.py output format to labeler format
            parsed_info = {
                "benchmark": benchmark_name,
                "binary_label": data.get("binary_label", {}).get("value", "Unknown"),
                "trojan_type": data.get("trojan_type", {}).get("value", "Unknown"),
                "trigger_type": data.get("trigger_type", {}).get("value", "Unknown"),
                "payload_type": data.get("payload_type", {}).get("value", "Unknown"),
                "activation": data.get("activation", {}).get("value", "Unknown"),
                "stealth": data.get("stealth", {}).get("value", "Unknown"),
                "confidence": data.get("confidence", {}).get("value", "Low"),
                "verified": False
            }
            
            self.trojan_rules[benchmark_name] = parsed_info
            loaded += 1

        logger.info(
            "Loaded %d Generated benchmark variants.",
            loaded,
        )

        # ---------------------------------------------------------------------
    # Repository Normalization
    # ---------------------------------------------------------------------

    def normalize_repository(
        self,
        repository: str,
    ) -> str:
        """
        Normalize repository names before lookup.

        Examples
        --------
        AES-T100
            -> AES-T100

        AES-T100.part01
            -> AES-T100

        EthernetMAC10GE-T700.part01
            -> EthernetMAC10GE-T700
        """

        if pd.isna(repository):
            return ""

        repository = str(repository).strip()

        # Remove multipart suffixes
        repository = re.sub(
            r"\.part\d+$",
            "",
            repository,
            flags=re.IGNORECASE,
        )

        return repository


    # ---------------------------------------------------------------------
    # Benchmark Lookup
    # ---------------------------------------------------------------------

    def lookup(
        self,
        repository: str,
    ) -> Dict[str, Any]:
        """
        Return benchmark metadata for a repository.
        """

        repository = self.normalize_repository(
            repository
        )

        info = self.trojan_rules.get(
            repository
        )

        if info is None:

            return {
                "binary_label": "Unknown",
                "trojan_type": "Unknown",
                "trigger_type": "Unknown",
                "payload_type": "Unknown",
                "activation": "Unknown",
                "stealth": "Unknown",
                "confidence": "Low",
                "verified": False,
            }

        return info

        # ---------------------------------------------------------------------
    # Family Resolution
    # ---------------------------------------------------------------------

    def resolve_family(
        self,
        row: pd.Series,
    ) -> str:
        """
        Resolve RTL family using repository name,
        file name and relative path.
        """

        search_text = " ".join([
            str(row.get("repository", "")),
            str(row.get("relative_path", "")),
            str(row.get("file_name", "")),
        ]).lower()

        aliases = self.aliases.get(
            "aliases",
            {}
        )

        # Longest alias first to avoid:
        # cpu matching before zipcpu
        # spi matching before spi_host

        candidates = []

        for family, names in aliases.items():

            for alias in names:

                candidates.append(
                    (
                        len(alias),
                        family,
                        alias.lower(),
                    )
                )

        candidates.sort(
            reverse=True
        )

        for _, family, alias in candidates:

            patterns = [

                rf"\b{re.escape(alias)}\b",

                rf"/{re.escape(alias)}/",

                rf"\\{re.escape(alias)}\\",

                rf"{re.escape(alias)}_",

                rf"_{re.escape(alias)}",

                rf"{re.escape(alias)}\.",

            ]

            for pattern in patterns:

                if re.search(
                    pattern,
                    search_text,
                    re.IGNORECASE,
                ):

                    return family

        return "Unknown"


    # ---------------------------------------------------------------------
    # Application Lookup
    # ---------------------------------------------------------------------

    def application(
        self,
        family: str,
    ) -> str:
        """
        Return application category
        for a resolved family.
        """

        info = self.family_rules.get(
            family,
            {}
        )

        return info.get(
            "application",
            "Unknown",
        )


    # ---------------------------------------------------------------------
    # Source Lookup
    # ---------------------------------------------------------------------

    def source(
        self,
        repository: str,
    ) -> str:
        """
        Determine repository source.
        """

        repo = repository.lower()

        for key, value in self.source_rules.items():

            if key.lower() in repo:

                return value.get(
                    "source",
                    "GitHub",
                )

        return "GitHub"


        # ---------------------------------------------------------------------
    # Label a Single RTL File
    # ---------------------------------------------------------------------

    def label_row(
        self,
        row: pd.Series,
    ) -> Dict[str, Any]:
        """
        Apply all labels to a single RTL file.
        """

        result = row.to_dict()

        # ---------------------------------------------------------
        # Resolve Family
        # ---------------------------------------------------------

        family = self.resolve_family(row)

        result["family"] = family

        result["application"] = self.application(
            family
        )

        result["source"] = self.source(
            row["repository"]
        )

        # ---------------------------------------------------------
        # Benchmark Knowledge
        # ---------------------------------------------------------

        info = self.lookup(
            row["repository"]
        )

        result["binary_label"] = (
            info.get("binary_label") or "Unknown"
        )

        result["trojan_type"] = (
            info.get("trojan_type") or "Unknown"
        )

        result["trigger_type"] = (
            info.get("trigger_type") or "Unknown"
        )

        result["payload_type"] = (
            info.get("payload_type") or "Unknown"
        )

        result["activation"] = (
            info.get("activation") or "Unknown"
        )

        result["stealth"] = (
            info.get("stealth") or "Unknown"
        )

        result["confidence"] = (
            info.get("confidence") or "Low"
        )

        result["verified"] = info.get(
            "verified",
            False,
        )

        # Optional fields
        result["trigger_size"] = info.get(
            "trigger_size",
            "",
        )

        result["insertion_level"] = info.get(
            "insertion_level",
            "",
        )

        result["reference"] = ", ".join(
            info.get(
                "reference",
                [],
            )
        )

        result["notes"] = info.get(
            "notes",
            "",
        )

        return result

    # ---------------------------------------------------------------------
# Label Entire Inventory
# ---------------------------------------------------------------------

    def label_inventory(
        self,
        inventory: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        Apply semantic labels to every RTL file.
        """

        logger.info("")
        logger.info("=" * 60)
        logger.info("Applying Semantic Labels")
        logger.info("=" * 60)

        labeled_rows = []

        total = len(inventory)

        for index, (_, row) in enumerate(
            inventory.iterrows(),
            start=1,
        ):

            labeled_rows.append(
                self.label_row(row)
            )

            if index % 250 == 0 or index == total:

                logger.info(
                    "[%5d/%5d] Labeled",
                    index,
                    total,
                )

        labeled_df = pd.DataFrame(
            labeled_rows
        )

        logger.info("")
        logger.info(
            "Successfully labeled %d RTL files.",
            len(labeled_df),
        )

        return labeled_df


    # ---------------------------------------------------------------------
    # Save Inventory
    # ---------------------------------------------------------------------

    def save(
        self,
        inventory: pd.DataFrame,
    ) -> Path:
        """
        Save labeled inventory.
        """

        output = (
            self.config.metadata /
            "08_labeled_inventory.csv"
        )

        inventory.to_csv(
            output,
            index=False,
        )

        logger.info(
            "Saved : %s",
            output,
        )

        return output

    # ---------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------

    def auto_label(
        config: DatasetConfig,
        inventory: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        Automatically apply semantic labels to an inventory.

        Parameters
        ----------
        config : DatasetConfig
            Project configuration.

        inventory : pd.DataFrame
            Enriched RTL inventory.

        Returns
        -------
        pd.DataFrame
            Labeled RTL inventory.
        """

        labeler = Labeler(config)

        labeled = labeler.label_inventory(
            inventory
        )

        labeler.save(
            labeled
        )

        return labeled

    # ---------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------

def print_summary(
    inventory: pd.DataFrame,
) -> None:
    """
    Print a summary of the labeled dataset.
    """

    print()
    print("=" * 70)
    print("HTBench Label Summary")
    print("=" * 70)

    print(f"RTL Files          : {len(inventory)}")
    print(f"Repositories       : {inventory['repository'].nunique()}")

    print()

    # ---------------------------------------------------------
    # Binary Labels
    # ---------------------------------------------------------

    print("Binary Labels")
    print("-" * 70)

    print(
        inventory["binary_label"]
        .value_counts(dropna=False)
        .to_string()
    )

    print()

    # ---------------------------------------------------------
    # Trojan Types
    # ---------------------------------------------------------

    print("Trojan Types")
    print("-" * 70)

    print(
        inventory["trojan_type"]
        .value_counts(dropna=False)
        .to_string()
    )

    print()

    # ---------------------------------------------------------
    # Trigger Types
    # ---------------------------------------------------------

    print("Trigger Types")
    print("-" * 70)

    print(
        inventory["trigger_type"]
        .value_counts(dropna=False)
        .to_string()
    )

    print()

    # ---------------------------------------------------------
    # Payload Types
    # ---------------------------------------------------------

    print("Payload Types")
    print("-" * 70)

    print(
        inventory["payload_type"]
        .value_counts(dropna=False)
        .to_string()
    )

    print()

    # ---------------------------------------------------------
    # Families
    # ---------------------------------------------------------

    print("Families")
    print("-" * 70)

    print(
        inventory["family"]
        .value_counts()
        .head(20)
        .to_string()
    )

    print()

    # ---------------------------------------------------------
    # Applications
    # ---------------------------------------------------------

    print("Applications")
    print("-" * 70)

    print(
        inventory["application"]
        .value_counts()
        .to_string()
    )

    print()

    # ---------------------------------------------------------
    # Sources
    # ---------------------------------------------------------

    print("Sources")
    print("-" * 70)

    print(
        inventory["source"]
        .value_counts()
        .to_string()
    )

    print()

    # ---------------------------------------------------------
    # Confidence
    # ---------------------------------------------------------

    print("Confidence")
    print("-" * 70)

    print(
        inventory["confidence"]
        .value_counts(dropna=False)
        .to_string()
    )

    print()

    # ---------------------------------------------------------
    # Verification
    # ---------------------------------------------------------

    print("Verified")
    print("-" * 70)

    print(
        inventory["verified"]
        .value_counts(dropna=False)
        .to_string()
    )

    print("=" * 70)
    print()



# ---------------------------------------------------------------------
# Command Line Entry
# ---------------------------------------------------------------------

# ---------------------------------------------------------------------
# Command Line Entry
# ---------------------------------------------------------------------
def validate_knowledge(
labeler: Labeler,
) -> None:


    print()
    print("=" * 70)
    print("Knowledge Base Validation")
    print("=" * 70)

    print(f"Aliases           : {len(labeler.aliases.get('aliases', {}))}")
    print(f"Families          : {len(labeler.family_rules)}")
    print(f"Sources           : {len(labeler.source_rules)}")
    print(f"Benchmarks Loaded : {len(labeler.trojan_rules)}")

    print()

    examples = [
        "AES-T100",
        "RS232-T100",
        "MC8051-T200",
        "b19-T100",
        "EthernetMAC10GE-T700",
    ]

    print("Sample Benchmarks")
    print("-" * 70)

    for repo in examples:

        if repo in labeler.trojan_rules:

            print(f"[OK] {repo}")

        else:

            print(f"[FAIL] {repo}")

    print("=" * 70)
    print()

def main() -> None:
    """
    HTBench Semantic Labeler Entry Point.
    """

    # ---------------------------------------------------------
    # Project Root
    # ---------------------------------------------------------

    root = (
        Path(__file__)
        .resolve()
        .parents[2]
    )

    config = DatasetConfig.from_project_root(
        root
    )

    # ---------------------------------------------------------
    # Input Inventory
    # ---------------------------------------------------------

    inventory_file = (
        config.metadata /
        "07_enriched_inventory.csv"
    )

    if not inventory_file.exists():

        raise FileNotFoundError(
            f"Inventory not found:\n{inventory_file}"
        )

    logger.info("")
    logger.info("=" * 60)
    logger.info("Reading Enriched Inventory")
    logger.info("=" * 60)

    inventory = pd.read_csv(
        inventory_file
    )

    logger.info(
        "Loaded %d RTL files.",
        len(inventory),
    )

    # ---------------------------------------------------------
    # Initialize Labeler
    # ---------------------------------------------------------

    labeler = Labeler(
        config
    )

    # ---------------------------------------------------------
    # Validate Knowledge Base
    # ---------------------------------------------------------

    validate_knowledge(
        labeler
    )

    # ---------------------------------------------------------
    # Apply Semantic Labels
    # ---------------------------------------------------------

    labeled = labeler.label_inventory(
        inventory
    )

    # ---------------------------------------------------------
    # Save Output
    # ---------------------------------------------------------

    labeler.save(
        labeled
    )

    # ---------------------------------------------------------
    # Print Summary
    # ---------------------------------------------------------

    print_summary(
        labeled
    )


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------

if __name__ == "__main__":

    main()


# ---------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------

