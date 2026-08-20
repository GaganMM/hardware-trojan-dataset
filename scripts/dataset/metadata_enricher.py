"""
HTBench Metadata Enricher

Reads sanitized RTL inventory and enriches it with
static metadata and RTL metrics.
"""

from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path
from typing import Dict

import pandas as pd

from scripts.dataset.config import DatasetConfig


# ---------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------

logger = logging.getLogger("HTBench.Metadata")

if not logger.handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s | %(message)s"
    )


# ---------------------------------------------------------------------
# Metadata Enricher
# ---------------------------------------------------------------------

class MetadataEnricher:

    def __init__(self, config: DatasetConfig):

        self.config = config

    # -------------------------------------------------------------

    @staticmethod
    def sha256(file_path: Path) -> str:
        """
        Compute SHA256 hash of a file.
        """

        h = hashlib.sha256()

        with open(file_path, "rb") as fp:

            while True:

                chunk = fp.read(1024 * 1024)

                if not chunk:
                    break

                h.update(chunk)

        return h.hexdigest()

    # -------------------------------------------------------------

    @staticmethod
    def read_text(file_path: Path) -> str:

        try:

            return file_path.read_text(
                encoding="utf-8",
                errors="ignore"
            )

        except Exception:

            return ""

    # -------------------------------------------------------------

    @staticmethod
    def loc(text: str) -> int:
        """
        Count non-empty lines.
        """

        return sum(

            1

            for line in text.splitlines()

            if line.strip()

        )

    # -------------------------------------------------------------

    @staticmethod
    def regex_count(
        pattern: str,
        text: str
    ) -> int:

        return len(

            re.findall(

                pattern,

                text,

                flags=re.IGNORECASE |
                      re.MULTILINE

            )

        )

    # -------------------------------------------------------------

    @staticmethod
    def module_count(text: str) -> int:

        return MetadataEnricher.regex_count(

            r"\bmodule\b",

            text

        )

    # -------------------------------------------------------------

    @staticmethod
    def input_count(text: str) -> int:

        return MetadataEnricher.regex_count(

            r"\binput\b",

            text

        )

    # -------------------------------------------------------------

    @staticmethod
    def output_count(text: str) -> int:

        return MetadataEnricher.regex_count(

            r"\boutput\b",

            text

        )

    # -------------------------------------------------------------

    @staticmethod
    def wire_count(text: str) -> int:

        return MetadataEnricher.regex_count(

            r"\bwire\b",

            text

        )

    # -------------------------------------------------------------

    @staticmethod
    def reg_count(text: str) -> int:

        return MetadataEnricher.regex_count(

            r"\breg\b",

            text

        )
    
    # -------------------------------------------------------------

    @staticmethod
    def parameter_count(text: str) -> int:

        return MetadataEnricher.regex_count(

            r"\bparameter\b",

            text

        )

    # -------------------------------------------------------------

    @staticmethod
    def localparam_count(text: str) -> int:

        return MetadataEnricher.regex_count(

            r"\blocalparam\b",

            text

        )

    # -------------------------------------------------------------

    @staticmethod
    def assign_count(text: str) -> int:

        return MetadataEnricher.regex_count(

            r"\bassign\b",

            text

        )

    # -------------------------------------------------------------

    @staticmethod
    def always_count(text: str) -> int:

        return MetadataEnricher.regex_count(

            r"\balways(_ff|_comb|_latch)?\b",

            text

        )

    # -------------------------------------------------------------

    @staticmethod
    def case_count(text: str) -> int:

        return MetadataEnricher.regex_count(

            r"\bcase[xz]?\b",

            text

        )

    # -------------------------------------------------------------

    @staticmethod
    def if_count(text: str) -> int:

        return MetadataEnricher.regex_count(

            r"\bif\b",

            text

        )

    # -------------------------------------------------------------

    @staticmethod
    def for_count(text: str) -> int:

        return MetadataEnricher.regex_count(

            r"\bfor\b",

            text

        )

    # -------------------------------------------------------------

    @staticmethod
    def generate_count(text: str) -> int:

        return MetadataEnricher.regex_count(

            r"\bgenerate\b",

            text

        )

    # -------------------------------------------------------------

    @staticmethod
    def endgenerate_count(text: str) -> int:

        return MetadataEnricher.regex_count(

            r"\bendgenerate\b",

            text

        )

    # -------------------------------------------------------------

    @staticmethod
    @staticmethod
    def instance_count(text: str) -> int:
        """
        Approximate Verilog/SystemVerilog module instantiation count.

        Matches examples:
            adder u1 (...);
            fifo #( .WIDTH(8) ) u_fifo (...);

        Ignores language keywords.
        """

        keywords = {
            "module",
            "endmodule",
            "if",
            "else",
            "for",
            "while",
            "case",
            "always",
            "always_ff",
            "always_comb",
            "always_latch",
            "assign",
            "wire",
            "reg",
            "logic",
            "input",
            "output",
            "parameter",
            "localparam",
            "generate",
            "endgenerate",
        }

        count = 0

        pattern = re.compile(
            r'^\s*([A-Za-z_]\w*)\s*(?:#\s*\([^;]*?\))?\s+([A-Za-z_]\w*)\s*\(',
            re.MULTILINE,
        )

        for match in pattern.finditer(text):

            module_name = match.group(1)

            if module_name not in keywords:
                count += 1

        return count
        # -------------------------------------------------------------

    @staticmethod
    def collect_metrics(text: str) -> Dict:

        return {

            "loc":
                MetadataEnricher.loc(text),

            "modules":
                MetadataEnricher.module_count(text),

            "inputs":
                MetadataEnricher.input_count(text),

            "outputs":
                MetadataEnricher.output_count(text),

            "wires":
                MetadataEnricher.wire_count(text),

            "regs":
                MetadataEnricher.reg_count(text),

            "parameters":
                MetadataEnricher.parameter_count(text),

            "localparams":
                MetadataEnricher.localparam_count(text),

            "assigns":
                MetadataEnricher.assign_count(text),

            "always_blocks":
                MetadataEnricher.always_count(text),

            "case_blocks":
                MetadataEnricher.case_count(text),

            "if_blocks":
                MetadataEnricher.if_count(text),

            "for_loops":
                MetadataEnricher.for_count(text),

            "generate_blocks":
                MetadataEnricher.generate_count(text),

            "instances":
                MetadataEnricher.instance_count(text),
        }
    
    # -------------------------------------------------------------

    def enrich_row(
        self,
        row: pd.Series
    ) -> Dict:

        file_path = Path(row.absolute_path)

        if not file_path.exists():

            logger.warning(
                "Missing RTL : %s",
                file_path
            )

            result = row.to_dict()

            result.update({

                "sha256": "",

                "loc": 0,

                "modules": 0,

                "inputs": 0,

                "outputs": 0,

                "wires": 0,

                "regs": 0,

                "parameters": 0,

                "localparams": 0,

                "assigns": 0,

                "always_blocks": 0,

                "case_blocks": 0,

                "if_blocks": 0,

                "for_loops": 0,

                "generate_blocks": 0,

                "instances": 0

            })

            return result

        text = self.read_text(file_path)

        metrics = self.collect_metrics(text)

        result = row.to_dict()

        result.update(metrics)

        result["sha256"] = self.sha256(file_path)

        return result

    # -------------------------------------------------------------

    def enrich_inventory(
        self,
        inventory: pd.DataFrame
    ) -> pd.DataFrame:

        logger.info("")
        logger.info("=" * 60)
        logger.info("Enriching RTL Metadata")
        logger.info("=" * 60)

        enriched = []

        total = len(inventory)

        for index, (_, row) in enumerate(
            inventory.iterrows(),
            start=1
        ):

            enriched.append(
                self.enrich_row(row)
            )

            if index % 250 == 0 or index == total:

                logger.info(

                    "[%5d/%5d] Processed",

                    index,

                    total

                )

        df = pd.DataFrame(enriched)

        logger.info(
            "Metadata enrichment complete."
        )

        return df

    # -------------------------------------------------------------

    def save(
        self,
        df: pd.DataFrame
    ) -> Path:

        output = (
            self.config.metadata /
            "07_enriched_inventory.csv"
        )

        df.to_csv(

            output,

            index=False

        )

        logger.info("")

        logger.info(

            "Saved : %s",

            output

        )

        return output
    
