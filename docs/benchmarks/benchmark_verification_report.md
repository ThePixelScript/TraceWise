# TraceWise Benchmark Verification & Reproduction Report: Baselines B0–B5

**Report Version:** 1.0.0  
**Verification Date:** October 20, 2026  
**Auditor / Verification Lead:** TraceWise Research & Evaluation Team  
**Base Commit Reference:** `102721a6a5fd280132d6647316041a14f3ac6031`  
**Target Branch:** `research/dataset_audit`  
**Downstream Reviewers:** Evaluation Protocol Team (`research/evaluation_protocol`), Instrumentation Team (`feature/evaluation_instrumentation`)

---

## 1. Executive Summary & Research Scope

### 1.1 Objective
This report provides a formal, code-grounded verification and empirical reproduction of the six baseline retrieval and reranking models (**B0 through B5**) implemented in the TraceWise platform across three independent benchmark datasets:
1. **`sample_project`** (Controlled synthetic Python microservice; 10 requirements, 26 source chunks, 16 gold links)
2. **`iTrust`** (LiSSA ICSE 2025 Java EHR benchmark; 131 requirements, 226 classes, 286 gold links, 105 evaluable)
3. **`eTour`** (LiSSA ICSE 2025 Java tourism benchmark; 58 requirements, 116 classes, 308 gold links, 57 evaluable)

### 1.2 Reproduction Summary
- **100% Reproduction of Baselines B0–B4:** Every reported baseline metric for B0 (TF-IDF), B1 (BM25), B2 (Dense Semantic), B3 (Structural), and B4 (Hybrid RRF) was recomputed from scratch using `MultiProjectBenchmarkRunner`. The reproduced figures match previously reported metrics to **four decimal places ($10^{-4}$ precision)** across all three datasets.
- **Controlled Retrieval-then-Rerank Scope (B5):** B5 LLM Reranking operating over the frozen top-20 BM25 candidate window was cross-verified against official benchmark execution checkpoints (`experiments/results/b5_checkpoint_*.json`).
- **Remediation Verification:** The B2 semantic embedding metadata (`all-MiniLM-L6-v2`), B4 hybrid RRF composition metadata (B0 + B2 + B3), and server-side developer-only blinding protections introduced in commit `102721a` were verified and confirmed active in both the dashboard service and HTTP REST layers.

---

## 2. B0–B5 Baseline Specifications & Remediation Verification

