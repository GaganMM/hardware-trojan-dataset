import argparse
import collections
import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field

# Imports for optional LLM mode
try:
    from google import genai
    from google.genai import types
    from openai import OpenAI
    HAS_LLM_LIBS = True
except ImportError:
    HAS_LLM_LIBS = False

from scripts.dataset.config import DatasetConfig

# ---------------------------------------------------------------------
# Logging Setup
# ---------------------------------------------------------------------

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("Annotator")


# ---------------------------------------------------------------------
# Structured Output Data Models
# ---------------------------------------------------------------------

class ExtractedMetadata(BaseModel):
    family: str = Field(default="Unknown")
    application: str = Field(default="Unknown")
    binary_label: str = Field(default="Unknown")
    trojan_present: bool = Field(default=False)
    trojan_type: str = Field(default="Unknown")
    trigger_type: str = Field(default="Unknown")
    payload_type: str = Field(default="Unknown")
    activation: str = Field(default="Unknown")
    stealth: str = Field(default="Unknown")
    confidence: float = Field(default=0.5)
    reasoning: List[str] = Field(default_factory=list)


class ReviewResult(BaseModel):
    agree: bool = Field(default=True)
    confidence: float = Field(default=1.0)
    feedback: str = Field(default="")


# ---------------------------------------------------------------------
# Engine 1: Static Heuristic Knowledge Extractor (Offline Default)
# ---------------------------------------------------------------------

class OfflineHeuristicExtractor:
    """
    Analyzes RTL source code, READMEs, and file structure using static 
    heuristics and AST-like pattern analysis to extract security metadata.
    """
    
    FAMILY_PATTERNS = {
        "AES": [r"\baes\b", r"aes_128", r"aes_256", r"sbox", r"mixcolumns"],
        "UART": [r"\buart\b", r"baud", r"tx_ready", r"rx_ready", r"rs232"],
        "RSA": [r"\brsa\b", r"montgomery", r"modular_exp"],
        "SHA": [r"\bsha\b", r"sha256", r"sha512", r"digest"],
        "RISC-V": [r"riscv", r"rv32", r"rv64", r"picorv32", r"ibex", r"vexriscv"],
        "MIPS": [r"mips", r"alu_control", r"regfile"],
        "CAN": [r"\bcan\b", r"can_controller", r"can_bus"],
        "SPI": [r"\bspi\b", r"spimaster", r"spislave"],
        "I2C": [r"\bi2c\b", r"i2c_master", r"sda", r"scl"],
        "Ethernet": [r"ethernet", r"mac_10g", r"rmii", r"smii"]
    }
    
    APPLICATION_MAP = {
        "AES": "Cryptography",
        "RSA": "Cryptography",
        "SHA": "Cryptography",
        "UART": "Communication",
        "CAN": "Communication",
        "SPI": "Communication",
        "I2C": "Communication",
        "Ethernet": "Communication",
        "RISC-V": "Processor",
        "MIPS": "Processor"
    }

    def analyze(self, repo_name: str, context: str) -> ExtractedMetadata:
        reasoning = []
        family = "Unknown"
        application = "Unknown"
        binary_label = "Unknown"
        trojan_present = False
        trojan_type = "Unknown"
        trigger_type = "Unknown"
        payload_type = "Unknown"
        activation = "Unknown"
        stealth = "Unknown"
        confidence = 0.60

        lower_context = context.lower()
        lower_repo = repo_name.lower()

        # 1. Family & Application Detection
        for fam, patterns in self.FAMILY_PATTERNS.items():
            for pat in patterns:
                if re.search(pat, lower_repo) or re.search(pat, lower_context):
                    family = fam
                    application = self.APPLICATION_MAP.get(fam, "Unknown")
                    reasoning.append(f"Identified family '{fam}' via pattern match '{pat}'")
                    break
            if family != "Unknown":
                break

        # 2. Trojan Presence Detection
        trojan_indicators = [r"\btrojan\b", r"\btj_in\b", r"\btjin\b", r"\bmalicious\b", r"side_channel_leak"]
        clean_indicators = [r"tjfree", r"verified_clean", r"clean_core"]

        is_trojan_indicated = any(re.search(pat, lower_repo) or re.search(pat, lower_context) for pat in trojan_indicators)
        is_clean_indicated = any(re.search(pat, lower_context) for pat in clean_indicators)

        if is_trojan_indicated:
            binary_label = "Trojan"
            trojan_present = True
            confidence = 0.85
            reasoning.append("Trojan logic detected via structural/naming keywords")
        elif is_clean_indicated:
            binary_label = "Clean"
            trojan_present = False
            confidence = 0.80
            reasoning.append("Verified clean module markers identified")
        else:
            binary_label = "Unknown"
            trojan_present = False
            confidence = 0.0
            reasoning.append("No verified evidence of Clean or Trojan status.")

        # 3. Trojan Type & Trigger/Payload Extraction
        if trojan_present:
            if re.search(r"count\s*<=|counter\s*<=", lower_context):
                trigger_type = "Sequential Counter"
                reasoning.append("Sequential counter logic identified in trigger path")
            elif re.search(r"always\s*@\s*\(\s*posedge", lower_context):
                trigger_type = "Sequential Condition"
                reasoning.append("Sequential clock-triggered logic identified")
            elif re.search(r"assign\s+.*==", lower_context):
                trigger_type = "Combinational Condition"
                reasoning.append("Combinational equality trigger condition identified")

            if re.search(r"leak|key\s*\^|secret", lower_context):
                trojan_type = "Information Leakage"
                payload_type = "Key Leakage"
                activation = "Internal"
                stealth = "High"
                reasoning.append("Key leakage path identified")
            elif re.search(r"disable|disable_core|hang|freeze", lower_context):
                trojan_type = "Denial of Service"
                payload_type = "System Failure"
                activation = "Internal"
                stealth = "Medium"
                reasoning.append("Denial of Service / Core disable logic identified")
            elif re.search(r"corrupt|alter|override", lower_context):
                trojan_type = "Functional Modification"
                payload_type = "Output Corruption"
                activation = "Internal"
                stealth = "High"
                reasoning.append("Functional modification logic identified")

        return ExtractedMetadata(
            family=family,
            application=application,
            binary_label=binary_label,
            trojan_present=trojan_present,
            trojan_type=trojan_type,
            trigger_type=trigger_type,
            payload_type=payload_type,
            activation=activation,
            stealth=stealth,
            confidence=confidence,
            reasoning=reasoning
        )


