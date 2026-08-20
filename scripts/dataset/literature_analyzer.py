import argparse
import logging
import time
from pathlib import Path

import pandas as pd
import requests
import yaml

from scripts.dataset.config import DatasetConfig

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("LiteratureAnalyzer")

class OpenAlexLiteratureAnalyzer:
    def __init__(self, config: DatasetConfig):
        self.config = config
        self.generated_dir = self.config.knowledge / "generated"
        self.session = requests.Session()
        # Polite pool for OpenAlex
        self.session.headers.update({"User-Agent": "mailto:htbench@example.com"})
        
    def _search_openalex(self, query: str) -> dict:
        url = "https://api.openalex.org/works"
        params = {
            "search": query,
            "per-page": 5,
            "sort": "relevance_score:desc",
            "select": "id,title,abstract_inverted_index,concepts"
        }
        try:
            resp = self.session.get(url, params=params, timeout=10)
            if resp.status_code == 200:
                return resp.json().get("results", [])
            else:
                logger.warning(f"OpenAlex returned {resp.status_code}")
                return []
        except Exception as e:
            logger.error(f"Failed to query OpenAlex: {e}")
            return []
            
    def _reconstruct_abstract(self, inverted_index: dict) -> str:
        if not inverted_index:
            return ""
        word_index = []
        for word, positions in inverted_index.items():
            for pos in positions:
                word_index.append((pos, word))
        word_index.sort()
        return " ".join([w for _, w in word_index])

    def analyze(self):
        inventory_file = self.config.metadata / "08_labeled_inventory.csv"
        if not inventory_file.exists():
            logger.error("08_labeled_inventory.csv not found.")
            return

        df = pd.read_csv(inventory_file)
        # Find unknowns
        unknown_repos = df[df['binary_label'] == 'Unknown']['repository'].unique()
        
        logger.info(f"Analyzing {len(unknown_repos)} Unknown repositories via OpenAlex...")
        
        found_count = 0
        
        for i, repo_name in enumerate(unknown_repos):
            # Try to avoid rate limits (10/sec allowed, sleep 0.2s is 5/sec)
            time.sleep(0.2)
            
            # Simple query transformation: replace hyphens with spaces
            query_str = repo_name.replace("-", " ")
            
            # Too short queries are noisy
            if len(query_str) < 4:
                continue
                
            results = self._search_openalex(query_str)
            if not results:
                continue
                
            # Analyze results
            is_clean = False
            is_trojan = False
            reasoning = []
            
            for res in results:
                title = (res.get("title") or "").lower()
                abstract = self._reconstruct_abstract(res.get("abstract_inverted_index")).lower()
                
                text = title + " " + abstract
                
                # Check for "hardware trojan"
                if "hardware trojan" in text or "malicious" in text:
                    is_trojan = True
                    reasoning.append(f"Found paper '{title}' mentioning hardware trojans and '{repo_name}'.")
                    break
                    
                # Check for benchmark/clean
                if ("benchmark" in text or "open-source core" in text or "processor" in text) and repo_name.lower() in text:
                    is_clean = True
                    reasoning.append(f"Found paper '{title}' citing '{repo_name}' as a benchmark or core.")
                    break
                    
            yaml_path = self.generated_dir / f"{repo_name}.yaml"
            if yaml_path.exists() and (is_clean or is_trojan):
                with open(yaml_path, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f) or {}
                
                if is_trojan:
                    data['binary_label'] = {"value": "Trojan", "confidence": 0.8, "source": "Literature Search", "evidence": reasoning}
                elif is_clean:
                    data['binary_label'] = {"value": "Clean", "confidence": 0.7, "source": "Literature Search", "evidence": reasoning}
                
                with open(yaml_path, 'w', encoding='utf-8') as f:
                    yaml.dump(data, f, sort_keys=False)
                    
                found_count += 1
                logger.info(f"[{repo_name}] Updated label to {'Trojan' if is_trojan else 'Clean'} via Literature Search.")
                
            if i % 10 == 0 and i > 0:
                logger.info(f"Processed {i}/{len(unknown_repos)}...")
                
        logger.info(f"Literature Analysis Complete. Successfully updated {found_count} repositories.")


def main():
    parser = argparse.ArgumentParser()
    parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    config = DatasetConfig.from_project_root(root)
    
    analyzer = OpenAlexLiteratureAnalyzer(config)
    analyzer.analyze()

if __name__ == "__main__":
    main()
