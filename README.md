This report summarizes the objectives, challenges, implementations, and results of integrating Large Language Models (LLMs) into the Hardware Trojan dataset generation pipeline.

1. Project Objective
The primary goal was to drastically reduce the number of Unknown labels in the Hardware Trojan dataset (initially standing at 7,835 unknown files) by leveraging open-source LLMs to analyze Verilog code and output a Trojan or Clean classification.

2. Hardware Constraints & Strategy
All analysis was constrained by the local hardware: an NVIDIA MX250 GPU with 2GB of VRAM.

Large, high-parameter LLMs (e.g., Llama 3 8B) were immediately ruled out due to Out-Of-Memory (OOM) errors.
We strategically pivoted to using highly capable, small-parameter coding models running via Ollama.
Primary Model: qwen2.5-coder:1.5b (code comprehension, fits in 2GB VRAM).

3. Pipeline Implementation & Refactoring
The OOM Bottleneck
Initially, the llm_analyzer.py script attempted to concatenate all .v files within an entire repository and feed them to the LLM in a single prompt. This massively exceeded the context window limits of small models and caused silent failures and missing labels.

File-by-File Iteration
We refactored llm_analyzer.py to evaluate the dataset iteratively:

Per-File Analysis: The LLM now evaluates each .v file individually, keeping context windows small and preventing VRAM crashes.
Label Preservation: We implemented logic to ensure that if the LLM detects a Trojan in any file within a repository, a subsequent Clean file evaluation in the same repository does not overwrite the repository's Trojan label.
Automated Batch Processing
To safely process 7,835 files without crashing the system, we created run_all_llm_batches.py:

Processes files in strictly controlled batches (500 files at a time).
Automatically updates the YAML evidence files.
Re-runs the build_dataset.py pipeline after each batch to bake the new labels into the manifest.csv.

4. Full Dataset Labeling & Completion
Following the initial batches, the automated batch runner (run_all_llm_batches.py) was deployed to process the entirety of the remaining dataset.

Execution Challenges
During the execution of Batch 4, the local Ollama instance began experiencing heavy load, resulting in multiple Read timed out (read timeout=600) errors from the LLM API. However, the robust error-handling in the pipeline allowed it to recover, skip the severely degraded files, and continue processing the rest of the dataset without fully crashing.

Final Dataset Statistics
The script successfully churned through all remaining batches (processing approximately 500 files every 2-3 hours) until every single Unknown file was classified.

Final HTBench Label Summary:

Total RTL Files: 9,005
Trojan: 6,617
Clean: 2,371
Unknown: 0
The dataset is now labeled.


FLOWCHART:

                    Multiple Sources
                        ↓
                    Download / Extraction
                        ↓
                    Cleaning
                        ↓
                    Duplicate Removal
                        ↓
                    Unified Inventory
                        ↓
                    RTL Metadata Extraction
                        ↓
                    Knowledge Base
                        ↓
                    Rule-Based Semantic Labeling
                        ↓
                    07_enriched_inventory.csv
                        ↓
                    Unknowns
                        ↓
                    LLM begins here


 ┌────────────────────────────────────────────────────────┐
 │                   manifest.csv                         │
 │           (Start: 7,835 Unknown Files)                 │
 └─────────────────────────┬──────────────────────────────┘
                           │ 
             [ Reads Batches of 500 ]
                           ▼ 
 ┌────────────────────────────────────────────────────────┐
 │             run_all_llm_batches.py                     │
 │            ( Loop Controller)            │
 └─────────────────────────┬──────────────────────────────┘
                           │ 
               [ Feeds Unprocessed Files ]
                           ▼
 ┌────────────────────────────────────────────────────────┐
 │                 llm_analyzer.py                        │
 │                                                        │
 │ 1. Reads raw Verilog code from local file              │
 │ 2. Calls Ollama API (qwen2.5-coder:1.5b)               │
 │ 3. Writes Trojan/Clean decision to repo's .yaml file   │
 └─────────────────────────┬──────────────────────────────┘
                           │ 
               [ Outputs Generated YAMLs ]
                           ▼
 ┌────────────────────────────────────────────────────────┐
 │        labeler.py & build_dataset.py                   │
 │                                                        │
 │ 1. Reads all YAMLs in knowledge/generated/             │
 │ 2. Injects labels into 08_labeled_inventory.csv        │
 │ 3. Overwrites manifest.csv with updated 'Unknown' count│
 └─────────────────────────┬──────────────────────────────┘
                           │ 
    [ Are there any Unknowns left? (Yes) -> LOOP BACK ]
    [ Are there any Unknowns left? (No)  -> COMPLETE  ]
                           ▼
 ┌────────────────────────────────────────────────────────┐
 │                                                        │
 │             (0 Unknowns remaining)                     │
 └────────────────────────────────────────────────────────┘