# ---------------------------------------------------------------------
# Engine 2: Dual-LLM Consensus Extractor (Optional Cloud Mode)
# ---------------------------------------------------------------------

class DualLLMExtractor:
    def __init__(self, config: DatasetConfig):
        self.config = config
        load_dotenv(config.root / ".env")
        
        self.gemini_key = os.environ.get("GEMINI_API_KEY")
        self.openai_key = os.environ.get("OPENAI_API_KEY")
        
        self.gemini_client = genai.Client(api_key=self.gemini_key) if (HAS_LLM_LIBS and self.gemini_key) else None
        self.openai_client = OpenAI(api_key=self.openai_key) if (HAS_LLM_LIBS and self.openai_key) else None

    def analyze(self, repo_name: str, context: str) -> Tuple[Optional[ExtractedMetadata], str]:
        if not self.gemini_client or not self.openai_client:
            return None, "LLM API keys missing."

        # Model A: Extraction
        prompt = f"Analyze hardware repository '{repo_name}' RTL code for Trojans:\n\n{context}"
        try:
            res_a = self.gemini_client.models.generate_content(
                model='gemini-2.5-pro',
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=ExtractedMetadata,
                ),
            )
            extracted = ExtractedMetadata(**json.loads(res_a.text))
        except Exception as e:
            return None, f"Gemini Extraction Error: {e}"

        # Model B: Audit
        review_prompt = f"Audit this extracted metadata:\n{extracted.model_dump_json(indent=2)}\n\nAgainst source context:\n{context}"
        try:
            res_b = self.openai_client.beta.chat.completions.parse(
                model="gpt-4o",
                messages=[{"role": "system", "content": "You are a hardware auditor."}, {"role": "user", "content": review_prompt}],
                response_format=ReviewResult,
            )
            review = res_b.choices[0].message.parsed
            if review.agree:
                return extracted, "Approved by Model B"
            else:
                return None, f"Disagreed by Model B: {review.feedback}"
        except Exception as e:
            return None, f"OpenAI Audit Error: {e}"


# ---------------------------------------------------------------------
# Unified Knowledge Annotator Pipeline
# ---------------------------------------------------------------------

