import argparse
import collections
import copy
import csv
import json
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

import yaml

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("RuleEngine")


# ============================================================================
# M1: CORE MODELS & DATACLASSES
# ============================================================================

@dataclass
class Evidence:
    """Evidence supporting a specific label."""
    field: str
    matched_value: str
    rule_name: str
    snippet: Optional[str] = None
    line_number: Optional[int] = None

@dataclass
class Provenance:
    """Tracks how a specific field was inferred."""
    value: str
    confidence: float
    source: str
    evidence: List[Evidence] = field(default_factory=list)

@dataclass
class RuleResult:
    """The outcome of a rule execution."""
    inferred_fields: Dict[str, Provenance] = field(default_factory=dict)
    
    def add(self, field_name: str, value: str, confidence: float, source: str, evidence: Evidence):
        if field_name not in self.inferred_fields:
            self.inferred_fields[field_name] = Provenance(value=value, confidence=confidence, source=source)
        self.inferred_fields[field_name].evidence.append(evidence)

@dataclass
class Repository:
    """Object model representing an RTL repository."""
    name: str
    path: Path
    files: List[Path] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    existing_labels: Dict[str, Any] = field(default_factory=dict)
    
    def get_file_contents(self, file_ext: tuple = ('.v', '.sv', '.vhdl', '.vhd')) -> Dict[str, str]:
        """Returns the contents of HDL files for scanning."""
        contents = {}
        for f in self.files:
            if f.suffix in file_ext:
                try:
                    contents[f.name] = f.read_text(encoding='utf-8', errors='ignore')
                except Exception:
                    pass
        return contents


# ============================================================================
# M2: MATCHER FRAMEWORK
# ============================================================================

class Matcher:
    """Base class for rule matchers."""
    def match(self, repo: Repository) -> List[Evidence]:
        raise NotImplementedError

class ExactMatcher(Matcher):
    def __init__(self, target_field: str, keyword: str, rule_name: str):
        self.target_field = target_field
        self.keyword = keyword
        self.rule_name = rule_name
        
    def match(self, repo: Repository) -> List[Evidence]:
        evidence = []
        for filename, content in repo.get_file_contents().items():
            if self.keyword in content:
                evidence.append(Evidence(self.target_field, self.keyword, self.rule_name, snippet=f"Found in {filename}"))
        return evidence

class PrefixMatcher(Matcher):
    def __init__(self, target_field: str, prefix: str, rule_name: str):
        self.target_field = target_field
        self.prefix = prefix
        self.rule_name = rule_name
        
    def match(self, repo: Repository) -> List[Evidence]:
        evidence = []
        for filename, content in repo.get_file_contents().items():
            for line in content.splitlines():
                if line.strip().startswith(self.prefix):
                    evidence.append(Evidence(self.target_field, self.prefix, self.rule_name, snippet=f"Matched prefix in {filename}"))
                    break
        return evidence

class SuffixMatcher(Matcher):
    def __init__(self, target_field: str, suffix: str, rule_name: str):
        self.target_field = target_field
        self.suffix = suffix
        self.rule_name = rule_name
        
    def match(self, repo: Repository) -> List[Evidence]:
        evidence = []
        for filename, content in repo.get_file_contents().items():
            for line in content.splitlines():
                if line.strip().endswith(self.suffix):
                    evidence.append(Evidence(self.target_field, self.suffix, self.rule_name, snippet=f"Matched suffix in {filename}"))
                    break
        return evidence

class ContainsMatcher(Matcher):
    def __init__(self, target_field: str, keyword: str, rule_name: str):
        self.target_field = target_field
        self.keyword = keyword
        self.rule_name = rule_name
        
    def match(self, repo: Repository) -> List[Evidence]:
        evidence = []
        for filename, content in repo.get_file_contents().items():
            if self.keyword in content:
                evidence.append(Evidence(self.target_field, self.keyword, self.rule_name, snippet=f"Found in {filename}"))
        return evidence

class RegexMatcher(Matcher):
    def __init__(self, target_field: str, pattern: str, rule_name: str):
        self.target_field = target_field
        self.pattern = re.compile(pattern)
        self.rule_name = rule_name
        
    def match(self, repo: Repository) -> List[Evidence]:
        evidence = []
        for filename, content in repo.get_file_contents().items():
            matches = self.pattern.finditer(content)
            for m in matches:
                evidence.append(Evidence(self.target_field, m.group(0), self.rule_name, snippet=f"Matched in {filename}"))
        return evidence

