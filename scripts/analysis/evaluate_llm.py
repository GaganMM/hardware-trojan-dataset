import logging
import sys
import pandas as pd
from pathlib import Path
from sklearn.metrics import classification_report, confusion_matrix
import json

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.dataset.config import DatasetConfig

# ---------------------------------------------------------------------
# Logging Setup
# ---------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("LLMEvaluator")

def evaluate():
    root = Path(__file__).resolve().parents[2]
    config = DatasetConfig.from_project_root(root)
    
    gt_csv = config.metadata / "ground_truth.csv"
    predictions_csv = config.metadata / "qwen_predictions.csv"
    evaluation_json = config.metadata / "qwen_evaluation.json"
    
    if not gt_csv.exists() or not predictions_csv.exists():
        logger.error("Missing ground_truth.csv or qwen_predictions.csv")
        return
        
    logger.info("Loading ground truth and Qwen predictions...")
    gt_df = pd.read_csv(gt_csv)
    pred_df = pd.read_csv(predictions_csv)
    
    # Evaluate files that are in BOTH ground truth and predictions
    merged = pd.merge(
        gt_df[['sha256', 'label']], 
        pred_df[['sha256', 'qwen_label']], 
        on='sha256', 
        how='inner',
        suffixes=('_gt', '_llm')
    )
    
    if merged.empty:
        logger.error("No matching files found between ground truth and Qwen predictions.")
        return
        
    logger.info(f"Evaluating {len(merged)} files against the Ground Truth Set.")
    
    # Filter out Unknown predictions for strict metrics, or treat them as Clean/False Negative
    # To be rigorous, we treat "Unknown" as a failure to detect a Trojan (if it was a Trojan) 
    # or a failure to verify (if it was Clean). 
    # For classification_report we can just map Unknown to "Unknown" and let it handle 3 classes,
    # or map Unknown to Clean (since Trojan detection is the primary goal).
    # Let's map Unknown to Clean for binary classification purposes (Trojan vs Not-Trojan).
    
    y_true = merged['label'].apply(lambda x: 'Trojan' if x == 'Trojan' else 'Clean')
    y_pred = merged['qwen_label'].apply(lambda x: 'Trojan' if x == 'Trojan' else 'Clean')
    
    report_dict = classification_report(y_true, y_pred, labels=["Trojan", "Clean"], output_dict=True)
    report_str = classification_report(y_true, y_pred, labels=["Trojan", "Clean"])
    
    print("\n" + "=" * 60)
    print("HTBench Qwen Evaluation Report")
    print("=" * 60)
    print(report_str)
    
    print("\nConfusion Matrix:")
    print("Predicted ->  Trojan  Clean")
    cm = confusion_matrix(y_true, y_pred, labels=["Trojan", "Clean"])
    print(f"True Trojan: {cm[0][0]:7d} {cm[0][1]:7d}")
    print(f"True Clean : {cm[1][0]:7d} {cm[1][1]:7d}")
    print("=" * 60)
    
    # Save to JSON
    results = {
        "files_evaluated": len(merged),
        "true_positives": int(cm[0][0]),
        "false_negatives": int(cm[0][1]),
        "false_positives": int(cm[1][0]),
        "true_negatives": int(cm[1][1]),
        "metrics": report_dict
    }
    
    with open(evaluation_json, 'w') as f:
        json.dump(results, f, indent=2)
    logger.info(f"Saved evaluation report to {evaluation_json.name}")

if __name__ == "__main__":
    evaluate()