class UnifiedAnnotator:

    def __init__(self, config: DatasetConfig, use_llm: bool = False):
        self.config = config
        self.use_llm = use_llm
        self.offline_extractor = OfflineHeuristicExtractor()
        self.llm_extractor = DualLLMExtractor(config) if use_llm else None
        
        self.generated_dir = self.config.knowledge / "generated"
        self.generated_dir.mkdir(parents=True, exist_ok=True)

    def _gather_context(self, repo_name: str, repo_df: pd.DataFrame) -> str:
        context_parts = [f"Repository: {repo_name}\n"]
        abs_paths = repo_df['absolute_path'].dropna().unique()
        files_found = 0
        repo_root = None

        for p_str in abs_paths:
            p = self.config.root / p_str if not Path(p_str).is_absolute() else Path(p_str)
            if p.exists() and p.is_file():
                if repo_root is None:
                    repo_root = p.parent
                    while repo_root.parent != self.config.downloads and repo_root != self.config.downloads and repo_root.parent != repo_root:
                        if (repo_root / "README.md").exists() or (repo_root / "README").exists():
                            break
                        repo_root = repo_root.parent
                        
                try:
                    content = p.read_text(encoding='utf-8', errors='ignore')
                    context_parts.append(f"--- File: {p.name} ---\n{content}\n")
                    files_found += 1
                except Exception:
                    pass

        if files_found == 0:
            matching_dirs = [d for d in self.config.downloads.rglob(repo_name) if d.is_dir()]
            if not matching_dirs:
                matching_dirs = [d for d in self.config.downloads.rglob("*") if d.is_dir() and d.name.lower() == repo_name.lower()]

            if matching_dirs:
                target_dir = matching_dirs[0]
                repo_root = target_dir
                for f in list(target_dir.rglob("*.v")) + list(target_dir.rglob("*.sv")) + list(target_dir.rglob("*.vhd")) + list(target_dir.rglob("*.vhdl")):
                    try:
                        content = f.read_text(encoding='utf-8', errors='ignore')
                        context_parts.append(f"--- File: {f.name} ---\n{content}\n")
                        files_found += 1
                    except Exception:
                        pass

        if files_found == 0:
            return "Context not found."

        if repo_root and repo_root.exists():
            readme_files = list(repo_root.rglob("README*"))
            if readme_files:
                try:
                    readme_content = readme_files[0].read_text(encoding='utf-8', errors='ignore')
                    context_parts.insert(1, f"--- README.md ---\n{readme_content[:2000]}\n")
                except Exception:
                    pass

        return "\n".join(context_parts)

    def save_generated_yaml(self, repo_name: str, extracted: ExtractedMetadata, source_tag: str):
        yaml_data = {}
        fields_to_map = [
            ("family", extracted.family),
            ("application", extracted.application),
            ("binary_label", extracted.binary_label),
            ("trojan_type", extracted.trojan_type),
            ("trigger_type", extracted.trigger_type),
            ("payload_type", extracted.payload_type),
            ("activation", extracted.activation),
            ("stealth", extracted.stealth)
        ]
        
        for key, val in fields_to_map:
            yaml_data[key] = {
                "value": val,
                "confidence": extracted.confidence,
                "source": source_tag,
                "evidence": extracted.reasoning
            }

        output_path = self.generated_dir / f"{repo_name}.yaml"
        with open(output_path, "w", encoding='utf-8') as f:
            yaml.dump(yaml_data, f, sort_keys=False, default_flow_style=False)
            
        logger.info(f"Saved generated knowledge to {output_path}")

    def run_pipeline(self):
        inventory_file = self.config.metadata / "08_labeled_inventory.csv"
        if not inventory_file.exists():
            logger.error("08_labeled_inventory.csv not found. Run labeler first.")
            return

        df = pd.read_csv(inventory_file)
        unknown_repos = df[(df['binary_label'] == 'Unknown') | (df['trojan_type'] == 'Unknown')]
        targets = unknown_repos.drop_duplicates(subset=['repository'])
        
        mode_str = "Dual-LLM Consensus" if self.use_llm else "Offline Static Analysis"
        logger.info(f"Running Knowledge Annotator [{mode_str}] over {len(targets)} repositories.")
        
        success_count = 0
        error_count = 0

        for index, row in targets.iterrows():
            repo_name = row['repository']
            
            if (self.generated_dir / f"{repo_name}.yaml").exists():
                logger.info(f"Skipping {repo_name} (YAML already exists)")
                continue

            logger.info(f"Analyzing {repo_name}...")
            
            repo_df = df[df['repository'] == repo_name]
            context = self._gather_context(repo_name, repo_df)
            
            if context == "Context not found.":
                logger.warning(f"No source code context found for {repo_name}.")
                error_count += 1
                continue

            if self.use_llm and self.llm_extractor:
                extracted, msg = self.llm_extractor.analyze(repo_name, context)
                source_tag = "LLM Consensus"
            else:
                extracted = self.offline_extractor.analyze(repo_name, context)
                source_tag = "Static Analysis Engine"
                msg = "Offline Analysis"

            if extracted:
                logger.info(f"[{repo_name}] Inferred: {extracted.binary_label} | Family: {extracted.family} | Type: {extracted.trojan_type}")
                self.save_generated_yaml(repo_name, extracted, source_tag)
                success_count += 1
            else:
                logger.warning(f"[{repo_name}] Skipped: {msg}")
                error_count += 1
                
        logger.info(f"Pipeline Complete [{mode_str}]. Generated: {success_count}, Skipped/Errors: {error_count}")


def main():
    parser = argparse.ArgumentParser(description="HTBench Unified Knowledge Annotator")
    parser.add_argument("--use-llm", action="store_true", help="Enable Dual-LLM Consensus mode (requires Gemini + OpenAI API keys)")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[2]
    config = DatasetConfig.from_project_root(root)
    
    annotator = UnifiedAnnotator(config, use_llm=args.use_llm)
    annotator.run_pipeline()


if __name__ == "__main__":
    main()