class FilenameMatcher(Matcher):
    def __init__(self, target_field: str, pattern: str, rule_name: str):
        self.target_field = target_field
        self.pattern = re.compile(pattern)
        self.rule_name = rule_name

    def match(self, repo: Repository) -> List[Evidence]:
        evidence = []
        for f in repo.files:
            if self.pattern.search(f.name):
                evidence.append(Evidence(self.target_field, f.name, self.rule_name, snippet=f"Filename matched"))
        return evidence

class ModuleNameMatcher(Matcher):
    def __init__(self, target_field: str, pattern: str, rule_name: str):
        self.target_field = target_field
        self.pattern = re.compile(pattern)
        self.rule_name = rule_name
        
    def match(self, repo: Repository) -> List[Evidence]:
        evidence = []
        module_pattern = re.compile(r'module\s+([a-zA-Z0-9_]+)')
        for filename, content in repo.get_file_contents().items():
            for m in module_pattern.finditer(content):
                mod_name = m.group(1)
                if self.pattern.search(mod_name):
                    evidence.append(Evidence(self.target_field, mod_name, self.rule_name, snippet=f"Matched module {mod_name} in {filename}"))
        return evidence

class MetadataMatcher(Matcher):
    def __init__(self, target_field: str, metadata_key: str, expected_value: str, rule_name: str):
        self.target_field = target_field
        self.metadata_key = metadata_key
        self.expected_value = expected_value
        self.rule_name = rule_name

    def match(self, repo: Repository) -> List[Evidence]:
        val = repo.metadata.get(self.metadata_key)
        if val == self.expected_value:
            return [Evidence(self.target_field, str(val), self.rule_name, snippet="Matched repository metadata")]
        return []


# ============================================================================
# M3: RULE REGISTRY
# ============================================================================

class RuleRegistry:
    """Central registry for all extraction rules."""
    def __init__(self):
        self.rules = []
        
    def register(self, source: str, confidence: float, inferred_value: str, matcher: Matcher):
        self.rules.append({
            'source': source,
            'confidence': confidence,
            'value': inferred_value,
            'matcher': matcher
        })
        
    def get_all_rules(self):
        return self.rules

# Precedence levels
SOURCE_PRECEDENCE = {
    "Manual": 100,
    "TrustHub": 90,
    "Generated": 80,
    "Static Analyzer": 70,
    "Graph Similarity": 60,
    "Repository Rule": 50,
    "LLM": 40
}


# ============================================================================
# M4: CONFIDENCE & CONFLICT ENGINE
# ============================================================================

class ExecutionEngine:
    def __init__(self, registry: RuleRegistry):
        self.registry = registry
        
    def execute(self, repo: Repository) -> RuleResult:
        result = RuleResult()
        
        # Collect all triggers
        raw_triggers = collections.defaultdict(list)
        for rule in self.registry.get_all_rules():
            matcher = rule['matcher']
            evidence_list = matcher.match(repo)
            if evidence_list:
                for ev in evidence_list:
                    raw_triggers[matcher.target_field].append((rule, ev))
                    
        # Aggregate and resolve conflicts
        for field_name, triggers in raw_triggers.items():
            # Group by value to compute aggregated confidence
            value_candidates = collections.defaultdict(list)
            for rule, ev in triggers:
                value_candidates[rule['value']].append((rule, ev))
                
            best_value = None
            best_score = -1
            best_source = None
            best_evidence = []
            
            for value, items in value_candidates.items():
                confidences = [item[0]['confidence'] for item in items]
                agg_conf = 1.0
                for c in confidences:
                    agg_conf *= (1.0 - c)
                agg_conf = 1.0 - agg_conf
                
                highest_precedence_source = max(items, key=lambda x: SOURCE_PRECEDENCE.get(x[0]['source'], 0))[0]['source']
                score = SOURCE_PRECEDENCE.get(highest_precedence_source, 0) + agg_conf
                
                if score > best_score:
                    best_score = score
                    best_value = value
                    best_source = highest_precedence_source
                    best_evidence = [item[1] for item in items]
                    best_conf = round(agg_conf, 2)
                    
            if best_value:
                for ev in best_evidence:
                    result.add(field_name, best_value, best_conf, best_source, ev)
                    
        return result


# ============================================================================
# M7: VALIDATION & QUALITY ASSURANCE FRAMEWORK
# ============================================================================

