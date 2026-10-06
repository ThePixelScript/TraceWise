# iTrust req2code Benchmark Variant

## 1. Dataset Identification & Provenance
* **Dataset Variant:** iTrust req2code benchmark variant sourced from the LiSSA ICSE 2025 replication package.
* **Source Repository:** [`ardoco/Replication-Package-ICSE25_LiSSA-Toward-Generic-Traceability-Link-Recovery-through-RAG`](https://github.com/ardoco/Replication-Package-ICSE25_LiSSA-Toward-Generic-Traceability-Link-Recovery-through-RAG)
* **Replication DOI:** [10.5281/zenodo.14714706](https://doi.org/10.5281/zenodo.14714706)
* **Repository Commit:** `a8e652f29bbdcc4bdcd3d98cd85aa4a37cb65480` (tagged `v1.0.0`)
* **Exact Dataset Subdirectory:** `LiSSA-RATLR-V2/lissa/datasets/req2code/iTrust/`
* **Canonical Checksum:**
  - `UC2JAVA.csv`: SHA-256 `36e57100b6fa0066252b0b147bc79f5424e1fe739ca4c50d66f67fbbba9a6acd`
  - `source_req.xml`: SHA-256 `2f2ffef238a2f59ddecaf59a88cd7d0fad890c0d7ea6725feff640cf46cc9026`
  - `target_JavaCode.xml`: SHA-256 `10b808194aca1f2f02e5d856bcb7996fddbc75aabb714f936a293064ad879cc2`

> [!IMPORTANT]
> **Variant Disclaimer:** Multiple processed variants of the iTrust dataset exist across the software engineering traceability literature (e.g., Asuncion et al. 2010, Gethers et al. 2011, TEFSE 2011, Ben Charrada et al., and historical CoEST dumps with varying use-case subsets and granularity definitions). TraceWise intentionally adopts the LiSSA ICSE 2025 `req2code` variant to ensure exact replication against modern benchmarks. **We do not claim equivalence with every published iTrust benchmark variant.**

## 2. Licensing & Redistribution Audit
* **LiSSA Replication Package License:** The tooling framework in the upstream replication repository is distributed under the **MIT License** (`Copyright (c) 2025 ArDoCo`).
* **Third-Party iTrust Dataset Provenance:** The underlying iTrust codebase and requirements originate from the North Carolina State University (NCSU, CSC326) course project and were later archived by the Center of Excellence for Software & Systems Traceability (CoEST). The raw requirement texts and Java source files bundled in the replication package do not contain an authoritative standalone license file.
* **Redistribution Policy:** Because third-party redistribution rights for the raw iTrust source files cannot be established confidently from upstream headers, TraceWise does not assert unrestricted redistribution rights. The raw data directories (`UC/`, `CC/`, `UC2JAVA.csv`, `trace_links.json`) are excluded from git tracking via `.gitignore`.
* **Placement & Automated Setup:** Users can obtain the dataset locally using the automated setup script (`python scripts/setup_itrust.py`) or by manually cloning the LiSSA ICSE 2025 replication package into `data/benchmarks/itrust/`.

## 3. Dataset Scale & Granularity
* **Characterization:** An external real-world traceability benchmark of moderate size relative to the current synthetic fixture.
* **Research Purpose:** External validation and independent ground truth, not proof of large-scale scalability.
* **Total Requirements:** 131 use-case scenario/exception files (`UC/UC*.txt`)
* **Source Classes:** 226 production Java classes (`CC/*.java`, single compilation units)
* **Gold-Standard Trace Links:** 286 unique links (`UC2JAVA.csv` / `trace_links.json`)
* **Granularity Alignment:** Use-case subflows are mapped to class compilation units via `FileChunker(use_stem_as_id=True)`, producing chunk IDs matching the class names in the gold standard (e.g., `AddPatientAction`).

## 4. Evaluation Query Denominator
The iTrust requirements corpus contains:
* **Total Requirements:** 131
* **Evaluable Requirements ($\ge 1$ gold link):** 105
* **Zero-Link Requirements ($0$ gold links):** 26

### Denominator Specification
* **MAP (Mean Average Precision):** Computed over the **105 evaluable requirements** ($N = 105$).
* **MRR (Mean Reciprocal Rank):** Computed over the **105 evaluable requirements** ($N = 105$).
* **Precision@k (P@1, P@3, P@5):** Averaged over the **105 evaluable requirements** ($N = 105$).
* **Recall@k (R@1, R@3, R@5):** Averaged over the **105 evaluable requirements** ($N = 105$).

Zero-link queries are excluded from ranking metrics according to the TraceWise evaluation protocol because recall is undefined when the gold relevant set is empty; including such queries would change the macro-averaging protocol. They are not silently included to artificially deflate or inflate performance.

## 5. Baseline Evaluation Results (Requirements $\to$ Source Code)

| Metric | B0 (TF-IDF) | B1 (BM25) | B2 (Semantic) |
| :--- | :---: | :---: | :---: |
| **MAP** | 0.3006 | **0.3718** | 0.0790 |
| **MRR** | 0.4194 | **0.5144** | 0.1441 |
| **P@1** | 0.2286 | **0.3524** | 0.0571 |
| **P@3** | 0.2413 | **0.2984** | 0.0571 |
| **P@5** | 0.2000 | **0.2190** | 0.0438 |
| **R@1** | 0.0895 | **0.1490** | 0.0162 |
| **R@3** | 0.2825 | **0.3554** | 0.0594 |
| **R@5** | 0.3913 | **0.4177** | 0.0832 |
| **Indexing Time** | 0.075s | 0.064s | 13.138s |
| **Query Time** | 0.380s | 0.339s | 3.191s |
| **Total Requirements** | 131 | 131 | 131 |
| **Evaluable Requirements (Denom)** | 105 | 105 | 105 |
| **Zero-Link Requirements** | 26 | 26 | 26 |
| **Source Classes** | 226 | 226 | 226 |
| **Gold Links** | 286 | 286 | 286 |

### B2 Interpretation
The current B2 configuration (`all-MiniLM-L6-v2` applied to TraceWise normalized requirement/class text) performs poorly on the selected iTrust benchmark. This reflects vocabulary mismatch between natural-language clinical flows and Java source identifiers without code-specific embedding adaptation or query reformulation; it should not be taken to infer that dense semantic retrieval in general fails.

## 6. Local Reproduction
```python
from tracewise.evaluation.manifest import BenchmarkProjectManifest
from tracewise.evaluation.adapters import ProjectIngestionAdapter
from tracewise.evaluation.multi_runner import MultiProjectBenchmarkRunner
from tracewise.retrieval.tfidf import TfidfRetriever
from tracewise.retrieval.bm25 import BM25Retriever
from tracewise.retrieval.semantic import SemanticRetriever

manifest = BenchmarkProjectManifest.from_file(
    "data/benchmarks/itrust/benchmark_manifest.json"
)
project = ProjectIngestionAdapter().ingest_project(manifest, validate=True)

runner = MultiProjectBenchmarkRunner([project], k_values=(1, 3, 5))
for name, retriever in [
    ("B0 (TF-IDF)", TfidfRetriever()),
    ("B1 (BM25)", BM25Retriever()),
    ("B2 (Semantic)", SemanticRetriever()),
]:
    result = runner.run(retriever)
    print(result.format_table())
```
