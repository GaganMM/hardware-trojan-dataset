import json
import logging
import argparse
from pathlib import Path

import pandas as pd
import requests
from tqdm import tqdm

from scripts.dataset.config import DatasetConfig

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("FastGemmaVerifier")


class FastGemmaVerifier:
    """Fast verifier: Gemma checks Qwen's conclusion instead of re-analyzing RTL."""

    def __init__(self, config, model_name="gemma2:2b", batch_size=25, timeout=120):
        self.config = config
        self.model_name = model_name
        self.batch_size = batch_size
        self.timeout = timeout
        self.ollama_url = "http://localhost:11434/api/generate"

    @staticmethod
    def _clean(value, default=""):
        return default if pd.isna(value) else str(value)

    @staticmethod
    def _parse_json(text):
        text = (text or "").strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start, end = text.find("["), text.rfind("]")
            if start != -1 and end > start:
                try:
                    return json.loads(text[start:end + 1])
                except json.JSONDecodeError:
                    pass
        return []

    def _evidence(self, row):
        fields = (
            "family", "application", "source", "confidence", "verified",
            "trojan_type", "trigger_type", "payload_type",
            "loc", "inputs", "outputs", "always_blocks", "if_blocks",
            "module_count", "signal_count", "assign_count", "case_blocks"
        )
        return {
            f: row[f] for f in fields
            if f in row.index and pd.notna(row[f])
        }

    def verify_batch(self, batch):
        cases = [{
            "id": x["id"],
            "file": x["file_name"],
            "repository": x["repository"],
            "qwen_label": x["qwen_label"],
            "qwen_confidence": x["qwen_confidence"],
            "qwen_reasoning": x["qwen_reasoning"],
            "evidence": x["evidence"],
        } for x in batch]

        prompt = f"""You are a lightweight verifier for a Hardware Trojan dataset.

Qwen2.5-Coder already analyzed each RTL file. Do NOT perform a fresh
full RTL analysis. Judge whether Qwen's conclusion is reasonable from
the supplied conclusion and evidence.

AGREE = Qwen's label is reasonably supported.
DISAGREE = supplied evidence gives a clear reason to reject it.
UNCERTAIN = insufficient evidence to decide.

Do not assume GitHub means Clean.
Do not call ordinary counters, FSMs, if-statements, or security logic
a Trojan by themselves.
Do not invent evidence.
Do not change Qwen's label.
Be conservative.

Return ONLY a JSON array, one result for every id:
[
  {{"id": 0, "agreement": "AGREE", "confidence": 0.85,
    "reason": "Short verification reason."}}
]

Cases:
{json.dumps(cases, indent=2, default=str)}
"""

        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.0, "num_ctx": 4096},
        }

        try:
            r = requests.post(self.ollama_url, json=payload, timeout=self.timeout)
            r.raise_for_status()
            return self._parse_json(r.json().get("response", "[]"))
        except Exception as exc:
            logger.error("Gemma API Error: %s", exc)
            return []

    def run(self, limit=None):
        manifest = self.config.metadata / "08_labeled_inventory.csv"
        if not manifest.exists():
            logger.error("Missing %s", manifest)
            return

        df = pd.read_csv(manifest)
        if "binary_label" not in df.columns:
            logger.error("binary_label column not found")
            return

        df = df[df["binary_label"].notna()].copy()
        if limit is not None:
            df = df.head(limit)

        records = df.to_dict("records")
        for i, row in enumerate(records):
            row["id"] = i

        logger.info("Verifying %d Qwen-labeled files with %s",
                    len(records), self.model_name)

        results = []
        counts = {"AGREE": 0, "DISAGREE": 0, "UNCERTAIN": 0, "FAILED": 0}

        for start in tqdm(range(0, len(records), self.batch_size),
                          desc="Gemma Verification"):
            raw_batch = records[start:start + self.batch_size]
            batch = []

            for row in raw_batch:
                qwen_label = row.get("binary_label", "Unknown")
                for name in ("qwen_label", "llm_label", "llm_binary_label"):
                    if name in row and pd.notna(row[name]):
                        qwen_label = row[name]
                        break

                qwen_conf = row.get("confidence", "")
                for name in ("qwen_confidence", "llm_confidence"):
                    if name in row and pd.notna(row[name]):
                        qwen_conf = row[name]
                        break

                reasoning = ""
                for name in ("qwen_reasoning", "llm_reasoning", "reasoning"):
                    if name in row and pd.notna(row[name]):
                        reasoning = row[name]
                        break

                batch.append({
                    "id": row["id"],
                    "file_name": self._clean(row.get("file_name", "")),
                    "repository": self._clean(row.get("repository", "")),
                    "qwen_label": self._clean(qwen_label, "Unknown"),
                    "qwen_confidence": self._clean(qwen_conf, "Unknown"),
                    "qwen_reasoning": self._clean(
                        reasoning, "No Qwen reasoning available."
                    ),
                    "evidence": self._evidence(pd.Series(row)),
                })

            parsed = self.verify_batch(batch)
            pred_map = {}

            if isinstance(parsed, dict):
                for key in ("results", "verification", "items"):
                    if isinstance(parsed.get(key), list):
                        parsed = parsed[key]
                        break

            if isinstance(parsed, list):
                for item in parsed:
                    if not isinstance(item, dict) or "id" not in item:
                        continue
                    agreement = str(item.get("agreement", "UNCERTAIN")).upper()
                    if agreement not in ("AGREE", "DISAGREE", "UNCERTAIN"):
                        agreement = "UNCERTAIN"
                    try:
                        conf = max(0.0, min(1.0, float(item.get("confidence", 0))))
                    except (TypeError, ValueError):
                        conf = 0.0
                    pred_map[item["id"]] = {
                        "agreement": agreement,
                        "confidence": conf,
                        "reason": str(item.get("reason", "")),
                    }

            for item in batch:
                v = pred_map.get(item["id"])
                if v is None:
                    v = {
                        "agreement": "UNCERTAIN",
                        "confidence": 0.0,
                        "reason": "Gemma returned no valid result for this id.",
                    }
                    counts["FAILED"] += 1

                counts[v["agreement"]] += 1
                results.append({
                    "file_name": item["file_name"],
                    "repository": item["repository"],
                    "qwen_label": item["qwen_label"],
                    "qwen_confidence": item["qwen_confidence"],
                    "qwen_reasoning": item["qwen_reasoning"],
                    "gemma_agreement": v["agreement"],
                    "gemma_confidence": v["confidence"],
                    "gemma_reason": v["reason"],
                })

        output = self.config.metadata / "fast_verification_results.csv"
        pd.DataFrame(results).to_csv(output, index=False)

        decisive = counts["AGREE"] + counts["DISAGREE"]
        logger.info("=" * 60)
        logger.info("FAST GEMMA VERIFICATION COMPLETE")
        logger.info("Total requested : %d", len(records))
        logger.info("AGREE           : %d", counts["AGREE"])
        logger.info("DISAGREE        : %d", counts["DISAGREE"])
        logger.info("UNCERTAIN        : %d", counts["UNCERTAIN"])
        logger.info("FAILED           : %d", counts["FAILED"])
        if decisive:
            logger.info("Decisive agreement rate: %.2f%%",
                        counts["AGREE"] / decisive * 100)
        logger.info("Results saved: %s", output)


def main():
    parser = argparse.ArgumentParser(
        description="Fast Gemma verifier for Qwen annotations"
    )
    parser.add_argument("--model", default="gemma2:2b")
    parser.add_argument("--batch-size", type=int, default=25)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()

    config = DatasetConfig.from_project_root(Path(".").resolve())
    FastGemmaVerifier(
        config, args.model, args.batch_size, args.timeout
    ).run(args.limit)


if __name__ == "__main__":
    main()