# Validator 2: Enum Validation Schemas
VALID_ENUMS = {
    "trojan_type": ["Information Leakage", "Denial of Service", "Functional Modification", "Performance Degradation", "Reliability", "Unknown"],
    "binary_label": ["Trojan", "Clean", "Unknown"]
}

class ValidationEngine:
    def __init__(self):
        self.issues = collections.defaultdict(list)
        
    def run_all(self, repos: List[Repository], results: Dict[str, RuleResult]):
        self.issues.clear()
        for repo in repos:
            result = results.get(repo.name)
            if not result:
                continue
            
            self._validator_1_schema(repo, result)
            self._validator_2_enum(repo, result)
            self._validator_3_cross_field(repo, result)
            self._validator_5_confidence_audit(repo, result)
            
        self._validator_4_duplicate_knowledge(results)
        self._validator_6_coverage(repos, results)
        self._validator_8_completeness(repos, results)
        
    def _validator_1_schema(self, repo: Repository, result: RuleResult):
        for field, prov in result.inferred_fields.items():
            if prov.value is None or prov.value == "":
                self.issues[repo.name].append(f"Validator 1 (Schema): Missing value for {field}")
            if not (0.0 <= prov.confidence <= 1.0):
                self.issues[repo.name].append(f"Validator 1 (Schema): Confidence {prov.confidence} out of range 0..1 for {field}")

    def _validator_2_enum(self, repo: Repository, result: RuleResult):
        for field, prov in result.inferred_fields.items():
            if field in VALID_ENUMS and prov.value not in VALID_ENUMS[field]:
                self.issues[repo.name].append(f"Validator 2 (Enum): Invalid value '{prov.value}' for {field}. Allowed: {VALID_ENUMS[field]}")

    def _validator_3_cross_field(self, repo: Repository, result: RuleResult):
        fields = result.inferred_fields
        if "binary_label" in fields and "trojan_type" in fields:
            bl = fields["binary_label"].value
            tt = fields["trojan_type"].value
            if bl == "Clean" and tt != "Unknown" and tt != "":
                self.issues[repo.name].append(f"Validator 3 (Cross-field): Conflict! binary_label={bl} but trojan_type={tt}")

    def _validator_4_duplicate_knowledge(self, results: Dict[str, RuleResult]):
        pass

    def _validator_5_confidence_audit(self, repo: Repository, result: RuleResult):
        for field, prov in result.inferred_fields.items():
            if prov.confidence > 0.95 and len(prov.evidence) == 1:
                self.issues[repo.name].append(f"Validator 5 (Confidence): Suspiciously high confidence ({prov.confidence}) with only 1 piece of evidence for {field}")

    def _validator_6_coverage(self, repos: List[Repository], results: Dict[str, RuleResult]):
        total = len(repos)
        known = sum(1 for r in repos if r.name in results and results[r.name].inferred_fields.get('binary_label', Provenance("Unknown",0,"")).value != "Unknown")
        
        self.coverage_stats = {
            "Total Repositories": total,
            "Known": known,
            "Unknown": total - known,
        }
        
        field_counts = collections.defaultdict(int)
        for res in results.values():
            for f, p in res.inferred_fields.items():
                if p.value != "Unknown":
                    field_counts[f] += 1
                
        self.coverage_stats["Field Coverage"] = {k: f"{(v/total if total > 0 else 0):.1%}" for k, v in field_counts.items()}

    def _validator_8_completeness(self, repos: List[Repository], results: Dict[str, RuleResult]):
        target_fields = ["family", "application", "protocol", "trojan_type", "trigger_type", "payload_type"]
        self.completeness_scores = {}
        for repo in repos:
            res = results.get(repo.name)
            if not res:
                self.completeness_scores[repo.name] = "0%"
                continue
            
            filled = sum(1 for f in target_fields if f in res.inferred_fields and res.inferred_fields[f].value != "Unknown")
            self.completeness_scores[repo.name] = f"{(filled/len(target_fields)):.0%}"
            
    def generate_review_queue(self, output_path: Path):
        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(["Repository", "Reason", "Suggested Action"])
            for repo_name, repo_issues in self.issues.items():
                for issue in repo_issues:
                    action = "Manual Review"
                    if "Confidence" in issue: action = "Verify evidence"
                    if "Cross-field" in issue: action = "Resolve conflict"
                    writer.writerow([repo_name, issue, action])

    def generate_health_report(self, output_path: Path):
        report = [
            "# Dataset Health Report",
            "Generated automatically by HTBench Validation Engine.",
            "",
            "## Coverage Analysis"
        ]
        if hasattr(self, 'coverage_stats'):
            for k, v in self.coverage_stats.items():
                if isinstance(v, dict):
                    report.append(f"\n### {k}")
                    for fk, fv in v.items():
                        report.append(f"- {fk}: {fv}")
                else:
                    report.append(f"- **{k}**: {v}")
                    
        report.append("\n## Completeness Scores (Sample)")
        if hasattr(self, 'completeness_scores'):
            for k, v in list(self.completeness_scores.items())[:10]:
                report.append(f"- {k}: {v}")
                
        report.append(f"\n## Open Issues")
        report.append(f"Found {sum(len(v) for v in self.issues.values())} validation issues across {len(self.issues)} repositories. Check `review_queue.csv`.")
        
        output_path.write_text("\n".join(report))