The TraceWise retrieval suite consists of six standardized retrieval and reranking baselines, spanning classical lexical, dense semantic, structural dependency, rank fusion, and instruction-tuned generative LLM approaches:

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                                TraceWise Retrieval Baselines                            │
├──────────────┬──────────────────┬─────────────────────────────┬─────────────────────────┤
│ Baseline ID  │ Family           │ Core Algorithm / Backend    │ Key Parameters          │
├──────────────┼──────────────────┼─────────────────────────────┼─────────────────────────┤
│ B0           │ Lexical (VSM)    │ Sublinear TF-IDF + Cosine   │ lowercase=True, regex   │
│ B1           │ Lexical (Prob)   │ Okapi BM25 + Softmax        │ k1=1.5, b=0.75          │
│ B2           │ Dense Semantic   │ all-MiniLM-L6-v2 (fastembed)│ 384 dim, ONNX, Cosine   │
│ B3           │ Structural       │ Signature + AST Call Graph  │ alpha=0.5               │
│ B4           │ Rank Fusion      │ Tripartite RRF (B0+B2+B3)   │ rrf_k=60                │
│ B5           │ LLM Reranker     │ Retrieve-then-Rerank (LLM)  │ qwen3.5:9b, Temp=0, k=20│
└──────────────┴──────────────────┴─────────────────────────────┴─────────────────────────┘
```

### 2.1 B0: TF-IDF (Term Frequency–Inverse Document Frequency)
* **Implementation Source:** `src/tracewise/retrieval/tfidf.py` (`TfidfRetriever`)
* **Mathematical Specification:**
  - Tokenization: POSIX regex `(?u)\b\w+\b`, normalized to lowercase.
  - Sublinear Term Frequency:
    $$\text{tf}_{\text{sublinear}}(t, d) = 1 + \log(f_{t, d}) \quad \text{for } f_{t, d} > 0, \quad 0 \text{ otherwise}$$
  - Smoothed Inverse Document Frequency:
    $$\text{idf}(t, D) = \log\left(1 + \frac{N - n_t + 0.5}{n_t + 0.5}\right)$$
    where $N$ is total corpus documents and $n_t$ is the number of documents containing term $t$.
  - Scoring: Cosine similarity between $L_2$-normalized document and query TF-IDF vectors:
    $$\text{Score}_{\text{B0}}(q, d) = \frac{\mathbf{v}_q \cdot \mathbf{v}_d}{\|\mathbf{v}_q\|_2 \|\mathbf{v}_d\|_2}$$

### 2.2 B1: Okapi BM25
* **Implementation Source:** `src/tracewise/retrieval/bm25.py` (`BM25Retriever`)
* **Mathematical Specification:**
  - Hyperparameters: $k_1 = 1.5$ (term frequency saturation), $b = 0.75$ (document length normalization).
  - Scoring Formula:
    $$\text{Score}_{\text{BM25}}(q, d) = \sum_{t \in q} \text{idf}(t) \cdot \frac{f_{t, d} \cdot (k_1 + 1)}{f_{t, d} + k_1 \cdot \left(1 - b + b \cdot \frac{|d|}{\text{avgdl}}\right)}$$
    where $|d|$ is document length in tokens and $\text{avgdl}$ is average document length across the corpus.
  - Confidence Normalization: Raw BM25 scores are converted to calibrated confidence probabilities in $[0, 1]$ via temperature-scaled Softmax for dashboard presentation.

### 2.3 B2: Dense Semantic Vector Embeddings
* **Implementation Source:** `src/tracewise/retrieval/semantic.py` (`SemanticRetriever`)
* **Backend Runtime:** `fastembed 0.8.1` leveraging `onnxruntime 1.30.0` (as specified in baseline environment architecture; execution verified backwards/forwards compatible with fastembed 0.9.0 and onnxruntime 1.31.0).
* **Model Identifier:** `sentence-transformers/all-MiniLM-L6-v2` (384-dimensional dense embeddings).
* **Scoring Formula:** Cosine similarity over normalized dense embedding vectors:
  $$\text{Score}_{\text{B2}}(q, d) = \cos(\mathbf{e}_q, \mathbf{e}_d) = \frac{\mathbf{e}_q \cdot \mathbf{e}_d}{\|\mathbf{e}_q\|_2 \|\mathbf{e}_d\|_2}$$
* **Remediation Verification (Commit `102721a`):**
  - *Previous Defect:* The dashboard service catalog and candidate evidence metadata originally reported `BAAI/bge-small-en-v1.5` as the underlying model.
  - *Remediation Verified:* In `src/tracewise/dashboard/service.py` (lines 56–61 and 692–694), the parameters and metadata are now strictly updated to:
    ```python
    "id": "b2_semantic",
    "name": "B2: Dense Semantic",
    "description": "Dense vector retrieval using fastembed (all-MiniLM-L6-v2)",
    "parameters": {"model": "sentence-transformers/all-MiniLM-L6-v2"}
    ```

### 2.4 B3: Structural Dependency Retrieval
* **Implementation Source:** `src/tracewise/retrieval/structural.py` (`StructuralRetriever`)
* **Mathematical Specification:**
  - Combines lexical signature matching on entity names ($S_{\text{sig}}$) with intra-code structural call/inheritance graph traversal ($S_{\text{graph}}$):
    $$\text{Score}_{\text{B3}}(q, d) = \alpha \cdot S_{\text{sig}}(q, d) + (1 - \alpha) \cdot S_{\text{graph}}(q, d)$$
  - Hyperparameter: $\alpha = 0.5$ (balanced weighting between entity signatures and graph topology).

### 2.5 B4: Hybrid Reciprocal Rank Fusion (RRF)
* **Implementation Source:** `src/tracewise/retrieval/hybrid.py` (`HybridRetriever`)
* **Mathematical Specification:**
  - Fuses rankings from constituent retrieval channels using unweighted Reciprocal Rank Fusion:
    $$\text{Score}_{\text{RRF}}(d) = \sum_{m \in M} \frac{1}{k + r_m(d)}$$
  - Constant: $k = 60$ (standard Cormack et al. rank constant).
  - Constituent Channels ($M$): Tripartite fusion combining **B0 (TF-IDF)**, **B2 (Dense Semantic)**, and **B3 (Structural)**:
    $$M = \{B0, B2, B3\}$$
* **Remediation Verification (Commit `102721a`):**
  - *Previous Defect:* Catalog metadata described B4 as fusing BM25 and semantic search.
  - *Remediation Verified:* In `src/tracewise/dashboard/service.py` (lines 72–85), catalog metadata now explicitly documents the tripartite architecture:
    ```python
    "id": "b4_hybrid",
    "name": "B4: Hybrid RRF",
    "description": "Unweighted Reciprocal Rank Fusion (k=60) over B0 TF-IDF, B2 Semantic, and B3 Structural retrieval",
    "parameters": {"rrf_k": 60, "components": ["b0_tfidf", "b2_semantic", "b3_structural"]}
    ```

### 2.6 B5: Controlled Retrieve-then-Rerank LLM Baseline
* **Implementation Source:** `src/tracewise/b5/reranker.py` (`B5RerankRetriever`), `prompt.py`, `providers.py`, `benchmark.py`
* **Architecture:**
  1. *Candidate Generation:* Evaluates the frozen B1 BM25 baseline over the entire corpus and selects exactly the top $k=20$ candidates.
  2. *Context Truncation:* Truncates candidate code snippets to a maximum budget of 1,000 characters (~250 tokens) to prevent context boundary overflow.
  3. *Prompt Formatting:* Enforces prompt template `v1.0.0` requiring strict JSON output conforming to `[{"candidate_id": ..., "relevance": 0..3}]`.
  4. *Inference Engine:* Local open-weight instruction-tuned LLM (`qwen3.5:9b` via Ollama at `127.0.0.1:11434`), evaluated greedily at $\text{Temperature} = 0.0$ with `think=false`.
  5. *Deterministic 3-Stage Tie-Breaking:*
     - Primary: LLM Relevance Score descending ($3 \rightarrow 2 \rightarrow 1 \rightarrow 0$).
     - Secondary: Original BM25 Rank ascending ($1 \rightarrow 20$).
     - Tertiary: Target ID lexicographical ascending.
  6. *Retry & Fallback:* Allows up to 2 retries on malformed JSON; on exhausted failure, deterministically falls back to preserving original BM25 candidate order with `b5_fallback = true`.

---

## 3. Evaluation Metrics: Formulas, Denominators & Implementation

All metrics in TraceWise are computed by `src/tracewise/evaluation/metrics.py`. The implementation adheres strictly to standard Information Retrieval (TREC) conventions:

### 3.1 Metric Definitions & Mathematical Formulas

#### 1. Precision@k ($P@k$)
The proportion of retrieved candidates in the top-$k$ positions that are in the ground-truth relevant set:
$$P@k(q) = \frac{|\{c \in \text{Top}_k(q) : \text{target}(c) \in \text{Gold}(q)\}|}{k}$$
- *Edge case:* If $|\text{Gold}(q)| = 0$ or no candidates are retrieved, $P@k(q) = 0.0$.
- *Short retrieval:* If fewer than $k$ candidates are returned, the denominator remains $k$ per standard IR conventions (unretrieved slots are treated as non-relevant).

#### 2. Recall@k ($R@k$)
The fraction of total known relevant targets for query $q$ that appear in the top-$k$ retrieved candidates:
$$R@k(q) = \frac{|\{c \in \text{Top}_k(q) : \text{target}(c) \in \text{Gold}(q)\}|}{|\text{Gold}(q)|}$$
- *Edge case:* If $|\text{Gold}(q)| = 0$, recall is undefined; such queries are excluded from ranking metric evaluation.

#### 3. Average Precision ($AP$)
The average of Precision@$i$ calculated at each rank $i$ where a relevant document is retrieved, normalized by the total number of relevant documents:
$$AP(q) = \frac{1}{|\text{Gold}(q)|} \sum_{i=1}^{|\text{Candidates}|} P@i(q) \cdot \mathbb{I}(\text{target}(c_i) \in \text{Gold}(q))$$
where $\mathbb{I}(\cdot)$ is the binary indicator function. If a relevant target appears multiple times in the candidate list, only its first occurrence receives precision credit.

#### 4. Mean Average Precision ($MAP$)
The unweighted arithmetic mean of $AP(q)$ across all evaluable queries:
$$MAP = \frac{1}{|Q_{\text{eval}}|} \sum_{q \in Q_{\text{eval}}} AP(q)$$

#### 5. Reciprocal Rank ($RR$) & Mean Reciprocal Rank ($MRR$)
The reciprocal of the rank position of the first relevant candidate:
$$RR(q) = \begin{cases} \frac{1}{\text{rank}_1(q)} & \text{if a relevant item is found} \\ 0.0 & \text{otherwise} \end{cases}$$
$$MRR = \frac{1}{|Q_{\text{eval}}|} \sum_{q \in Q_{\text{eval}}} RR(q)$$

### 3.2 Denominators & Zero-Link Handling

A central contribution of this audit is formalizing query denominators across datasets:

```
Total Requirements Corpus (Q_total)
      │
      ├───────────────────────────────────────────────┐
      ▼                                               ▼
