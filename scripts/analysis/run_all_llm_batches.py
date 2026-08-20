import subprocess
import pandas as pd
import logging
import time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("BatchRunner")

def run_batches():
    manifest_path = Path("metadata/manifest.csv")
    
    while True:
        if not manifest_path.exists():
            logger.error("Manifest not found. Ensure dataset is built.")
            break
            
        df = pd.read_csv(manifest_path)
        unknown_count = len(df[df['binary_label'] == 'Unknown'])
        logger.info(f"Current Unknowns: {unknown_count}")
        
        if unknown_count == 0:
            logger.info("All files have been analyzed!")
            break
            
        logger.info("Starting next batch of 500 files...")
        
        # 1. Run LLM Analyzer
        result = subprocess.run(["python", "-m", "scripts.analysis.llm_analyzer", "--model", "qwen2.5-coder:1.5b", "--limit", "500"])
        if result.returncode != 0:
            logger.error("LLM Analyzer failed. Stopping batch process.")
            break
            
        # 2. Run Labeler
        logger.info("Running labeler to integrate batch results...")
        result = subprocess.run(["python", "-m", "scripts.dataset.labeler"])
        if result.returncode != 0:
            logger.error("Labeler failed. Stopping batch process.")
            break
            
        # 3. Run Builder
        logger.info("Running dataset builder...")
        result = subprocess.run(["python", "-m", "scripts.dataset.build_dataset"])
        if result.returncode != 0:
            logger.error("Builder failed. Stopping batch process.")
            break
            
        logger.info("Batch integrated successfully.\n")
        time.sleep(5) # short pause between batches

if __name__ == "__main__":
    run_batches()
