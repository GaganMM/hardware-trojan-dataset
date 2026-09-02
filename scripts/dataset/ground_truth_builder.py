#!/usr/bin/env python3
"""
HTBench Authoritative Ground Truth Builder

Purpose
-------
Build metadata/ground_truth.csv containing ONLY authoritative ground-truth
records that this project is willing to treat as externally credible.

Current policy
--------------
1. Trust-Hub verified, per-variant benchmark knowledge is authoritative.
2. Repository-reputation / "official upstream" evidence is NOT treated as
   authoritative ground truth by this builder.
3. knowledge/generated/*.yaml is NOT treated as ground truth. It is checked
   only for conflicts/diagnostics.
4. Qwen predictions are NOT read or modified here. Qwen is the fallback
   inference source later during final dataset merging.
5. No "Unknown" rows are created here. Files without authoritative GT are
   simply absent from ground_truth.csv and will retain their Qwen prediction.

Inputs
------
    knowledge/trusthub/*.yaml
    metadata/08_labeled_inventory.csv

Outputs
-------
    metadata/ground_truth.csv
    metadata/ground_truth_conflicts.csv

Ground-truth columns
--------------------
    sha256
    rtl_id
    repository
    relative_path
    label
    ground_truth_type
    assurance_tier
    assurance_basis
    confidence
    trojan_type
    trigger_type
    payload_type
    source_citation

Important
---------
This builder intentionally operates before build_dataset.py. It reads the
file-level inventory rather than manifest.csv to avoid circular dependence on
the final dataset artifact.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import yaml

from scripts.dataset.config import DatasetConfig


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("HTBench.AuthoritativeGroundTruth")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_true(value: Any) -> bool:
    """Normalize common YAML boolean-like values."""
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes"}


def _normalize_label(value: Any) -> Optional[str]:
    """Normalize accepted binary labels."""
    if value is None:
        return None

    label = str(value).strip().lower()

    if label == "trojan":
        return "Trojan"

    if label == "clean":
        return "Clean"

    return None


def _join_references(value: Any) -> str:
    """Convert YAML reference field into a readable citation string."""
    if value is None:
        return "TrustHub"

    if isinstance(value, list):
        refs = [str(x).strip() for x in value if str(x).strip()]
        return "; ".join(refs) if refs else "TrustHub"

    text = str(value).strip()
    return text or "TrustHub"


# ---------------------------------------------------------------------------
# Ground Truth Builder
# ---------------------------------------------------------------------------

class AuthoritativeGroundTruthBuilder:
    """
    Build authoritative ground truth from verified Trust-Hub variants only.
    """

    def __init__(self, config: DatasetConfig) -> None:
        self.config = config

        # benchmark name -> authoritative metadata
        self.trusthub_variants: Dict[str, Dict[str, Any]] = {}

        self._load_trusthub()

    # ------------------------------------------------------------------
    # Repository normalization
    # ------------------------------------------------------------------

    @staticmethod
    def normalize_repository(repository: Any) -> str:
        """
        Normalize repository / benchmark names.

        Examples:
            AES-T100.part01 -> AES-T100
            EthernetMAC10GE-T700.part01 -> EthernetMAC10GE-T700
        """
        if repository is None or pd.isna(repository):
            return ""

        repository = str(repository).strip()

        repository = re.sub(
            r"\.part\d+$",
            "",
            repository,
            flags=re.IGNORECASE,
        )

        return repository

    # ------------------------------------------------------------------
    # Trust-Hub loader
    # ------------------------------------------------------------------

    def _load_trusthub(self) -> None:
        trusthub_dir = self.config.knowledge / "trusthub"

        if not trusthub_dir.exists():
            raise FileNotFoundError(
                f"Trust-Hub knowledge directory not found: {trusthub_dir}"
            )

        loaded = 0
        skipped_unverified = 0
        skipped_unknown_label = 0

        for yaml_file in sorted(trusthub_dir.glob("*.yaml")):
            try:
                with open(yaml_file, "r", encoding="utf-8") as fp:
                    data = yaml.safe_load(fp) or {}
            except Exception as exc:
                logger.warning(
                    "Could not read Trust-Hub file %s: %s",
                    yaml_file,
                    exc,
                )
                continue

            variants = data.get("variants", {})
            if not isinstance(variants, dict):
                logger.warning(
                    "Skipping %s: variants is not a mapping.",
                    yaml_file.name,
                )
                continue

            family_source = (
                data.get("family", {}).get("source", "TrustHub")
                if isinstance(data.get("family"), dict)
                else "TrustHub"
            )

            for variant_name, info in variants.items():
                if not isinstance(info, dict):
                    continue

                benchmark = info.get("benchmark") or variant_name
                benchmark = str(benchmark).strip()

                if not benchmark:
                    continue

                # Authoritative GT requires explicit verification.
                if not _is_true(info.get("verified", False)):
                    skipped_unverified += 1
                    continue

                label = _normalize_label(info.get("binary_label"))
                if label is None:
                    skipped_unknown_label += 1
                    logger.warning(
                        "Skipping verified Trust-Hub variant %s in %s: "
                        "binary_label=%r is not Clean/Trojan.",
                        benchmark,
                        yaml_file.name,
                        info.get("binary_label"),
                    )
                    continue

                if benchmark in self.trusthub_variants:
                    previous = self.trusthub_variants[benchmark]

                    # Conflicting duplicate benchmark definitions are not
                    # silently overwritten.
                    if previous["label"] != label:
                        raise ValueError(
                            "Conflicting authoritative Trust-Hub labels for "
                            f"{benchmark}: {previous['label']} vs {label}"
                        )

                    logger.warning(
                        "Duplicate Trust-Hub benchmark definition for %s; "
                        "keeping the first definition.",
                        benchmark,
                    )
                    continue

                self.trusthub_variants[benchmark] = {
                    "label": label,
                    "confidence": info.get("confidence", "High"),
                    "trojan_type": info.get("trojan_type", "Unknown"),
                    "trigger_type": info.get("trigger_type", "Unknown"),
                    "payload_type": info.get("payload_type", "Unknown"),
                    "reference": _join_references(info.get("reference")),
                    "notes": info.get("notes", ""),
                    "knowledge_source": str(family_source),
                    "knowledge_file": yaml_file.name,
                }

                loaded += 1

        logger.info(
            "Authoritative Trust-Hub variants loaded: %d",
            loaded,
        )
        logger.info(
            "Unverified Trust-Hub variants excluded: %d",
            skipped_unverified,
        )
        logger.info(
            "Verified variants with invalid/unknown labels excluded: %d",
            skipped_unknown_label,
        )

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def lookup(self, repository: Any) -> Optional[Dict[str, Any]]:
        """
        Return authoritative GT metadata or None.

        Only Trust-Hub verified benchmark variants are accepted.
        """
        normalized = self.normalize_repository(repository)

        info = self.trusthub_variants.get(normalized)
        if info is None:
            return None

        return {
            "label": info["label"],
            "ground_truth_type": "TrustHub_verified_variant",
            "assurance_tier": 1,
            "assurance_basis": "trusthub_constructed_documented",
            "confidence": info["confidence"],
            "trojan_type": info["trojan_type"],
            "trigger_type": info["trigger_type"],
            "payload_type": info["payload_type"],
            "source_citation": info["reference"],
        }

    # ------------------------------------------------------------------
    # Build ground_truth.csv
    # ------------------------------------------------------------------

    def build(self) -> pd.DataFrame:
        inventory_file = self.config.metadata / "08_labeled_inventory.csv"

        if not inventory_file.exists():
            raise FileNotFoundError(
                f"{inventory_file} not found. "
                "Expected the file-level labeled inventory."
            )

        inventory = pd.read_csv(inventory_file)

        required = {"sha256", "repository"}
        missing = required - set(inventory.columns)

        if missing:
            raise ValueError(
                f"{inventory_file} is missing required columns: {sorted(missing)}"
            )

        rows: List[Dict[str, Any]] = []

        for _, row in inventory.iterrows():
            sha256 = str(row.get("sha256", "")).strip()

            if not sha256 or sha256.lower() == "nan":
                continue

            repository = row.get("repository", "")
            info = self.lookup(repository)

            # No authoritative evidence -> deliberately absent from GT.
            # Qwen will provide the fallback final label later.
            if info is None:
                continue

            rows.append(
                {
                    "sha256": sha256,
                    "rtl_id": row.get("rtl_id", ""),
                    "repository": repository,
                    "relative_path": row.get("relative_path", ""),
                    "label": info["label"],
                    "ground_truth_type": info["ground_truth_type"],
                    "assurance_tier": info["assurance_tier"],
                    "assurance_basis": info["assurance_basis"],
                    "confidence": info["confidence"],
                    "trojan_type": info["trojan_type"],
                    "trigger_type": info["trigger_type"],
                    "payload_type": info["payload_type"],
                    "source_citation": info["source_citation"],
                }
            )

        df = pd.DataFrame(rows)

        if df.empty:
            logger.warning(
                "No authoritative Trust-Hub ground-truth rows were found."
            )
            return df

        # ------------------------------------------------------------------
        # Duplicate SHA-256 handling
        # ------------------------------------------------------------------
        duplicates = df[df.duplicated("sha256", keep=False)].copy()

        if not duplicates.empty:
            logger.warning(
                "%d rows participate in duplicate SHA-256 ground-truth "
                "assignments.",
                len(duplicates),
            )

            conflict_counts = duplicates.groupby("sha256")["label"].nunique()
            conflicting_sha = conflict_counts[conflict_counts > 1].index.tolist()

            if conflicting_sha:
                raise ValueError(
                    "Conflicting authoritative labels found for SHA-256 values: "
                    + ", ".join(conflicting_sha[:20])
                    + (
                        " ..."
                        if len(conflicting_sha) > 20
                        else ""
                    )
                )

            # Same label from multiple benchmark/path records is safe to
            # collapse because SHA-256 is content identity.
            df = (
                df.sort_values(
                    by=[
                        "sha256",
                        "repository",
                        "relative_path",
                    ]
                )
                .drop_duplicates(
                    subset=["sha256"],
                    keep="first",
                )
                .reset_index(drop=True)
            )

        return df

    # ------------------------------------------------------------------
    # Conflict check against legacy generated LLM knowledge
    # ------------------------------------------------------------------

    def check_legacy_generated_conflicts(
        self,
        ground_truth: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        Diagnostic only.

        Compare authoritative GT against knowledge/generated/*.yaml.
        These generated YAMLs never override GT and are not themselves GT.
        """
        generated_dir = self.config.knowledge / "generated"

        columns = [
            "repository",
            "ground_truth_label",
            "ground_truth_assurance_tier",
            "ground_truth_basis",
            "generated_label",
            "generated_confidence",
            "generated_evidence",
        ]

        if not generated_dir.exists():
            logger.info(
                "knowledge/generated not found; skipping legacy conflict check."
            )
            return pd.DataFrame(columns=columns)

        if ground_truth.empty:
            return pd.DataFrame(columns=columns)

        gt_by_repo = (
            ground_truth[
                [
                    "repository",
                    "label",
                    "assurance_tier",
                    "assurance_basis",
                ]
            ]
            .drop_duplicates(subset=["repository"])
            .set_index("repository")
        )

        conflicts: List[Dict[str, Any]] = []

        for yaml_file in sorted(generated_dir.glob("*.yaml")):
            repo_name = yaml_file.stem

            if repo_name not in gt_by_repo.index:
                continue

            try:
                with open(yaml_file, "r", encoding="utf-8") as fp:
                    data = yaml.safe_load(fp) or {}
            except Exception as exc:
                logger.warning(
                    "Could not read generated knowledge %s: %s",
                    yaml_file.name,
                    exc,
                )
                continue

            label_block = data.get("binary_label", {})
            if not isinstance(label_block, dict):
                continue

            generated_label = _normalize_label(
                label_block.get("value")
            ) or str(label_block.get("value", "Unknown"))

            generated_confidence = label_block.get(
                "confidence",
                data.get("confidence", "Unknown"),
            )

            evidence = label_block.get("evidence", [])
            if isinstance(evidence, list):
                generated_evidence = " | ".join(
                    str(x) for x in evidence
                )
            else:
                generated_evidence = str(evidence)

            gt_row = gt_by_repo.loc[repo_name]

            if (
                generated_label != "Unknown"
                and generated_label != gt_row["label"]
            ):
                conflicts.append(
                    {
                        "repository": repo_name,
                        "ground_truth_label": gt_row["label"],
                        "ground_truth_assurance_tier": gt_row[
                            "assurance_tier"
                        ],
                        "ground_truth_basis": gt_row["assurance_basis"],
                        "generated_label": generated_label,
                        "generated_confidence": generated_confidence,
                        "generated_evidence": generated_evidence[:1000],
                    }
                )

        conflicts_df = pd.DataFrame(conflicts, columns=columns)

        if not conflicts_df.empty:
            logger.warning(
                "%d legacy generated-knowledge conflicts detected.",
                len(conflicts_df),
            )
        else:
            logger.info(
                "No conflicts with legacy generated knowledge."
            )

        return conflicts_df

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    def save(
        self,
        ground_truth: pd.DataFrame,
        conflicts: pd.DataFrame,
    ) -> None:
        gt_path = self.config.metadata / "ground_truth.csv"
        ground_truth.to_csv(gt_path, index=False)

        conflicts_path = (
            self.config.metadata / "ground_truth_conflicts.csv"
        )
        conflicts.to_csv(conflicts_path, index=False)

        logger.info(
            "Saved authoritative GT: %s",
            gt_path,
        )
        logger.info(
            "Saved legacy conflict report: %s",
            conflicts_path,
        )


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def print_summary(
    ground_truth: pd.DataFrame,
    conflicts: pd.DataFrame,
) -> None:
    print()
    print("=" * 72)
    print("HTBench AUTHORITATIVE GROUND TRUTH")
    print("=" * 72)

    print(
        f"Authoritative GT files : {len(ground_truth)}"
    )

    if not ground_truth.empty:
        print()
        print("Labels")
        print("-" * 72)
        print(
            ground_truth["label"]
            .value_counts()
            .to_string()
        )

        print()
        print("Repositories")
        print("-" * 72)
        print(
            f"Unique repositories: "
            f"{ground_truth['repository'].nunique()}"
        )

        print()
        print("Ground-truth type")
        print("-" * 72)
        print(
            ground_truth["ground_truth_type"]
            .value_counts()
            .to_string()
        )

        print()
        print("Assurance tier")
        print("-" * 72)
        print(
            ground_truth["assurance_tier"]
            .value_counts()
            .sort_index()
            .to_string()
        )

    print()
    print(
        f"Legacy generated-knowledge conflicts : "
        f"{len(conflicts)}"
    )

    if not conflicts.empty:
        print()
        print("Conflicts")
        print("-" * 72)
        for _, row in conflicts.iterrows():
            print(
                f"{row['repository']:<35} "
                f"GT={row['ground_truth_label']:<7} "
                f"vs generated={row['generated_label']:<7} "
                f"(conf={row['generated_confidence']})"
            )

    print()
    print("=" * 72)
    print(
        "Qwen predictions are NOT read or modified by this builder."
    )
    print(
        "Files without authoritative GT are intentionally absent from "
        "ground_truth.csv and will use Qwen as the final-label fallback."
    )
    print("=" * 72)
    print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    root = Path(__file__).resolve().parents[2]
    config = DatasetConfig.from_project_root(root)

    builder = AuthoritativeGroundTruthBuilder(config)

    ground_truth = builder.build()
    conflicts = builder.check_legacy_generated_conflicts(
        ground_truth
    )

    builder.save(
        ground_truth,
        conflicts,
    )

    print_summary(
        ground_truth,
        conflicts,
    )


if __name__ == "__main__":
    main()

