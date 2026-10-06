# TraceWise

An intelligent platform for automated requirements traceability and change impact analysis across software artifacts.

## Status

Active development:
- **Milestone 0 (Project Foundation):** Complete
- **Milestone 1A (Artifact Ingestion):** Complete
- **Milestone 1B (Python Artifact Chunk Extraction):** Complete
- **Synthetic Evaluation Fixtures (PR #1):** Complete
- **Milestone 1C (Text Preprocessing):** Complete
- **Milestone 2A (Retrieval Contracts & Candidate Model):** Complete
- **Milestone 2B (TF-IDF + Cosine Retrieval Baseline):** Complete
- **Milestone 3A (Evaluation Metrics & Ground-Truth Benchmark Harness):** Complete
- **Milestone 3B (BM25 Lexical Retrieval Baseline):** Complete
- **Milestone 4A (Dense Semantic Retrieval Baseline):** Complete
- **Milestone 4B (Real-Project Benchmark Infrastructure):** Complete
- **Milestone 4C (First Real-Project Dataset Integration - iTrust ONLY):** Complete
- **Milestone 4C-R (Methodology Corrections ONLY):** Complete
- **Milestone 4D (Second External Benchmark Integration - eTour ONLY):** Complete

## Project Scope

TraceWise investigates automated and semi-automated traceability between:

- Requirements
- Source Code
- Test Cases

The system will also investigate change impact analysis using recovered trace links and software dependencies.

## Architecture & Project Structure

The repository follows a standard `src` layout under `src/tracewise/`:

- `src/tracewise/`: Core Python package
  - `models/`: Domain models (`Artifact`, `ArtifactChunk`, `ArtifactType`, `TraceLink`, `TraceLinkStatus`)
  - `ingestion/`: Filesystem traversal, path normalization, rule matching, and structural chunkers (`ArtifactIngestor`, `PythonChunker`)
  - `preprocessing/`: Text normalization, code tokenization, and `ProcessedText` representation (`src/tracewise/preprocessing/`, Milestone 1C - Complete)
  - `retrieval/`: Candidate retrieval contracts (`BaseRetriever`, `RetrievalCandidate`) and retrieval baselines (`TfidfRetriever` [B0], `BM25Retriever` [B1], `SemanticRetriever` [B2])
  - `evaluation/`: IR metrics, dataset manifests, integrity validators, ground-truth adapters, and multi-project benchmark execution (`BenchmarkProject`, `MultiProjectBenchmarkRunner`, Milestone 4B - Complete)
  - `ranking/`: Candidate ranking and score combination
  - `cia/`: Change impact analysis engine
- `data/`: Dataset fixtures, benchmarks, and ground-truth traceability links (`data/fixtures/sample_project/`)
- `experiments/`: Benchmark evaluation harnesses and metric calculators
- `tests/`: Automated unit and integration test suite
- `docs/`: Technical specifications and architectural documentation

## Development Setup

### Requirements

- Python 3.10+

### Installation

```bash
# Create and activate a virtual environment
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

# Install package with development dependencies
pip install -e ".[dev]"
```

### Testing & Linting

```bash
# Run unit tests
pytest

# Check code style and lint rules
ruff check .

# Check code formatting
ruff format --check .
```

## Retrieval Baselines

TraceWise uses candidate retrieval to generate ranked hypotheses across software artifacts:
- **`TfidfRetriever` [B0]:** Lexical retrieval baseline using sublinear term frequency ($1 + \ln(\text{count})$), smoothed inverse document frequency ($\ln(1 + N/\text{DF})$), and cosine similarity over pre-normalized document vectors.
- **`BM25Retriever` [B1]:** Classical probabilistic BM25 baseline with configurable parameters ($k_1=1.5, b=0.75$), computing length-normalized probabilistic relevance scores.
- **`SemanticRetriever` [B2]:** Dense semantic embedding baseline using pretrained Transformer sentence/code embeddings (mean-pooled, cosine similarity) without fine-tuning on ground truth.
- **`StructuralRetriever` [B3]:** Structure-guided identifier + dependency retrieval baseline. Requirement tokens are matched only against declared structural entity/identifier terms to create seed activation, and graph dependencies propagate that seed signal across an intra-code dependency graph with normalized 1-hop diffusion ($\alpha=0.5$). Full code-text lexical retrieval is not used; dense embeddings are not used; LLM/RAG is not used. Note: B3 is not a completely lexical-free method because seed activation relies on matching requirement terms to entity identifiers. Reference edges are inferred from explicit symbol-name occurrences in source text using deterministic matching, an approximation of true program dependencies that may include false structural edges from textual occurrences rather than a compiler-verified call graph. $\alpha = 0.5$ is a fixed, a priori equal-weight design choice between direct identifier-based seed activation and structural neighbor diffusion, and was not tuned using benchmark ground truth.
- **Hypotheses vs. Ground Truth:** Candidate retrieval produces ranked candidate matches (`RetrievalCandidate`). Candidate generation is strictly distinct from ground-truth creation, validation, and lifecycle management.


- **Separation of Evaluation:** Evaluation against benchmark ground truth remains an independent layer.

## Benchmark Datasets

TraceWise maintains a strict methodological distinction between controlled synthetic fixtures and external empirical benchmarks:

### 1. Controlled Synthetic Benchmark (`sample_project`)
- **Purpose:** Development fixture and regression test suite.
- **Scope:** 10 requirements, 26 source code AST chunks, 16 ground-truth links.
- **Frozen Baselines (Requirements → Source Code):**
  - **B0 (TF-IDF):** MAP = 0.7485, MRR = 0.8500, P@1 = 0.8000, R@1 = 0.5500
  - **B1 (BM25):** MAP = 0.7030, MRR = 0.8033, P@1 = 0.7000, R@1 = 0.5000
  - **B2 (Semantic):** MAP = 0.7350, MRR = 0.8500, P@1 = 0.7000, R@1 = 0.4500
  - **B3 (Structural):** MAP = 0.3977, MRR = 0.4333, P@1 = 0.2000, R@1 = 0.1000


### 2. External Benchmark (`itrust`)
- **Variant:** iTrust req2code benchmark variant sourced from the LiSSA ICSE 2025 replication package (commit `a8e652f29bbdcc4bdcd3d98cd85aa4a37cb65480`, DOI: [10.5281/zenodo.14714706](https://doi.org/10.5281/zenodo.14714706)). Multiple processed variants exist in the literature; TraceWise does not claim equivalence with every published variant.
- **Dataset Scale:** An external real-world traceability benchmark of moderate size relative to the current synthetic fixture (external validation, not proof of large-scale scalability).
- **Measured Dimensions:**
  - Total Requirements = 131 (`UC/*.txt`)
  - Evaluable Requirements = 105 (with $\ge 1$ gold link)
  - Zero-Link Requirements = 26 (with $0$ gold links)
  - Source Classes = 226 (`CC/*.java`, single compilation units)
  - Gold Links = 286 unique links (`UC2JAVA.csv`)
- **Evaluation Denominator:** Ranking metrics (MAP, MRR, P@k, R@k) are computed strictly over the 105 evaluable requirements with $\ge 1$ gold link; the 26 zero-link requirements are excluded from ranking metrics according to the TraceWise evaluation protocol.
- **Baseline Results (Requirements → Source Code):**
  - **B0 (TF-IDF):** MAP = 0.3006, MRR = 0.4194, P@1 = 0.2286, R@1 = 0.0895
  - **B1 (BM25):** MAP = 0.3718, MRR = 0.5144, P@1 = 0.3524, R@1 = 0.1490
  - **B2 (Semantic):** MAP = 0.0790, MRR = 0.1441, P@1 = 0.0571, R@1 = 0.0162
  - **B3 (Structural):** MAP = 0.1770, MRR = 0.2675, P@1 = 0.0857, R@1 = 0.0247
- **B2 & B3 Interpretation:** The current B2 configuration (`all-MiniLM-L6-v2`) performs poorly on iTrust due to the clinical-to-code vocabulary gap without domain adaptation. In contrast, B3 provides an isolated test of structure-guided retrieval. Its mixed performance indicates that structural information contains useful signal (achieving MAP = 0.1770 on iTrust, exceeding B2's 0.0790) but is insufficient as a standalone retrieval mechanism on these benchmarks.



### 3. External Benchmark 2 (`etour`)
- **Variant:** eTour req2code benchmark variant sourced from the LiSSA ICSE 2025 replication package (commit `a8e652f29bbdcc4bdcd3d98cd85aa4a37cb65480`, DOI: [10.5281/zenodo.14714706](https://doi.org/10.5281/zenodo.14714706)). Multiple processed variants exist in the literature; TraceWise does not claim equivalence with every published variant.
- **Dataset Scale:** An external real-world traceability benchmark of moderate size relative to the current synthetic fixture (external validation, not proof of large-scale scalability).
- **Measured Dimensions:**
  - Total Requirements = 58 (`UC/*.txt`)
  - Evaluable Requirements = 57 (with $\ge 1$ gold link)
  - Zero-Link Requirements = 1 (`UC37`, with $0$ gold links)
  - Source Classes = 116 (`CC/*.java`, single compilation units)
  - Gold Links = 308 unique links (`UC2CC.csv`)
- **Evaluation Denominator:** Ranking metrics (MAP, MRR, P@k, R@k) are computed strictly over the 57 evaluable requirements with $\ge 1$ gold link; the 1 zero-link requirement is excluded from ranking metrics according to the TraceWise evaluation protocol.
- **Baseline Results (Requirements → Source Code):**
  - **B0 (TF-IDF):** MAP = 0.3878, MRR = 0.6636, P@1 = 0.5263, R@1 = 0.1211
  - **B1 (BM25):** MAP = 0.2987, MRR = 0.5994, P@1 = 0.4035, R@1 = 0.0712
  - **B2 (Semantic):** MAP = 0.4329, MRR = 0.6918, P@1 = 0.5439, R@1 = 0.1129
  - **B3 (Structural):** MAP = 0.2755, MRR = 0.3210, P@1 = 0.1228, R@1 = 0.0319


### 4. Cross-Project Empirical Comparison

| Project | Model | MAP | MRR | P@1 | P@3 | P@5 | R@1 | R@3 | R@5 | Total Reqs | Eval Reqs (Denom) | Zero-Link Reqs | Source Classes | Gold Links |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `sample_project` | `tfidf` | 0.7485 | 0.8500 | 0.8000 | 0.3667 | 0.2400 | 0.5500 | 0.7500 | 0.8000 | 10 | 10 | 0 | 26 | 16 |
| `sample_project` | `bm25` | 0.7030 | 0.8033 | 0.7000 | 0.3333 | 0.2600 | 0.5000 | 0.7000 | 0.8500 | 10 | 10 | 0 | 26 | 16 |
| `sample_project` | `semantic` | 0.7350 | 0.8500 | 0.7000 | 0.4333 | 0.2800 | 0.4500 | 0.8500 | 0.9000 | 10 | 10 | 0 | 26 | 16 |
| `sample_project` | `structural` | 0.3977 | 0.4333 | 0.2000 | 0.2000 | 0.2200 | 0.1000 | 0.4000 | 0.7000 | 10 | 10 | 0 | 26 | 16 |
| `itrust` | `tfidf` | 0.3006 | 0.4194 | 0.2286 | 0.2413 | 0.2000 | 0.0895 | 0.2825 | 0.3913 | 131 | 105 | 26 | 226 | 286 |
| `itrust` | `bm25` | 0.3718 | 0.5144 | 0.3524 | 0.2984 | 0.2190 | 0.1490 | 0.3554 | 0.4177 | 131 | 105 | 26 | 226 | 286 |
| `itrust` | `semantic` | 0.0790 | 0.1441 | 0.0571 | 0.0571 | 0.0438 | 0.0162 | 0.0594 | 0.0832 | 131 | 105 | 26 | 226 | 286 |
| `itrust` | `structural` | 0.1770 | 0.2675 | 0.0857 | 0.1333 | 0.1238 | 0.0247 | 0.1569 | 0.2316 | 131 | 105 | 26 | 226 | 286 |
| `etour` | `tfidf` | 0.3878 | 0.6636 | 0.5263 | 0.4386 | 0.3509 | 0.1211 | 0.2686 | 0.3686 | 58 | 57 | 1 | 116 | 308 |
| `etour` | `bm25` | 0.2987 | 0.5994 | 0.4035 | 0.3567 | 0.2772 | 0.0712 | 0.2332 | 0.2969 | 58 | 57 | 1 | 116 | 308 |
| `etour` | `semantic` | 0.4329 | 0.6918 | 0.5439 | 0.4620 | 0.4035 | 0.1129 | 0.2685 | 0.3952 | 58 | 57 | 1 | 116 | 308 |
| `etour` | `structural` | 0.2755 | 0.3210 | 0.1228 | 0.1696 | 0.1895 | 0.0319 | 0.0985 | 0.1871 | 58 | 57 | 1 | 116 | 308 |

*Artifact-Granularity Caveat & Methodological Notes:*
- `sample_project` is evaluated using Python AST-level source chunks (functions, methods, classes).
- `itrust` and `etour` are evaluated at the Java compilation-unit/class level.
- Therefore, B0 vs B1 vs B2 vs B3 comparisons **within** each project are directly controlled and fair.
- Absolute metric values **across** projects should not be interpreted as directly comparable difficulty scores because artifact granularity differs.
- Cross-project analysis is used primarily to examine relative retriever behavior and robustness trends.
- Generalization cannot be claimed from only two real-world projects. Cross-project variation in retrieval performance motivates evaluating hybrid retrieval and evidence-backed verification as candidate approaches rather than assuming a single retrieval paradigm is sufficient.
- **B3 Methodology & Scope:** B3 is a structure-guided identifier + dependency retrieval baseline. Requirement tokens are matched only against declared structural entity/identifier terms to create seed activation; graph dependencies propagate that seed signal. Full code-text lexical retrieval is not used; dense embeddings are not used; LLM/RAG is not used. Note that B3 is not a completely lexical-free method because seed activation relies on matching requirement tokens to entity identifiers.
- **Graph Extraction Limitation:** Reference edges in B3 are inferred from explicit symbol-name occurrences in source text using deterministic matching. This is an approximation of true program dependencies and may include false structural edges from textual occurrences; it is not a compiler-verified call graph or complete dependency graph.
- **Alpha Justification:** $\alpha = 0.5$ is a fixed, a priori equal-weight design choice between direct identifier-based seed activation and structural neighbor diffusion. It was not tuned using benchmark ground truth.
- **Experimental Interpretation:** B3 provides an isolated test of structure-guided retrieval. Its mixed performance indicates that structural information contains useful signal but is insufficient as a standalone retrieval mechanism on these benchmarks.





