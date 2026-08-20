import argparse
import csv
import json
import logging
import sys
from pathlib import Path
from typing import Dict, Optional, Set

import pandas as pd
import requests
from tqdm import tqdm

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.dataset.config import DatasetConfig


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("LLMAnalyzer")


class LLMAnalyzer:
    """
    Fast, resumable Qwen RTL analyzer.

    Design goals:
      1. No long retry loops.
      2. Short Ollama timeout.
      3. Skip repeatedly failing files.
      4. Persist every successful prediction immediately.
      5. Resume by SHA-256, so completed work is not repeated.
      6. Send compact RTL context instead of blindly sending large files.
      7. Preflight-check Ollama before starting a batch.
      8. Failed inference never creates a Trojan/Clean label.
    """

    def __init__(
        self,
        config: DatasetConfig,
        model_name: str = "qwen2.5-coder:1.5b",
        timeout: int = 30,
        max_chars: int = 3500,
        max_failures: int = 1,
        retry_failed: bool = False,
    ):
        self.config = config
        self.model_name = model_name
        self.timeout = timeout
        self.max_chars = max_chars
        self.max_failures = max_failures
        self.retry_failed = retry_failed

        self.ollama_url = "http://localhost:11434/api/generate"
        self.ollama_tags_url = "http://localhost:11434/api/tags"

        self.predictions_csv = self.config.metadata / "qwen_predictions.csv"
        self.failures_csv = self.config.metadata / "qwen_failures.csv"

        self.prediction_columns = [
            "file_id",
            "sha256",
            "qwen_label",
            "qwen_confidence",
            "qwen_reasoning",
        ]

        self.failure_columns = [
            "file_id",
            "sha256",
            "failures",
            "last_error",
        ]

        self.existing_predictions: Dict[str, dict] = {}
        self.failure_counts: Dict[str, int] = {}

        self._initialize_prediction_store()
        self._load_existing_predictions()
        self._load_failure_store()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _initialize_prediction_store(self) -> None:
        """Create the predictions CSV if it does not exist."""
        if not self.predictions_csv.exists():
            pd.DataFrame(columns=self.prediction_columns).to_csv(
                self.predictions_csv,
                index=False,
            )

    def _initialize_failure_store(self) -> None:
        """Create the failure CSV if it does not exist."""
        if not self.failures_csv.exists():
            pd.DataFrame(columns=self.failure_columns).to_csv(
                self.failures_csv,
                index=False,
            )

    def _load_existing_predictions(self) -> None:
        """Load successful predictions so interrupted runs can resume."""
        try:
            df = pd.read_csv(self.predictions_csv)
            if "sha256" not in df.columns:
                logger.warning(
                    "%s exists but has no sha256 column. Starting with no resume state.",
                    self.predictions_csv.name,
                )
                return

            for _, row in df.iterrows():
                sha = str(row["sha256"]).strip()
                if sha and sha.lower() != "nan":
                    self.existing_predictions[sha] = row.to_dict()

            logger.info(
                "Loaded %d existing predictions.",
                len(self.existing_predictions),
            )

        except Exception as exc:
            logger.error(
                "Error reading existing predictions: %s",
                exc,
            )

    def _load_failure_store(self) -> None:
        """Load failure counts for retry/skip control."""
        self._initialize_failure_store()

        try:
            df = pd.read_csv(self.failures_csv)

            if "sha256" not in df.columns:
                return

            for _, row in df.iterrows():
                sha = str(row["sha256"]).strip()
                if not sha or sha.lower() == "nan":
                    continue

                try:
                    self.failure_counts[sha] = int(row["failures"])
                except (TypeError, ValueError):
                    self.failure_counts[sha] = 0

            logger.info(
                "Loaded %d failure records.",
                len(self.failure_counts),
            )

        except Exception as exc:
            logger.warning(
                "Could not load failure ledger: %s",
                exc,
            )

    def _record_success(self, prediction: dict) -> None:
        """
        Persist one successful prediction immediately.

        This is intentionally one-row-at-a-time so a crash after any
        successful inference does not lose a batch of work.
        """
        pd.DataFrame(
            [prediction],
            columns=self.prediction_columns,
        ).to_csv(
            self.predictions_csv,
            mode="a",
            header=False,
            index=False,
        )

        self.existing_predictions[prediction["sha256"]] = prediction

    def _record_failure(
        self,
        file_id: str,
        sha256: str,
        error: str,
    ) -> int:
        """
        Update failure count for a file.

        Failed files remain Unknown because this CSV is only a failure ledger.
        """
        count = self.failure_counts.get(sha256, 0) + 1
        self.failure_counts[sha256] = count

        # Rewrite compact failure ledger with latest state per SHA.
        rows = []

        if self.failures_csv.exists():
            try:
                df = pd.read_csv(self.failures_csv)
                if "sha256" in df.columns:
                    rows = df.to_dict("records")
            except Exception:
                rows = []

        by_sha = {
            str(row.get("sha256", "")): row
            for row in rows
            if str(row.get("sha256", "")).strip()
        }

        by_sha[sha256] = {
            "file_id": file_id,
            "sha256": sha256,
            "failures": count,
            "last_error": str(error)[:500],
        }

        pd.DataFrame(
            list(by_sha.values()),
            columns=self.failure_columns,
        ).to_csv(
            self.failures_csv,
            index=False,
        )

        return count

    # ------------------------------------------------------------------
    # Ollama preflight
    # ------------------------------------------------------------------

    def check_ollama(self) -> bool:
        """
        Check that the Ollama server responds before starting the batch.

        This avoids wasting time if localhost:11434 is down.
        """
        try:
            response = requests.get(
                self.ollama_tags_url,
                timeout=3,
            )
            response.raise_for_status()

            data = response.json()
            models = data.get("models", [])
            model_names: Set[str] = {
                str(item.get("name", ""))
                for item in models
            }

            if self.model_name not in model_names:
                logger.warning(
                    "Ollama is reachable, but '%s' was not listed.",
                    self.model_name,
                )
                logger.info(
                    "Available Ollama models: %s",
                    sorted(model_names),
                )

            logger.info(
                "Ollama preflight OK: http://localhost:11434"
            )
            return True

        except Exception as exc:
            logger.error(
                "Ollama preflight failed: %s",
                exc,
            )
            logger.error(
                "Start Ollama and verify: "
                "curl http://localhost:11434/api/tags"
            )
            return False

    # ------------------------------------------------------------------
    # RTL context reduction
    # ------------------------------------------------------------------

    def _extract_context(self, content: str) -> str:
        """
        Reduce the RTL context sent to Qwen.

        We prioritize:
          - module/interface declarations
          - declarations
          - assignments
          - always/initial blocks
          - control conditions
          - counter/trigger/payload/security-looking logic

        If the reduced context is still large, keep both the beginning
        and end instead of blindly taking only the first N characters.
        """
        content = content.replace("\x00", " ")
        lines = content.splitlines()

        keywords = (
            "module",
            "endmodule",
            "input",
            "output",
            "inout",
            "wire",
            "reg",
            "logic",
            "parameter",
            "localparam",
            "assign",
            "always",
            "always_ff",
            "always_comb",
            "initial",
            "if",
            "else",
            "case",
            "endcase",
            "for",
            "while",
            "counter",
            "count",
            "trigger",
            "payload",
            "secret",
            "key",
            "enable",
            "disable",
            "reset",
            "state",
            "fsm",
        )

        selected = []
        seen = set()

        # Preserve header/interface context.
        for line in lines[:100]:
            text = line.strip()
            if text and text not in seen:
                selected.append(text)
                seen.add(text)

        # Add semantically interesting lines.
        for line in lines:
            text = line.strip()
            lower = text.lower()

            if (
                text
                and any(keyword in lower for keyword in keywords)
                and text not in seen
            ):
                selected.append(text)
                seen.add(text)

        compact = "\n".join(selected)

        if len(compact) <= self.max_chars:
            return compact

        head_chars = self.max_chars // 2
        tail_chars = self.max_chars - head_chars

        return (
            compact[:head_chars]
            + "\n\n// ... CONTEXT TRUNCATED ...\n\n"
            + compact[-tail_chars:]
        )

    # ------------------------------------------------------------------
    # Qwen inference
    # ------------------------------------------------------------------

    def prompt_llm(self, code_content: str) -> Optional[dict]:
        """
        One-shot Qwen inference.

        No retry loop here. A timeout/error returns None immediately.
        The caller records the failure and leaves the file Unknown.
        """
        context = self._extract_context(code_content)

        prompt = f"""Classify this Verilog/SystemVerilog RTL as Trojan or Clean.

A Trojan requires malicious or unauthorized trigger-and-payload behavior.
Do not call an ordinary counter, FSM, encryption block, testbench construct,
reset logic, or control path a Trojan by itself.

Return ONLY valid JSON:
{{
  "label": "Trojan" or "Clean",
  "confidence": 0.0,
  "reasoning": "one short evidence-based sentence"
}}

RTL:
{context}
"""

        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {
                "temperature": 0.0,
                "num_ctx": 4096,
            },
        }

        try:
            response = requests.post(
                self.ollama_url,
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()

            response_text = response.json().get(
                "response",
                "",
            ).strip()

            if not response_text:
                raise ValueError(
                    "Ollama returned an empty response."
                )

            # Some local model wrappers may still emit fences.
            if response_text.startswith("```json"):
                response_text = response_text[7:]

            if response_text.endswith("```"):
                response_text = response_text[:-3]

            result = json.loads(response_text.strip())

            label = result.get("label")

            if label not in {"Trojan", "Clean"}:
                raise ValueError(
                    f"Invalid label returned: {label!r}"
                )

            confidence = float(
                result.get("confidence", 0.0)
            )
            confidence = max(
                0.0,
                min(1.0, confidence),
            )

            reasoning = str(
                result.get("reasoning", "")
            ).strip()

            return {
                "label": label,
                "confidence": confidence,
                "reasoning": reasoning[:500],
            }

        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Malformed JSON from Ollama: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Main analysis
    # ------------------------------------------------------------------

    def analyze(self, limit: Optional[int] = None) -> None:
        manifest_file = (
            self.config.metadata
            / "manifest.csv"
        )

        if not manifest_file.exists():
            logger.error(
                "manifest.csv not found."
            )
            return

        # Check Ollama BEFORE reading/processing the batch.
        if not self.check_ollama():
            logger.error(
                "Stopping safely. No predictions were changed."
            )
            return

        try:
            df = pd.read_csv(
                manifest_file,
            )
        except Exception as exc:
            logger.error(
                "Could not read manifest.csv: %s",
                exc,
            )
            return

        required_columns = {
            "sha256",
            "absolute_path",
        }

        missing = required_columns - set(
            df.columns
        )

        if missing:
            logger.error(
                "Manifest is missing required columns: %s",
                sorted(missing),
            )
            return

        logger.info(
            "Loaded %d files from manifest.",
            len(df),
        )

        # --------------------------------------------------------------
        # Resume
        # --------------------------------------------------------------

        df["sha256"] = (
            df["sha256"]
            .fillna("")
            .astype(str)
            .str.strip()
        )

        # Work on samples not already successfully predicted.
        pending = df[
            ~df["sha256"].isin(
                self.existing_predictions.keys()
            )
        ].copy()

        # The current Qwen script is intended to fill unresolved samples.
        # If binary_label exists, prefer Unknown rows. If it doesn't,
        # analyze everything that is not already in qwen_predictions.csv.
        if "binary_label" in pending.columns:
            unknown_pending = pending[
                pending["binary_label"].fillna(
                    "Unknown"
                ).eq("Unknown")
            ].copy()
        else:
            unknown_pending = pending

        # Skip files that have already failed too many times.
        if not self.retry_failed:
            unknown_pending = unknown_pending[
                unknown_pending["sha256"].map(
                    lambda sha: self.failure_counts.get(
                        sha,
                        0,
                    )
                    < self.max_failures
                )
            ]

        if limit is not None:
            unknown_pending = (
                unknown_pending.head(limit)
            )

        if unknown_pending.empty:
            logger.info(
                "No pending files require Qwen analysis."
            )
            return

        logger.info(
            "Pending Qwen analysis: %d files.",
            len(unknown_pending),
        )
        logger.info(
            "Per-request timeout: %ds | Max context: %d chars | Max failures: %d",
            self.timeout,
            self.max_chars,
            self.max_failures,
        )

        processed_count = 0
        trojan_count = 0
        clean_count = 0
        failed_count = 0

        for _, row in tqdm(
            unknown_pending.iterrows(),
            total=len(unknown_pending),
            desc="LLM Analysis",
        ):
            file_id = row.get(
                "rtl_id",
                f"GH-{row['sha256'][:8]}",
            )

            sha256 = str(
                row["sha256"]
            ).strip()

            file_path = str(
                row["absolute_path"]
            )

            repository = str(
                row.get(
                    "repository",
                    "",
                )
            )

            # ----------------------------------------------------------
            # Read RTL
            # ----------------------------------------------------------

            try:
                path = (
                    self.config.root / file_path
                    if not Path(file_path).is_absolute()
                    else Path(file_path)
                )

                content = path.read_text(
                    errors="ignore",
                )

            except Exception as exc:
                count = self._record_failure(
                    file_id=file_id,
                    sha256=sha256,
                    error=f"File read error: {exc}",
                )

                failed_count += 1

                logger.warning(
                    "Skipped %s (read failure %d/%d).",
                    file_id,
                    count,
                    self.max_failures,
                )

                continue

            if not content.strip():
                count = self._record_failure(
                    file_id=file_id,
                    sha256=sha256,
                    error="Empty RTL file.",
                )

                failed_count += 1

                logger.warning(
                    "Skipped %s: empty RTL file.",
                    file_id,
                )

                continue

            # ----------------------------------------------------------
            # Qwen
            # ----------------------------------------------------------

            try:
                llm_result = self.prompt_llm(
                    content
                )

            except Exception as exc:
                count = self._record_failure(
                    file_id=file_id,
                    sha256=sha256,
                    error=str(exc),
                )

                failed_count += 1

                logger.warning(
                    "Qwen failed for %s "
                    "(failure %d/%d): %s",
                    file_id,
                    count,
                    self.max_failures,
                    exc,
                )

                # IMPORTANT:
                # No prediction is written.
                # The file remains Unknown.
                continue

            if not llm_result:
                count = self._record_failure(
                    file_id=file_id,
                    sha256=sha256,
                    error="No valid Qwen result.",
                )

                failed_count += 1

                continue

            # ----------------------------------------------------------
            # Immediate durable save
            # ----------------------------------------------------------

            prediction = {
                "file_id": file_id,
                "sha256": sha256,
                "qwen_label": llm_result["label"],
                "qwen_confidence": llm_result[
                    "confidence"
                ],
                "qwen_reasoning": llm_result[
                    "reasoning"
                ],
            }

            self._record_success(
                prediction
            )

            processed_count += 1

            if prediction["qwen_label"] == "Trojan":
                trojan_count += 1
            elif prediction["qwen_label"] == "Clean":
                clean_count += 1

        logger.info("")
        logger.info("=" * 70)
        logger.info("QWEN ANALYSIS COMPLETE")
        logger.info("=" * 70)
        logger.info(
            "Successful         : %d",
            processed_count,
        )
        logger.info(
            "Trojan predictions : %d",
            trojan_count,
        )
        logger.info(
            "Clean predictions  : %d",
            clean_count,
        )
        logger.info(
            "Failed / skipped   : %d",
            failed_count,
        )
        logger.info(
            "Predictions saved  : %s",
            self.predictions_csv,
        )
        logger.info(
            "Failures saved     : %s",
            self.failures_csv,
        )
        logger.info(
            "Failed files remain Unknown.",
        )
        logger.info("=" * 70)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fast, resumable Qwen RTL analyzer",
    )

    parser.add_argument(
        "--model",
        type=str,
        default="qwen2.5-coder:1.5b",
        help="Ollama model name",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=500,
        help="Maximum number of pending files to analyze",
    )

    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="Per-file Ollama timeout in seconds",
    )

    parser.add_argument(
        "--max-chars",
        type=int,
        default=6000,
        help="Maximum compact RTL context sent to Qwen",
    )

    parser.add_argument(
        "--max-failures",
        type=int,
        default=1,
        help="Maximum recorded failures before a file is skipped",
    )

    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help="Retry files already present in qwen_failures.csv",
    )

    args = parser.parse_args()

    root = (
        Path(__file__)
        .resolve()
        .parents[2]
    )

    config = DatasetConfig.from_project_root(
        root
    )

    analyzer = LLMAnalyzer(
        config=config,
        model_name=args.model,
        timeout=args.timeout,
        max_chars=args.max_chars,
        max_failures=args.max_failures,
        retry_failed=args.retry_failed,
    )

    analyzer.analyze(
        limit=args.limit
    )


if __name__ == "__main__":
    main()