# ============================================================================
# M5: YAML EXPORTER
# ============================================================================

def export_yaml(repo_name: str, result: RuleResult, output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    
    yaml_data = {}
    for field, prov in result.inferred_fields.items():
        yaml_data[field] = {
            "value": prov.value,
            "confidence": prov.confidence,
            "source": prov.source,
            "evidence": list(set([f"{e.rule_name}: {e.snippet} ({e.matched_value})" for e in prov.evidence]))
        }
        
    with open(output_dir / f"{repo_name}.yaml", "w", encoding='utf-8') as f:
        yaml.dump(yaml_data, f, sort_keys=False, default_flow_style=False)


# ============================================================================
# INTEGRATION AND CLI
# ============================================================================

def register_default_rules(registry: RuleRegistry):
    """Register built-in baseline rules."""
    registry.register(
        source="Repository Rule",
        confidence=0.9,
        inferred_value="AES",
        matcher=FilenameMatcher("family", r"aes_.*\.v", "AES Filename Rule")
    )
    registry.register(
        source="Repository Rule",
        confidence=0.8,
        inferred_value="Information Leakage",
        matcher=ExactMatcher("trojan_type", "leakage", "Leakage Keyword Rule")
    )
    registry.register(
        source="Static Analyzer",
        confidence=0.85,
        inferred_value="Sequential Counter",
        matcher=RegexMatcher("trigger_type", r"always @\(posedge.*count <=", "Counter Trigger Rule")
    )
    registry.register(
        source="Manual",
        confidence=1.0,
        inferred_value="Clean",
        matcher=ExactMatcher("binary_label", "verified_clean_core", "Clean Core Tag")
    )


def main():
    parser = argparse.ArgumentParser(description="HTBench Rule Engine v2")
    parser.add_argument("--repo-dir", type=str, required=True, help="Path to repositories directory")
    parser.add_argument("--output-dir", type=str, default="knowledge/generated", help="Path to output YAMLs")
    parser.add_argument("--report-dir", type=str, default="reports", help="Path for validation reports")
    args = parser.parse_args()

    repo_dir = Path(args.repo_dir)
    out_dir = Path(args.output_dir)
    report_dir = Path(args.report_dir)
    
    report_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Initializing Rule Engine v2...")
    registry = RuleRegistry()
    register_default_rules(registry)
    
    engine = ExecutionEngine(registry)
    validator = ValidationEngine()
    
    repos = []
    results = {}
    
    # Discovery
    logger.info(f"Scanning repositories in {repo_dir}")
    if repo_dir.exists():
        for d in repo_dir.iterdir():
            if d.is_dir():
                files = list(d.rglob("*"))
                repo = Repository(name=d.name, path=d, files=files)
                repos.append(repo)
    else:
        logger.error(f"Directory {repo_dir} not found.")
        return

    # Execution
    logger.info("Executing rules...")
    for repo in repos:
        res = engine.execute(repo)
        results[repo.name] = res
        export_yaml(repo.name, res, out_dir)
        
    # Validation
    logger.info("Running Validation & QA Framework...")
    validator.run_all(repos, results)
    
    # Reports
    validator.generate_review_queue(report_dir / "review_queue.csv")
    validator.generate_health_report(report_dir / "dataset_health_report.md")
    
    logger.info(f"Complete. Processed {len(repos)} repositories. Reports in {report_dir}")


if __name__ == "__main__":
    main()
