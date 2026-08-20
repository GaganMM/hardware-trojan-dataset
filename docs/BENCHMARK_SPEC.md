\# HTBench Specification v1.0



\## Overview



HTBench is an open, reproducible benchmark for Hardware Trojan detection and

multi-class classification from Verilog/SystemVerilog RTL.



The benchmark aggregates RTL from multiple trusted sources into a unified dataset

with standardized labels.



\---



\# Objectives



\- Build the largest publicly available RTL Hardware Trojan benchmark.

\- Support multi-class classification.

\- Support graph-based and transformer-based models.

\- Maintain complete source provenance.

\- Be fully reproducible.



\---



\# Supported Languages



\- Verilog (.v)

\- SystemVerilog (.sv)



Future



\- VHDL



\---



\# Label Taxonomy



Clean



HT1

Always-on / Combinational Functional Trojan



HT2

Triggered Functional Trojan



HT3

Information Leakage Trojan



HT4

Denial of Service Trojan



\---



\# Three-Tier Source Policy



\## Tier 1



Official Benchmark Datasets



Examples



\- Trust-Hub

\- Trust-Hub Mirrors

\- RISC-V Web3

\- TrojanBench



Highest priority.



\---



\## Tier 2



Academic Repositories



Repositories accompanying peer-reviewed publications.



Sources include



\- IEEE HOST

\- DAC

\- ICCAD

\- DATE

\- ASP-DAC

\- ISCAS



Only repositories containing synthesizable RTL are accepted.



\---



\## Tier 3



Open-source RTL



Examples



\- OpenTitan

\- Ibex

\- PicoRV32

\- ZipCPU

\- SERV

\- OpenCores

\- LiteX



Used primarily for Clean samples.



\---



\# Inclusion Rules



Include



✓ Synthesizable RTL



✓ Verilog



✓ SystemVerilog



✓ Documented Trojan implementations



✓ Research-quality RTL



Exclude



✗ Testbenches



✗ Simulation files



✗ Documentation



✗ Generated files



✗ Temporary files



✗ Duplicate modules



\---



\# Dataset Layout



HTBench/



&#x20;   manifest.csv



&#x20;   sources.csv



&#x20;   data/



&#x20;       TrustHub/



&#x20;       RISCV-Web3/



&#x20;       Academic/



&#x20;       OpenRTL/



\---



\# Manifest Schema



sample\_id



source



family



module\_name



file\_path



label



\---



\# Source Schema



source\_id



source\_name



tier



category



url



status



\---



\# Naming Convention



sample\_id



archive\_\_module



Example



AES-T100\_\_aes\_128



RS232-T400\_\_uart



IBEX\_\_ibex\_core



\---



\# Duplicate Policy



Duplicates are identified by



\- identical RTL hash

\- identical module name

\- identical functionality



Only one copy is retained.



\---



\# Split Policy



Train



Validation



Test



Must preserve



\- label balance



\- family diversity



\- source diversity



\---



\# Benchmark Goals



Version 1



>1000 Clean



>250 HT1



>250 HT2



>250 HT3



>250 HT4



Version 2



>5000 Total Samples



Version 3



Support VHDL



Support gate-level netlists



Support sequential Trojan localization



\---



\# Future Extensions



\- Trojan localization



\- Explainability



\- Gate-level graphs



\- AST graphs



\- Semantic graphs



\- LLM explanations



\- Agentic benchmark builder