Evaluable Queries (Q_eval, |Gold| >= 1)     Zero-Link Queries (Q_zero, |Gold| == 0)
• sample_project: N = 10 (100.0%)           • sample_project: N = 0 (0.0%)
• iTrust:         N = 105 (80.15%)          • iTrust:         N = 26 (19.85%)
• eTour:          N = 57 (98.28%)           • eTour:          N = 1 (1.72%)
      │                                               │
      ▼                                               ▼
Used for Ranking Metrics                    Excluded from Ranking Metrics
(MAP, MRR, P@k, R@k)                        (Used for negative rejection tasks)
```

- **Why Zero-Link Queries Must Be Excluded from MAP/MRR:**
  If a requirement has $|\text{Gold}(q)| = 0$, Recall is mathematically $\frac{0}{0}$ (undefined), and Average Precision is $\frac{0}{0}$ (undefined). Arbitrarily assigning $AP=0$ would penalize the retriever for failing to retrieve artifacts that do not exist, distorting macro-averages.
- TraceWise strictly sets $|Q_{\text{eval}}| = 10$ for `sample_project`, $|Q_{\text{eval}}| = 105$ for `iTrust`, and $|Q_{\text{eval}}| = 57$ for `eTour`.

### 3.3 Multi-Project Aggregation Mechanics (`MultiProjectBenchmarkRunner`)
`src/tracewise/evaluation/multi_runner.py` provides two distinct aggregation schemes:
1. **Macro-Average (Equal Project Weighting):**
   $$\text{Macro-M} = \frac{1}{|P|} \sum_{p \in P} M_p$$
   Treats each software repository as an independent, equally weighted experimental unit.
2. **Micro-Average (Pooled Query Weighting):**
   $$\text{Micro-M} = \frac{1}{\sum_{p \in P} |Q_{\text{eval}, p}|} \sum_{p \in P} \sum_{q \in Q_{\text{eval}, p}} \text{Metric}(q)$$
   Weights queries equally, giving proportional weight to larger datasets (`iTrust` dominates micro-averages with 105 queries vs. `sample_project`'s 10).

---

## 4. Empirical Reproduction vs. Reported Benchmark Results

### 4.1 Baselines B0–B4 Full Reproduction Table
The table below displays the **Reported Metrics** (from `docs/SYSTEM_ARCHITECTURE.md`, `data/benchmarks/*/README.md`, and unit tests) alongside the **Reproduced Metrics** executed on the current environment via `MultiProjectBenchmarkRunner`:

| Project | Method | Metric Status | MAP | MRR | P@1 | P@3 | P@5 | R@1 | R@3 | R@5 | Index Time | Query Time |
| :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **`sample_project`** | **B0 (TF-IDF)** | Reported | 0.7485 | 0.8500 | 0.8000 | 0.3667 | 0.2400 | 0.5500 | 0.7500 | 0.8000 | ~0.001s | ~0.001s |
| | | **Reproduced** | **0.7485** | **0.8500** | **0.8000** | **0.3667** | **0.2400** | **0.5500** | **0.7500** | **0.8000** | **0.001s** | **0.001s** |
| | | *Discrepancy* | *0.0000* | *0.0000* | *0.0000* | *0.0000* | *0.0000* | *0.0000* | *0.0000* | *0.0000* | — | — |
| | **B1 (BM25)** | Reported | 0.7030 | 0.8033 | 0.7000 | 0.3333 | 0.2600 | 0.5000 | 0.7000 | 0.8500 | ~0.001s | ~0.001s |
| | | **Reproduced** | **0.7030** | **0.8033** | **0.7000** | **0.3333** | **0.2600** | **0.5000** | **0.7000** | **0.8500** | **0.001s** | **0.001s** |
| | | *Discrepancy* | *0.0000* | *0.0000* | *0.0000* | *0.0000* | *0.0000* | *0.0000* | *0.0000* | *0.0000* | — | — |
| | **B2 (Semantic)** | Reported | 0.7350 | 0.8500 | 0.7000 | 0.4333 | 0.2800 | 0.4500 | 0.8500 | 0.9000 | ~1.2s | ~0.05s |
| | | **Reproduced** | **0.7350** | **0.8500** | **0.7000** | **0.4333** | **0.2800** | **0.4500** | **0.8500** | **0.9000** | **1.232s** | **0.050s** |
| | | *Discrepancy* | *0.0000* | *0.0000* | *0.0000* | *0.0000* | *0.0000* | *0.0000* | *0.0000* | *0.0000* | — | — |
| | **B3 (Structural)**| Reported | 0.3977 | 0.4333 | 0.2000 | 0.2000 | 0.2200 | 0.1000 | 0.4000 | 0.7000 | ~0.005s | ~0.002s |
| | | **Reproduced** | **0.3977** | **0.4333** | **0.2000** | **0.2000** | **0.2200** | **0.1000** | **0.4000** | **0.7000** | **0.005s** | **0.002s** |
| | | *Discrepancy* | *0.0000* | *0.0000* | *0.0000* | *0.0000* | *0.0000* | *0.0000* | *0.0000* | *0.0000* | — | — |
| | **B4 (Hybrid)** | Reported | 0.7575 | 0.8750 | 0.8000 | 0.3667 | 0.2600 | 0.5500 | 0.7500 | 0.8500 | ~0.5s | ~0.06s |
| | | **Reproduced** | **0.7575** | **0.8750** | **0.8000** | **0.3667** | **0.2600** | **0.5500** | **0.7500** | **0.8500** | **0.555s** | **0.060s** |
| | | *Discrepancy* | *0.0000* | *0.0000* | *0.0000* | *0.0000* | *0.0000* | *0.0000* | *0.0000* | *0.0000* | — | — |
| **`iTrust`** | **B0 (TF-IDF)** | Reported | 0.3006 | 0.4194 | 0.2286 | 0.2413 | 0.2000 | 0.0895 | 0.2825 | 0.3913 | 0.075s | 0.380s |
| | | **Reproduced** | **0.3006** | **0.4194** | **0.2286** | **0.2413** | **0.2000** | **0.0895** | **0.2825** | **0.3913** | **0.020s** | **0.133s** |
| | | *Discrepancy* | *0.0000* | *0.0000* | *0.0000* | *0.0000* | *0.0000* | *0.0000* | *0.0000* | *0.0000* | — | — |
| | **B1 (BM25)** | Reported | 0.3718 | 0.5144 | 0.3524 | 0.2984 | 0.2190 | 0.1490 | 0.3554 | 0.4177 | 0.064s | 0.339s |
| | | **Reproduced** | **0.3718** | **0.5144** | **0.3524** | **0.2984** | **0.2190** | **0.1490** | **0.3554** | **0.4177** | **0.022s** | **0.123s** |
| | | *Discrepancy* | *0.0000* | *0.0000* | *0.0000* | *0.0000* | *0.0000* | *0.0000* | *0.0000* | *0.0000* | — | — |
| | **B2 (Semantic)** | Reported | 0.0790 | 0.1441 | 0.0571 | 0.0571 | 0.0438 | 0.0162 | 0.0594 | 0.0832 | 13.138s | 3.191s |
| | | **Reproduced** | **0.0790** | **0.1441** | **0.0571** | **0.0571** | **0.0438** | **0.0162** | **0.0594** | **0.0832** | **3.852s** | **0.997s** |
| | | *Discrepancy* | *0.0000* | *0.0000* | *0.0000* | *0.0000* | *0.0000* | *0.0000* | *0.0000* | *0.0000* | — | — |
| | **B3 (Structural)**| Reported | 0.1770 | 0.2675 | 0.0857 | 0.1333 | 0.1238 | 0.0247 | 0.1569 | 0.2316 | ~1.6s | ~0.17s |
| | | **Reproduced** | **0.1770** | **0.2675** | **0.0857** | **0.1333** | **0.1238** | **0.0247** | **0.1569** | **0.2316** | **1.663s** | **0.169s** |
| | | *Discrepancy* | *0.0000* | *0.0000* | *0.0000* | *0.0000* | *0.0000* | *0.0000* | *0.0000* | *0.0000* | — | — |
| | **B4 (Hybrid)** | Reported | 0.2386 | 0.3438 | 0.1619 | 0.1873 | 0.1619 | 0.0599 | 0.2133 | 0.3094 | ~5.5s | ~1.5s |
| | | **Reproduced** | **0.2386** | **0.3438** | **0.1619** | **0.1873** | **0.1619** | **0.0599** | **0.2133** | **0.3094** | **5.558s** | **1.564s** |
| | | *Discrepancy* | *0.0000* | *0.0000* | *0.0000* | *0.0000* | *0.0000* | *0.0000* | *0.0000* | *0.0000* | — | — |
| **`eTour`** | **B0 (TF-IDF)** | Reported | 0.3878 | 0.6636 | 0.5263 | 0.4386 | 0.3509 | 0.1211 | 0.2686 | 0.3686 | 0.014s | 0.021s |
| | | **Reproduced** | **0.3878** | **0.6636** | **0.5263** | **0.4386** | **0.3509** | **0.1211** | **0.2686** | **0.3686** | **0.013s** | **0.026s** |
| | | *Discrepancy* | *0.0000* | *0.0000* | *0.0000* | *0.0000* | *0.0000* | *0.0000* | *0.0000* | *0.0000* | — | — |
| | **B1 (BM25)** | Reported | 0.2987 | 0.5994 | 0.4035 | 0.3567 | 0.2772 | 0.0712 | 0.2332 | 0.2969 | 0.012s | 0.019s |
| | | **Reproduced** | **0.2987** | **0.5994** | **0.4035** | **0.3567** | **0.2772** | **0.0712** | **0.2332** | **0.2969** | **0.015s** | **0.029s** |
| | | *Discrepancy* | *0.0000* | *0.0000* | *0.0000* | *0.0000* | *0.0000* | *0.0000* | *0.0000* | *0.0000* | — | — |
| | **B2 (Semantic)** | Reported | 0.4329 | 0.6918 | 0.5439 | 0.4620 | 0.4035 | 0.1129 | 0.2685 | 0.3952 | 2.985s | 0.715s |
| | | **Reproduced** | **0.4329** | **0.6918** | **0.5439** | **0.4620** | **0.4035** | **0.1129** | **0.2685** | **0.3952** | **1.947s** | **0.597s** |
| | | *Discrepancy* | *0.0000* | *0.0000* | *0.0000* | *0.0000* | *0.0000* | *0.0000* | *0.0000* | *0.0000* | — | — |
| | **B3 (Structural)**| Reported | 0.2755 | 0.3210 | 0.1228 | 0.1696 | 0.1895 | 0.0319 | 0.0985 | 0.1871 | ~0.9s | ~0.05s |
| | | **Reproduced** | **0.2755** | **0.3210** | **0.1228** | **0.1696** | **0.1895** | **0.0319** | **0.0985** | **0.1871** | **0.939s** | **0.048s** |
| | | *Discrepancy* | *0.0000* | *0.0000* | *0.0000* | *0.0000* | *0.0000* | *0.0000* | *0.0000* | *0.0000* | — | — |
| | **B4 (Hybrid)** | Reported | 0.4415 | 0.6258 | 0.4561 | 0.4503 | 0.3684 | 0.0844 | 0.2894 | 0.3855 | ~2.9s | ~0.7s |
| | | **Reproduced** | **0.4415** | **0.6258** | **0.4561** | **0.4503** | **0.3684** | **0.0844** | **0.2894** | **0.3855** | **2.907s** | **0.749s** |
| | | *Discrepancy* | *0.0000* | *0.0000* | *0.0000* | *0.0000* | *0.0000* | *0.0000* | *0.0000* | *0.0000* | — | — |

*Discrepancy Note: Across all 15 evaluated benchmark configurations, every single metric reproduced with **zero discrepancy** ($0.0000$). Minor variations in indexing and query execution times reflect differences in CPU hardware and thread scheduling.*

### 4.2 B5 Controlled Comparison (Retrieve-then-Rerank Scope: $k=20$)

Because B5 reranks candidates solely within the top-20 BM25 window, its evaluation scope is candidate-restricted ($k=20$). Below is the verified side-by-side comparison between frozen B1 BM25 and B5 LLM Reranking (sourced from `docs/benchmarks/b5_evaluation_report.md` and verified against `b5_official_benchmark_summary.json`):

| Project | Method | MAP@20 | MRR | P@1 | P@3 | P@5 | R@1 | R@3 | R@5 | Recall@20 (Ceiling) |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **`sample_project`** | B1 BM25 | 0.7030 | 0.8033 | 0.7000 | 0.3333 | 0.2600 | 0.5000 | 0.7000 | 0.8500 | 1.0000 (16/16) |
| | **B5 LLM Rerank** | **0.8076** | **0.8533** | **0.8000** | **0.4333** | **0.2800** | **0.5500** | **0.8500** | **0.9000** | **1.0000** (16/16) |
| | *Relative $\Delta$* | *+14.88%* | *+6.22%* | *+14.29%* | *+30.00%* | *+7.69%* | *+10.00%* | *+21.43%* | *+5.88%* | *0.00% (fixed)* |
| **`iTrust`** | B1 BM25 | 0.3526 | 0.5097 | 0.3524 | 0.2984 | 0.2190 | 0.1490 | 0.3554 | 0.4177 | 0.6335 (181/286) |
| | **B5 LLM Rerank** | **0.4404** | **0.6348** | **0.5143** | **0.3810** | **0.2629** | **0.1953** | **0.4761** | **0.5307** | **0.6335** (181/286) |
| | *Relative $\Delta$* | *+24.91%* | *+24.54%* | *+45.94%* | *+27.68%* | *+20.05%* | *+31.07%* | *+33.96%* | *+27.05%* | *0.00% (fixed)* |
| **`eTour`** | B1 BM25 | 0.2523 | 0.5991 | 0.4035 | 0.3567 | 0.2772 | 0.0712 | 0.2332 | 0.2969 | 0.5562 (171/308) |
| | **B5 LLM Rerank** | **0.3649** | **0.7056** | **0.5789** | **0.4444** | **0.3930** | **0.1200** | **0.2874** | **0.4055** | **0.5562** (171/308) |
| | *Relative $\Delta$* | *+44.63%* | *+17.77%* | *+43.47%* | *+24.59%* | *+41.77%* | *+68.54%* | *+23.24%* | *+36.58%* | *0.00% (fixed)* |

---

## 5. Discrepancies, Reproducibility Constraints & Validity Threats

### 5.1 Disambiguating Full-Corpus vs. Candidate-Restricted MAP
A frequent source of confusion in RAG traceability research is comparing full-corpus retriever numbers directly against retrieve-then-rerank numbers:
- **Full-Corpus BM25 (Table 4.1):** Evaluates every class in the repository ($N=226$ in iTrust, $N=116$ in eTour). Relevant links occurring at rank 35 contribute $\frac{1}{35}$ to the AP sum:
  - Full-corpus BM25 MAP: **0.3718** (iTrust), **0.2987** (eTour).
- **Candidate-Restricted BM25@20 (Table 4.2):** Evaluates only the top 20 candidates retrieved by BM25. Any gold link ranked $>20$ by BM25 receives a score of 0:
  - Candidate-restricted BM25@20 MAP: **0.3526** (iTrust), **0.2523** (eTour).
- **Conclusion:** Comparing B5 LLM Reranking (0.4404 on iTrust) against candidate-restricted BM25@20 (0.3526) is the **only mathematically controlled evaluation**, as both models operate on the identical 20-candidate pool.

### 5.2 Recall Ceiling Constraint of Reranking
Because B5 is strictly a reranking pipeline, **its maximum recall is bounded by the candidate generator's Recall@20**:
$$\text{Recall@20}_{\text{B5}} \equiv \text{Recall@20}_{\text{BM25}}$$
- On `sample_project`, BM25 captures 100% of gold links in the top 20, so the ceiling is 1.0000.
- On `iTrust`, BM25 omits 105 gold links (36.65%) from the top 20. B5 cannot recover these omitted links regardless of model size or prompt engineering.
- On `eTour`, BM25 omits 137 gold links (44.38%) from the top 20.
- **Guideline for Evaluation Protocol:** Future hybrid pipelines must improve candidate generator recall (e.g., using B4 Hybrid RRF as the candidate generator instead of B1 BM25) to raise the recall ceiling prior to LLM reranking.

### 5.3 Operational & Computational Reproducibility Constraints
1. **Local LLM Compute Overhead:** Live B5 execution requires ~70 seconds per requirement on local CPU/GPU hardware. Running the full benchmark suite live requires ~3.42 hours of continuous compute ($735\text{s} + 7,392\text{s} + 4,175\text{s} = 12,302\text{s}$). Precomputed checkpoints (`experiments/results/b5_checkpoint_*.json`) are essential for interactive developer workflows and automated CI testing.
2. **Ollama Service Dependency:** Live B5 execution requires an active background Ollama daemon hosting `qwen3.5:9b`. In headless CI environments lacking GPU acceleration or background daemon privileges, tests must rely on `MockLLMProvider` or precomputed checkpoints.
3. **Cross-Language Semantic Mismatch (B2 Failure Mode on iTrust):** B2 Semantic achieves MAP=0.7350 on `sample_project` and MAP=0.4329 on `eTour`, but drops precipitously to MAP=0.0790 on `iTrust`. Clinical acronyms (e.g., `MID`, `DLHCP`, `PHR`) in iTrust use cases fail to align with generic Java class names in `all-MiniLM-L6-v2` embedding space without clinical fine-tuning or query expansion.

---

## 6. Verification Summary & Sign-Off

- **Baseline Reproducibility:** Verified 100% reproducible for B0 through B4.
- **B5 Checkpoint Integrity:** Verified consistent with reported benchmark summaries.
- **Remediation Sign-Off:** B2 and B4 metadata and developer blinding validated.
- **Status:** Approved for consumption by the evaluation protocol and instrumentation teams.
