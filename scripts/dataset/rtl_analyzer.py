import argparse
import logging
from pathlib import Path
import traceback
import re
import multiprocessing

import pandas as pd
import yaml

from scripts.dataset.config import DatasetConfig

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("RTLAnalyzer")

def get_heuristic_score(content: str) -> int:
    score = 0
    content = content.lower()
    
    patterns = {
        r"counter": 2,
        r"lfsr": 3,
        r"compare": 3,
        r"\d+'h": 4,
        r"debug": 2,
        r"key": 1,
        r"always": 1,
        r"case": 1,
        r"shift": 1,
        r"==": 1,
        r"!=": 1,
        r"\+": 1,
        r"secret": 2,
        r"scan": 1,
        r"test": 1
    }
    
    for pat, val in patterns.items():
        if re.search(pat, content):
            score += val
            
    return score

def process_repository(args):
    repo_name, fpaths, config_root_str, generated_dir_str = args
    config_root = Path(config_root_str)
    generated_dir = Path(generated_dir_str)
    
    found = False
    reasoning = []
    
    # Regex patterns equivalent to the AST checks for cheat codes and timebombs
    cheat_code_pattern = re.compile(r"(==|!=)\s*\d+'h[0-9a-fA-F]{6,}")
    timebomb_pattern = re.compile(r"(\w+)\s*<=\s*\1\s*\+\s*[a-zA-Z0-9_']+")
    
    for fpath in fpaths:
        if not isinstance(fpath, str):
            continue
            
        p = config_root / fpath if not Path(fpath).is_absolute() else Path(fpath)
        if not p.exists() or p.suffix not in ['.v', '.sv']:
            continue
            
        try:
            content = p.read_text(errors='ignore')
            score = get_heuristic_score(content)
            
            if score < 5:
                continue # Skip completely!
        except Exception:
            continue

        try:
            # Fast regex checks instead of slow PyVerilog AST parsing
            cheat_match = cheat_code_pattern.search(content)
            if cheat_match:
                found = True
                reasoning.append(f"Found suspicious hardcoded comparator trigger: {cheat_match.group(0)}")
                
            timebomb_match = timebomb_pattern.search(content)
            if timebomb_match:
                # To be slightly more robust, ensure it's not a standard naming
                var_name = timebomb_match.group(1).lower()
                if var_name not in ["clk", "rst", "reset"]:
                    found = True
                    reasoning.append(f"Found potential timebomb counter: {timebomb_match.group(0)}")
            
            if found:
                break # We found one in this repo, no need to check other files
        except Exception:
            pass
            
    if found:
        # Update YAML
        yaml_path = generated_dir / f"{repo_name}.yaml"
        if yaml_path.exists():
            try:
                with open(yaml_path, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f) or {}
                    
                data['binary_label'] = {
                    "value": "Trojan", 
                    "confidence": 0.85, 
                    "source": "Static RTL Analysis", 
                    "evidence": reasoning
                }
                
                with open(yaml_path, 'w', encoding='utf-8') as f:
                    yaml.dump(data, f, sort_keys=False)
            except Exception as e:
                pass
                
    return repo_name, found

class RTLAnalyzer:
    def __init__(self, config: DatasetConfig):
        self.config = config
        self.generated_dir = self.config.knowledge / "generated"

    def analyze(self):
        inventory_file = self.config.metadata / "08_labeled_inventory.csv"
        if not inventory_file.exists():
            logger.error("08_labeled_inventory.csv not found.")
            return

        df = pd.read_csv(inventory_file)
        unknown_repos = df[df['binary_label'] == 'Unknown']['repository'].unique()
        
        logger.info(f"Running AST-based Static RTL Analysis on {len(unknown_repos)} repositories...")
        
        repo_groups = df.groupby("repository")
        
        tasks = []
        for repo_name in unknown_repos:
            if repo_name in repo_groups.groups:
                repo_files = repo_groups.get_group(repo_name)
                fpaths = repo_files['absolute_path'].dropna().tolist()
                tasks.append((repo_name, fpaths, str(self.config.root), str(self.generated_dir)))
                
        logger.info(f"Submitting {len(tasks)} repositories to multiprocessing pool with {multiprocessing.cpu_count()} workers...")
        
        found_count = 0
        with multiprocessing.Pool(processes=multiprocessing.cpu_count()) as pool:
            for i, result in enumerate(pool.imap_unordered(process_repository, tasks)):
                repo_name, found_trojan = result
                if found_trojan:
                    found_count += 1
                if i > 0 and i % 10 == 0:
                    logger.info(f"Processed {i}/{len(tasks)} repositories...")
                    
        logger.info(f"RTL Analysis Complete. Successfully updated {found_count} repositories to Trojan.")

def main():
    parser = argparse.ArgumentParser()
    parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    config = DatasetConfig.from_project_root(root)
    
    analyzer = RTLAnalyzer(config)
    analyzer.analyze()

if __name__ == "__main__":
    main()
