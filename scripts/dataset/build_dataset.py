import json
import logging
import sys
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.dataset.config import DatasetConfig

# ---------------------------------------------------------------------
# Logging Setup
# ---------------------------------------------------------------------

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("DatasetBuilder")

# ---------------------------------------------------------------------
# Main Builder Class
# ---------------------------------------------------------------------

class DatasetBuilder:
    """
    Final stage of the HTBench pipeline.
    Reads the fully labeled inventory, filters out rejected/duplicate files,
    assigns RTL IDs, and generates the final manifest and dataset statistics.
    """
    
    def __init__(self, config: DatasetConfig):
        self.config = config
        
        self.input_csv = self.config.metadata / "08_labeled_inventory.csv"
        self.manifest_csv = self.config.metadata / "manifest.csv"
        self.duplicates_csv = self.config.metadata / "duplicate_report.csv"
        self.stats_json = self.config.metadata / "dataset_stats.json"
        self.ground_truth_csv = self.config.metadata / "ground_truth.csv"
        self.qwen_predictions_csv = self.config.metadata / "qwen_predictions.csv"
        
        self.config.metadata.mkdir(parents=True, exist_ok=True)

    def run(self):
        logger.info("=" * 70)
        logger.info("HTBench Dataset Builder")
        logger.info("=" * 70)

        if not self.input_csv.exists():
            logger.error(f"Missing fully labeled inventory: {self.input_csv}")
            return

        logger.info(f"Loading {self.input_csv.name}...")
        df = pd.read_csv(self.input_csv)
        total_initial_files = len(df)
        
        # 1. Filter out invalid/rejected files, UNLESS they are explicitly Clean/Trojan from a knowledge base
        valid_mask = df['is_valid'].isin([True, 'True', 'true', 1, '1'])
        known_mask = df['binary_label'].isin(['Clean', 'Trojan'])
        
        keep_mask = valid_mask | known_mask
        rejected_files = df[~keep_mask]
        manifest = df[keep_mask].copy()
        
        logger.info(f"Filtered out {len(rejected_files)} invalid files (testbenches, etc.).")

        # 2. Duplicate Detection
        if 'sha256' not in manifest.columns:
            logger.error("sha256 column missing from inventory!")
            return
            
        duplicate_mask = manifest.duplicated(subset=["sha256"], keep="first")
        duplicate_report = manifest[duplicate_mask].copy()
        duplicate_report["duplicate_reason"] = "Identical SHA256"
        
        duplicate_report.to_csv(self.duplicates_csv, index=False)
        manifest = manifest[~duplicate_mask].copy()
        
        logger.info(f"Filtered out {len(duplicate_report)} exact SHA256 duplicates.")

        # 3. Ground Truth Integration and Qwen Predictions
        gt_mapping = {}
        if self.ground_truth_csv.exists():
            logger.info(f"Loading ground truth from {self.ground_truth_csv.name}...")
            gt_df = pd.read_csv(self.ground_truth_csv)
            gt_mapping = dict(zip(gt_df['sha256'], gt_df['label']))
        else:
            logger.warning(f"Ground truth file {self.ground_truth_csv.name} not found.")

        qwen_mapping = {}
        qwen_conf_mapping = {}
        if self.qwen_predictions_csv.exists():
            logger.info(f"Loading Qwen predictions from {self.qwen_predictions_csv.name}...")
            qwen_df = pd.read_csv(self.qwen_predictions_csv)
            qwen_mapping = dict(zip(qwen_df['sha256'], qwen_df['qwen_label']))
            qwen_conf_mapping = dict(zip(qwen_df['sha256'], qwen_df['qwen_confidence']))
        else:
            logger.warning(f"Qwen predictions file {self.qwen_predictions_csv.name} not found.")

        # Apply ground truth to the manifest
        # If Ground Truth exists, use it and mark as verified.
        # Otherwise, use Qwen prediction and mark as inferred.
        # If neither exists, label is Unknown.
        
        def assign_label(row):
            sha = row['sha256']
            if sha in gt_mapping:
                return pd.Series({'final_label': gt_mapping[sha], 'is_verified': True})
            elif sha in qwen_mapping:
                return pd.Series({'final_label': qwen_mapping[sha], 'is_verified': False})
            else:
                return pd.Series({'final_label': 'Unknown', 'is_verified': False})

        # Drop the old binary_label and confidence from 08_labeled_inventory
        if 'binary_label' in manifest.columns:
            manifest.drop(columns=['binary_label'], inplace=True)
        if 'confidence' in manifest.columns:
            manifest.drop(columns=['confidence'], inplace=True)
            
        label_res = manifest.apply(assign_label, axis=1)
        manifest['binary_label'] = label_res['final_label']
        manifest['is_verified'] = label_res['is_verified']
        manifest['confidence'] = manifest['sha256'].apply(lambda x: qwen_conf_mapping.get(x, "Unknown") if x not in gt_mapping else "Verified")
        
        num_verified = manifest['is_verified'].sum()
        num_inferred = len(manifest) - num_verified - (manifest['binary_label'] == 'Unknown').sum()
        logger.info(f"Assigned {num_verified} verified Ground Truth labels and {num_inferred} inferred Qwen labels.")

        # 4. Stable Sort and ID Assignment
        manifest = manifest.sort_values(by=["repository", "relative_path"]).reset_index(drop=True)
        
        if 'rtl_id' in manifest.columns:
            manifest.drop(columns=['rtl_id'], inplace=True)
            
        manifest.insert(0, "rtl_id", [f"RTL{i:06d}" for i in range(1, len(manifest) + 1)])

        # 5. Save Final Manifest
        manifest.to_csv(self.manifest_csv, index=False)
        logger.info(f"Saved {len(manifest)} files to {self.manifest_csv.name}")

        # 6. Generate Statistics
        verified_mask = manifest['is_verified'] == True
        inferred_mask = manifest['is_verified'] == False
        
        stats = {
            "inventory_files_initial": int(total_initial_files),
            "accepted_unique_files": int(len(manifest)),
            "rejected_files": int(len(rejected_files)),
            "duplicate_files": int(len(duplicate_report)),
            
            "trojan_verified": int(((manifest["binary_label"] == "Trojan") & verified_mask).sum()),
            "trojan_inferred": int(((manifest["binary_label"] == "Trojan") & inferred_mask).sum()),
            "clean_verified": int(((manifest["binary_label"] == "Clean") & verified_mask).sum()),
            "clean_inferred": int(((manifest["binary_label"] == "Clean") & inferred_mask).sum()),
            "unknown_files": int((manifest["binary_label"] == "Unknown").sum())
        }

        with self.stats_json.open("w", encoding="utf-8") as f:
            json.dump(stats, f, indent=4)
            
        logger.info(f"Saved dataset statistics to {self.stats_json.name}")

        # Summary Log
        logger.info("")
        logger.info("=" * 70)
        logger.info("Dataset Build Complete")
        logger.info("=" * 70)
        logger.info(f"Accepted         : {stats['accepted_unique_files']}")
        logger.info(f"Trojan (Verified): {stats['trojan_verified']}")
        logger.info(f"Trojan (Inferred): {stats['trojan_inferred']}")
        logger.info(f"Clean  (Verified): {stats['clean_verified']}")
        logger.info(f"Clean  (Inferred): {stats['clean_inferred']}")
        logger.info(f"Unknown          : {stats['unknown_files']}")
        logger.info("=" * 70)


def main():
    root = Path(__file__).resolve().parents[2]
    config = DatasetConfig.from_project_root(root)
    builder = DatasetBuilder(config)
    builder.run()

if __name__ == "__main__":
    main()