# ---------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------

def enrich_metadata(
    config: DatasetConfig,
    inventory: pd.DataFrame
) -> pd.DataFrame:

    enricher = MetadataEnricher(config)

    df = enricher.enrich_inventory(
        inventory
    )

    enricher.save(df)

    return df


# ---------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------

def print_summary(
    df: pd.DataFrame
) -> None:

    print()
    print("=" * 70)
    print("HTBench Metadata Summary")
    print("=" * 70)

    print(f"RTL Files            : {len(df)}")
    print(f"Repositories         : {df['repository'].nunique()}")

    print()

    metrics = [

        "loc",
        "modules",
        "inputs",
        "outputs",
        "wires",
        "regs",
        "parameters",
        "assigns",
        "always_blocks",
        "instances"

    ]

    print("Average Metrics")
    print("-" * 70)

    for metric in metrics:

        print(

            f"{metric:<20}"

            f"{df[metric].mean():>10.2f}"

        )

    print()

    print("Largest RTL Files")
    print("-" * 70)

    largest = (

        df.sort_values(

            "loc",

            ascending=False

        )

        .head(10)

    )

    for _, row in largest.iterrows():

        print(

            f"{row['repository']:<30}"

            f"{row['file_name']:<35}"

            f"{row['loc']:>8}"

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
        "06_master_inventory.csv"
    )

    if not inventory_file.exists():

        raise FileNotFoundError(
            inventory_file
        )

    inventory = pd.read_csv(
        inventory_file
    )

    enriched = enrich_metadata(

        config,

        inventory

    )

    print_summary(
        enriched
    )


if __name__ == "__main__":

    main()