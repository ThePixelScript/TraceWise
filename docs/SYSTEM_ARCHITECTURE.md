# TraceWise System Architecture

## Overview

TraceWise is an automated requirements traceability and change impact analysis platform designed to recover, verify, and monitor relationships across software artifacts.

The core pipeline operates across deterministic stages:
```
Filesystem
    ↓ (Ingestion)
Artifacts
    ↓ (Structural Chunking)
ArtifactChunks
    ↓ (Text Preprocessing)
Preprocessed Text (ProcessedText)
    ↓ (Retrieval & Ranking)
TraceLinks
```

---

## Artifact vs ArtifactChunk

- **`Artifact`**: Represents a top-level, ingestible unit discovered on the filesystem (e.g., a complete source file, a requirement specification, or a test file). It holds physical provenance, raw text, and project-relative paths.
- **`ArtifactChunk`**: Represents an addressable structural unit inside an `Artifact` (e.g., a class, a method, or a standalone function). It enables granular retrieval and fine-grained traceability links without altering the parent artifact.

---

## Structural Chunking (Python AST)

### 1. Scope
In Milestone 1B, structural chunking is Python-only (`.py` files classified as `SOURCE_CODE` or `TEST_CASE`). It relies exclusively on the Python standard library `ast` module. Other languages and non-Python artifacts are rejected at the chunker boundary.

### 2. Extracted Structural Units
- **Top-level functions (`FunctionDef`)**: Emitted as function chunks.
- **Top-level async functions (`AsyncFunctionDef`)**: Emitted as function chunks with `metadata["is_async"] = True`.
- **Top-level classes (`ClassDef`)**: Emitted as class chunks. Direct methods within the class body (`FunctionDef` / `AsyncFunctionDef`) are emitted as method chunks.

### 3. Nested Functions & Nested Classes
- **Nested functions**: Functions defined inside other functions or methods are not emitted as independent chunks. They remain part of the enclosing function or method's content.
- **Nested classes**: Classes defined inside other classes or functions are not emitted as independent chunks in this milestone. They remain part of the enclosing class's content.

### 4. Line Numbering & Slicing Semantics
- **1-based and inclusive**: All `start_line` and `end_line` bounds are 1-based and inclusive.
- **Exact raw content preservation**: Extracted source text corresponds exactly to lines `start_line` through `end_line` using `splitlines(keepends=True)`. No whitespace stripping, normalization, or modification is performed during extraction. `content` is initially identical to `raw_content`.
- **Decorators**: When a function, async function, or class has decorators, `start_line` is the minimum line number of its decorators (`min(d.lineno for d in node.decorator_list)`), ensuring decorator code is included in the chunk slice.
- **End line**: Uses AST `node.end_lineno`. If an AST node lacks a valid `end_lineno` or reports `end_lineno < start_line`, a `PythonParsingError` is raised rather than guessing bounds.

### 5. Deterministic Identifiers & Collision Handling
Identifiers are deterministic and derive from the POSIX `artifact.file_path`:
- **Top-level function**: `{file_path}#{function_name}` (with `parent_id = artifact.id`)
- **Top-level class**: `{file_path}#{class_name}` (with `parent_id = artifact.id`)
- **Class method**: `{file_path}#{class_name}.{method_name}` (with `parent_id = class_chunk.id`)

**Collision Handling**:
When a base identifier is unique across the artifact, the clean, unadorned ID is preserved (e.g., `src/example.py#process`, `src/example.py#Service.run`).
If Python code contains duplicate definitions (e.g., repeated function definitions, class/function name collisions, or duplicate method declarations), every colliding chunk receives a deterministic source-line discriminator using its 1-based `start_line`:
- Duplicate function: `{file_path}#{function_name}@L{start_line}` (e.g., `src/example.py#process@L4`)
- Duplicate method: `{file_path}#{class_name}.{method_name}@L{start_line}` (e.g., `src/example.py#Service.run@L7`)

Path normalization is strictly handled by the ingestion layer; `PythonChunker` preserves `artifact.file_path` as supplied without silent path mutations.

### 6. Deliberate Class / Method Overlap
Class chunks and method chunks intentionally overlap textually:
- A class chunk contains the entire class definition including all method implementations.
- A method chunk contains the specific method implementation.

This overlap allows retrieval strategies to evaluate coarse-grained conceptual units (classes) as well as fine-grained localized units (methods) without premature deduplication.

### 7. Syntax Error Handling & Empty Files
- **Empty / whitespace files**: Files containing only whitespace or comments (valid syntax without top-level functions/classes) return an empty list `[]`.
- **Parser failures**: Syntactically invalid Python files raise `PythonParsingError` (subclass of `ChunkingError`) detailing the file path and line number, ensuring callers distinguish valid empty artifacts from parsing failures.

---

## Text Preprocessing (Milestone 1C)

### 1. Scope & Package Location
The text preprocessing module resides in `src/tracewise/preprocessing/`:
- `models.py`: Domain model `ProcessedText`
- `normalizer.py`: Deterministic text normalization (`normalize_unicode`, `normalize_case`, `normalize_whitespace`, `normalize_text`)
- `tokenizer.py`: Compound identifier splitting (`split_identifier`) and lexical tokenization (`tokenize`)
- `preprocessor.py`: Stateless `Preprocessor` orchestrating transformation of `Artifact` and `ArtifactChunk` instances

### 2. ProcessedText Contract & Role
`ProcessedText` is the canonical domain model emitted by preprocessing and consumed by downstream retrieval indexing:
- **`source_id`**: String identifier identifying the source `Artifact.id` or `ArtifactChunk.id`. Must be non-empty.
- **`original_text`**: Exact, verbatim input text. Preserved without modification for provenance and downstream display.
- **`normalized_text`**: Canonical, readable text sequence produced via Unicode NFC normalization, lowercasing, and whitespace collapsing. Punctuation and sentence/code structure are preserved for semantic retrieval models.
- **`tokens`**: Deterministic list of lowercased lexical terms with compound identifiers split and punctuation removed. Required field serving as the term representation for lexical retrieval.
- **`metadata`**: Free-form dictionary preserving upstream artifact/chunk metadata and structural provenance (`artifact_type`, `parent_id`, `name`, `start_line`, `end_line`).
- **`model_config = ConfigDict(extra="forbid")`**: Strict schema forbidding undocumented fields.

### 3. Determinism & Input Preservation
All preprocessing components are pure, stateless, and deterministic:
- Identical input text yields identical `normalized_text` and `tokens` across runs and instances.
- Input `Artifact` and `ArtifactChunk` objects are never mutated.
- Stopword removal, stemming, lemmatization, and aggressive keyword filtering are disabled by default to maintain research neutrality and prevent benchmark overfitting.

### 4. Preprocessing → Retrieval Boundary
The retrieval layer consumes `ProcessedText` objects as its unit of indexing and query evaluation. Retrieval strategies do not access filesystem storage, AST parsing, or raw artifact ingestion details; they operate solely on the preprocessed representations (`normalized_text` for dense/semantic models, `tokens` for sparse/lexical models).

---

## Retrieval Layer Contracts (Milestone 2A)

### 1. Scope & Package Location
The retrieval contracts reside in `src/tracewise/retrieval/`:
- `models.py`: `RetrievalCandidate`
- `base.py`: `BaseRetriever` abstract base class (imports `ProcessedText` from `tracewise.preprocessing.models`)
- `exceptions.py`: `RetrieverError`, `NotIndexedError`

### 2. Architectural Flow
The retrieval layer sits between text preprocessing and candidate ranking / link creation:
```
Artifact / ArtifactChunk
    ↓ (Preprocessing)
ProcessedText (query / corpus)
    ↓
BaseRetriever.index(documents) / retrieve(query, top_k)
    ↓
RetrievalCandidate[] (query_id, target_id, score, rank, retriever_name)
    ↓
Ranking & Candidate Combination
    ↓
Evaluation / Human Verification
    ↓
TraceLink (source_id, target_id, status)
```

The retrieval layer does not know about filesystem traversal, ingestion, raw AST parsing, or evaluation metrics. It consumes `ProcessedText` and yields ranked `RetrievalCandidate` lists.

### 3. RetrievalCandidate vs TraceLink
- **`RetrievalCandidate`**: Represents an algorithm-generated candidate match. It is immutable/frozen, stores raw unnormalized scores, 1-based consecutive ranks, and the originating `retriever_name`. It has no acceptance/rejection status or verification lifecycle.
- **`TraceLink`**: Represents a validated or proposed traceability relationship with a lifecycle `TraceLinkStatus` (e.g., `PROPOSED`, `VERIFIED`, `REJECTED`).
- Conceptually:
  - `RetrievalCandidate.query_id` → `TraceLink.source_id`
  - `RetrievalCandidate.target_id` → `TraceLink.target_id`

### 4. Shared Contract Semantics
- **Score**: Higher score denotes higher relevance. Raw matcher scores are preserved without normalization.
- **Rank**: 1-based, consecutive integers (1, 2, 3, ...).
- **Ordering**: Sorted by descending score, breaking ties deterministically by `target_id` ascending:
  `sorted(candidates, key=lambda c: (-c.score, c.target_id))`
- **Results**: No duplicate `target_id` values per query. `top_k=None` returns the complete ranking; `top_k>0` limits results; `top_k<=0` raises `ValueError`.
- **Lifecycle**: Retrievers must be indexed before querying (`retrieve` before `index` raises `NotIndexedError`). Re-indexing replaces the previous index completely.

### 5. Concrete Implementations
- **`TfidfRetriever` (Milestone 2B - Complete, B0)**: Canonical lexical retrieval baseline using sublinear TF-IDF and Cosine similarity.
- **`BM25Retriever` (Milestone 3B - Complete, B1)**: Classical probabilistic lexical retrieval baseline using Okapi BM25 term weighting and document length normalization.
- **`SemanticRetriever` (Milestone 4A - Complete, B2)**: Dense semantic retrieval baseline using pretrained transformer embeddings and cosine similarity.
- **`StructuralRetriever` (Milestone B3 - Complete, B3)**: Structure-guided identifier + dependency retrieval baseline using declared entity signatures and intra-code dependency graph propagation.
- **Future Retrievers**: Fixed hybrid (B4), LLM/RAG (B5), and TraceWise evidence workflow (B6) remain future milestones.




---

## Dense Semantic Retrieval Baseline: Embeddings + Cosine (Milestone 4A)

### 1. Scope & Role
`SemanticRetriever` is located in `src/tracewise/retrieval/semantic.py` and implements `BaseRetriever`. It serves as the dense semantic retrieval baseline (B2) for requirement-to-code traceability in TraceWise.

Like B0 and B1, B2 is a non-novel baseline. It uses standard dense vector embeddings from a pretrained sentence/code transformer (`sentence-transformers/all-MiniLM-L6-v2` via `fastembed` ONNX runtime) without fine-tuning, training, or exposure to ground truth.

### 2. Algorithmic Formulation & Design
1. **Text Representation**: Extracted from `doc.normalized_text` (falling back to `" ".join(doc.tokens)` if blank).
2. **Dense Embedding**: Transformed into dense vectors $\mathbf{v} \in \mathbb{R}^D$ ($D=384$ for `all-MiniLM-L6-v2`).
3. **Vector Normalization**: Safe $L_2$ normalization:
   $$\hat{\mathbf{v}} = \frac{\mathbf{v}}{\max(\|\mathbf{v}\|_2, 10^{-12})}$$
   Zero vectors remain zero.
4. **Scoring**: Cosine similarity via inner product:
   $$\text{Score}(q, d) = \hat{\mathbf{q}} \cdot \hat{\mathbf{d}}$$
5. **Score Clamping**: Clamped to $[0.0, 1.0]$.
6. **Pluggable Architecture**: Accepts any custom callable `embedder: Callable[[Sequence[str]], np.ndarray]` or defaults to ONNX-accelerated local execution. Deterministic unit tests use `DeterministicMockEmbedder` without network dependency.

---

## Lexical Retrieval Baseline: TF-IDF + Cosine (Milestone 2B)

### 1. Scope & Role
`TfidfRetriever` is located in `src/tracewise/retrieval/tfidf.py` and implements `BaseRetriever`. It serves as the initial lexical baseline for software artifact retrieval in TraceWise.

TF-IDF with cosine similarity is a standard, classical technique from information retrieval; TraceWise uses it as a transparent, reproducible comparative baseline and makes no claim of algorithmic novelty.

### 2. Algorithmic Specification
- **Token Source**: Operates exclusively on `ProcessedText.tokens` emitted by the preprocessing layer. It does not re-tokenize, strip stopwords, access AST structures, or inspect raw files.
- **Vocabulary Fitting**: Fitted strictly on indexed target documents (`sorted(unique target tokens)`). Unseen query terms do not expand the vocabulary and contribute zero weight.
- **Sublinear Term Frequency**:
  $$\text{TF}(t, d) = \begin{cases} 0 & \text{if } \text{count}(t, d) = 0 \\ 1 + \ln(\text{count}(t, d)) & \text{otherwise} \end{cases}$$
- **Document Frequency**: $\text{DF}(t)$ is the count of indexed target documents containing $t$ at least once.
- **Smoothed Inverse Document Frequency**:
  $$\text{IDF}(t) = \ln\left(1 + \frac{N}{\text{DF}(t)}\right)$$
  where $N$ is the total count of indexed target documents.
- **Term Weighting**: $\text{weight}(t, d) = \text{TF}(t, d) \times \text{IDF}(t)$. The query vector uses the same fitted IDF values.
- **Pre-normalized Dense Matrix**: Document rows are pre-normalized by their L2 norm during indexing into a dense `float64` NumPy matrix $D_{\text{norm}}$, enabling vectorized matrix-vector dot product retrieval:
  $$\text{score}(q, d) = \frac{\mathbf{q} \cdot \mathbf{d}}{\|\mathbf{q}\|_2 \|\mathbf{d}\|_2} = \mathbf{d}_{\text{norm}} \cdot \mathbf{q}_{\text{norm}}$$
  If $\|\mathbf{q}\|_2 \le 10^{-12}$ or $\|\mathbf{d}\|_2 \le 10^{-12}$, the similarity score is $0.0$. Scores are finite and clamped to $[0.0, 1.0]$.

### 3. Lifecycle & Atomicity
- **State Initialization**: Unindexed instances report `is_indexed = False` and raise `NotIndexedError` upon query.
- **Atomic Indexing**: Index computation occurs in local temporary variables before state assignment. Any failure (e.g., empty corpus, duplicate `source_id`) raises `ValueError` and leaves the prior active index completely intact.
- **Full Replacement**: Successfully calling `index` completely replaces the previous vocabulary, IDF weights, and document matrices.
- **Query Immutability**: Query execution is purely read-only and never alters indexed state.

### 4. Architectural Boundaries
- **Hypothesis Generation vs Ground Truth**: Candidate retrieval produces ranked hypotheses (`RetrievalCandidate`). It does not create or mutate ground-truth `TraceLink` entities.
- **Separation of Evaluation**: The retriever has no access to ground-truth link sets or evaluation metrics. Evaluation is conducted by an independent downstream evaluation harness using identical inputs.
- **Fair Comparison Baseline**: The lexical vocabulary, token stream, and target chunk set are frozen to ensure direct, controlled comparison against BM25 and upcoming semantic embedding baselines.

---

## Lexical Retrieval Baseline: BM25 (Milestone 3B)

### 1. Scope & Role
`BM25Retriever` is located in `src/tracewise/retrieval/bm25.py` and implements `BaseRetriever`. It serves as the second classical lexical retrieval baseline (B1) for software artifact retrieval in TraceWise.

BM25 is an established information retrieval baseline from the probabilistic relevance framework; TraceWise incorporates standard Okapi BM25 as an objective reference and makes no claim of algorithmic novelty.

### 2. Algorithmic Specification
- **Token Source**: Operates exclusively on `ProcessedText.tokens` emitted by the preprocessing layer without secondary tokenization or filtering.
- **Document Length**: $|d| = \text{len}(d.\text{tokens})$, with average document length across target corpus $\text{avgdl} = \frac{1}{N} \sum_{d} |d|$.
- **Length Normalization Component**:
  $$B(d) = 1 - b + b \cdot \frac{|d|}{\text{avgdl}} \quad (\text{or } 1.0 \text{ if } \text{avgdl} = 0)$$
- **BM25 Term Weighting**:
  $$\text{TF}_{\text{BM25}}(t, d) = \frac{\text{TF}(t, d) \cdot (k_1 + 1)}{\text{TF}(t, d) + k_1 \cdot B(d)}$$
- **Smoothed Non-Negative Inverse Document Frequency**:
  $$\text{IDF}(t) = \ln \left( 1 + \frac{N - \text{DF}(t) + 0.5}{\text{DF}(t) + 0.5} \right)$$
  ensuring finite, non-negative IDF values even for frequent terms.
- **Query Scoring**:
  $$\text{Score}(Q, d) = \sum_{t \in Q} \text{TF}_{\text{BM25}}(t, d) \cdot \text{IDF}(t)$$
  vectorized as a dot product between the precomputed document matrix and the query term count vector.
- **Default Parameters**: $k_1 = 1.5$, $b = 0.75$, standard un-tuned Okapi BM25 defaults.
- **Ties & Ordering**: Candidates are sorted by `(-score, target_id)` with consecutive 1-based ranks.

### 3. Architectural Boundaries
- Consumes identical `ProcessedText` instances as `TfidfRetriever`.
- Derives all corpus statistics strictly from indexed target documents without ground-truth knowledge.
- Evaluated independently via `BenchmarkRunner(artifact_type_filter="source_code")`.

---

## Structure-Guided Retrieval Baseline: Identifier Signatures + Dependency Graph (Milestone B3)

### 1. Scope & Role
`StructuralRetriever` is located in `src/tracewise/retrieval/structural.py` and implements `BaseRetriever`. It serves as the structure-guided identifier + dependency retrieval baseline (B3) for requirement-to-code traceability in TraceWise.

B3 provides an isolated test of structure-guided retrieval:
- **Seed Activation**: Requirement tokens are matched only against declared structural entity / identifier terms to create initial seed activation.
- **Dependency Propagation**: Intra-code graph dependencies then propagate that seed signal across an intra-code dependency graph.
- **Boundaries**: Full code-text lexical retrieval is not used; dense embeddings are not used; LLM/RAG is not used.
- **Terminology Caveat**: B3 is not a completely lexical-free structural method because initial seed activation relies on matching requirement tokens against declared entity identifiers.

### 2. Algorithmic Formulation & Design
1. **Target Structural Signatures**:
   For each indexed code artifact chunk $c \in V$, its declared identifier name is extracted from `metadata["name"]` (or derived from symbol parts of `source_id`). Constituent structural terms $T_{\text{struct}}(c)$ are extracted by splitting compound identifiers (camelCase, PascalCase, snake_case) and inheriting parent class terms if hierarchical (Python methods belonging to classes). Generic keywords and dunder names are filtered.

2. **Deterministic Intra-Code Dependency Graph $G = (V, E)$**:
   Constructed directly from the target code corpus without external knowledge:
   - **Hierarchy / Enclosure**: Bidirectional edge if `parent_id` links child methods/classes to parent classes/modules.
   - **Intra-corpus Entity References**: Directed edge $(u, v)$ if chunk $u$'s source code explicitly references the declared symbol identifier of chunk $v$ (excluding language reserved keywords).
   - **Propagation Neighborhood**: Undirected structural diffusion neighborhood $N(c) = \{u \in V \mid (u, c) \in E \lor (c, u) \in E\}$. Node degree is $\text{deg}(c) = \max(1, |N(c)|)$.
   - **Graph Extraction Limitation**: Reference edges are inferred from explicit symbol-name occurrences in source text using deterministic matching. This is an approximation of true program dependencies and may include false structural edges from textual occurrences; it is not a compiler-verified call graph or complete dependency graph.

3. **Requirement Query Scoring**:
   For a requirement query $q$ with tokens $T(q)$:
   - **Direct Structural Match (Seed Activation)**:
     $$S_{\text{seed}}(q, c) = \frac{|T(q) \cap T_{\text{struct}}(c)|}{|T_{\text{struct}}(c)|} \quad (\text{if } |T_{\text{struct}}(c)| > 0 \text{ else } 0.0)$$
   - **Structural Dependency Propagation (Normalized 1-Hop Diffusion)**:
     $$S_{\text{graph}}(q, c) = \frac{1}{\sqrt{\text{deg}(c)}} \sum_{u \in N(c)} \frac{S_{\text{seed}}(q, u)}{\sqrt{\text{deg}(u)}} \quad (\text{if } |N(c)| > 0 \text{ else } 0.0)$$
   - **Composite Structural Score**:
     $$S(q, c) = (1 - \alpha) \cdot S_{\text{seed}}(q, c) + \alpha \cdot S_{\text{graph}}(q, c)$$
     where $\alpha = 0.5$ is a fixed, a priori equal-weight design choice between direct identifier-based seed activation and structural neighbor diffusion. It was not tuned using benchmark ground truth.
   - **Candidate Ranking**: Sorted by `(-score, target_id)` with consecutive 1-based ranks. Candidate metadata includes `seed_score`, `graph_score`, and `degree`.

### 3. Architectural Boundaries & Isolation
- B3 is strictly isolated: no ground-truth trace links are accessed during indexing or scoring.
- No hybrid fusion (B4), no LLM generation (B5), and no developer verification labels are used.
- Evaluated independently via `MultiProjectBenchmarkRunner`.
- **Experimental Interpretation**: B3 provides an isolated test of structure-guided retrieval. Its mixed performance indicates that structural information contains useful signal but is insufficient as a standalone retrieval mechanism on these benchmarks.


---

## Evaluation Layer & Benchmark Harness (Milestone 3A)


### 1. Scope & Package Location
The evaluation module resides in `src/tracewise/evaluation/`:
- `models.py`: Domain models `QueryEvaluationResult` and `EvaluationResult`
- `ground_truth.py`: Ground-truth loader (`load_ground_truth`) producing `dict[str, set[str]]`
- `metrics.py`: Information Retrieval metrics (`precision_at_k`, `recall_at_k`, `average_precision`, `mean_average_precision`, `reciprocal_rank`, `mean_reciprocal_rank`, `evaluate_query`, `evaluate_retrieval`)
- `runner.py`: End-to-end evaluation runner (`BenchmarkRunner`, `run_sample_project_benchmark`)

### 2. Architectural Boundaries & Data Flow
Evaluation operates strictly downstream of candidate retrieval:
```
Artifacts & Chunks → Preprocessor → ProcessedText
                                          ↓
                               BaseRetriever.index()
                                          ↓
                             BaseRetriever.retrieve()
                                          ↓
                             RetrievalCandidate[] (Hypotheses)
                                          ↓
           Independent Ground Truth (trace_links.json)
                                          ↓
               Evaluation Layer (metrics & benchmark runner)
                                          ↓
                              EvaluationResult (Typed)
```

The retrieval layer has zero access to ground truth, gold link files, or evaluation metrics. The evaluation layer accepts algorithm-agnostic `RetrievalCandidate` lists and independently evaluates them against ground-truth target sets.

### 3. Evaluation Granularity & Exact Target Matching
In the TraceWise evaluation harness:
- **Exact Target Matching**: Candidate `target_id` is matched exactly against ground-truth `artifact_id` entries.
- **Granularity Preservation**: Coarse-grained units (such as class chunks) and fine-grained units (such as methods or standalone functions) are not interchangeable. If ground truth specifies `src/auth/service.py#AuthenticationService.authenticate_user`, retrieving the enclosing class `src/auth/service.py#AuthenticationService` counts as a false positive.

### 4. Metric Semantics & Edge-Case Conventions
- **Precision@k**: $\frac{|\{c \in \text{top-}k \mid c.\text{target\_id} \in \text{relevant\_targets}\}|}{k}$. Divides by $k$ per standard TREC/IR convention even if fewer than $k$ candidates were retrieved. Returns $0.0$ if $k \le 0$ raises `ValueError`, or if relevant/candidate sets are empty.
- **Recall@k**: $\frac{|\{c \in \text{top-}k \mid c.\text{target\_id} \in \text{relevant\_targets}\}|}{|\text{relevant\_targets}|}$. Returns $0.0$ if relevant targets set is empty.
- **Average Precision (AP)**: $\frac{\sum_{i=1}^k P(i) \times \text{rel}(i)}{|\text{relevant\_targets}|}$. Divides by the total count of known relevant targets in ground truth.
- **Mean Average Precision (MAP)**: Unweighted mean of AP across all queries in ground truth having at least one relevant target. Queries with zero retrieved items receive an AP of $0.0$.
- **Reciprocal Rank (RR)**: $\frac{1}{\text{rank of first relevant candidate}}$ within cutoff $k$, else $0.0$.
- **Mean Reciprocal Rank (MRR)**: Unweighted mean of RR across all queries with at least one relevant target.
- **Duplicate Handling**: In arbitrary candidate lists containing duplicate target IDs, each unique relevant target receives credit at most once.

---

## Real-Project Evaluation Infrastructure (Milestone 4B)

### 1. Research Context & External Validity
The synthetic `sample_project` benchmark (10 requirements, 26 source chunks, 16 ground-truth links) serves as a controlled, deterministic development benchmark for unit testing and baseline verification.

However, a controlled synthetic dataset is **not sufficient** to establish external validity or generalization across realistic software projects with larger vocabularies, varying code styles, and complex dependency structures.

Milestone 4B provides the project-level benchmark infrastructure required to evaluate TraceWise across multiple realistic software repositories without modifying baseline algorithms or compromising experimental rigor.

> [!NOTE]
> TraceWise has not yet been validated on large-scale real-world projects. Milestone 4B establishes the experimental infrastructure and evaluation protocol so that multi-project evaluations can be executed rigorously in future phases.

### 2. Architectural Separation & Invariants
The benchmark framework enforces strict boundaries:
```
Project Artifacts (Raw)
       ↓
ProjectIngestionAdapter (Ingestion + PythonChunker + Preprocessor)
       ↓
BenchmarkProject (Isolated Normalized Representation)
 ├── Requirements (ProcessedText[])
 ├── Source Code Target Corpus (ProcessedText[])
 └── Ground Truth (dict[query_id, set[target_id]])
       ↓
BaseRetriever.index(source_artifacts)   [NO ACCESS TO GROUND TRUTH]
       ↓
BaseRetriever.retrieve(requirement)     [NO ACCESS TO GROUND TRUTH]
       ↓
RetrievalCandidate[] (Hypotheses)
       ↓
MultiProjectBenchmarkRunner (Evaluation Layer)
 ├── validate_benchmark_project()
 ├── evaluate_retrieval()
 ├── Scalability Telemetry (timing & chunk counts)
 └── Macro & Micro Aggregation
```

Key research invariants:
- **Zero Ground-Truth Contamination**: Ground truth is completely decoupled from retrieval and is evaluated strictly downstream.
- **Fair Baseline Comparison**: Every retriever (B0, B1, B2, and future methods) must be evaluated against the exact same project data, preprocessing, chunking, and ground truth.
- **Candidate $\ne$ Validated Link**: Retrieval produces candidate hypotheses; evaluation measures retrieval quality independently.

### 3. Real-Project Evaluation Protocol

The evaluation workflow follows a structured four-stage protocol:

1. **Manifest Declaration**: Each benchmark project defines a declarative manifest (`BenchmarkProjectManifest`) specifying relative paths, artifact patterns, and configuration options without hard-coding dataset-specific assumptions.
2. **Ingestion & Normalization**: The `ProjectIngestionAdapter` processes raw artifacts into normalized `ProcessedText` objects using the same shared chunking and preprocessing contracts.
3. **Integrity Validation**: Before any retrieval execution, `validate_benchmark_project()` enforces dataset integrity:
   - Uniqueness of requirement IDs and source chunk IDs.
   - Referential integrity (all ground-truth links point to existing requirements and source chunks).
   - Exclusion of test artifacts from source-code evaluations.
   - Absence of duplicate ground-truth links.
   - Non-emptiness of requirement and source target corpuses.
4. **Execution & Telemetry**: `MultiProjectBenchmarkRunner` executes the retriever across all specified projects, measuring:
   - Indexing time ($\text{sec}$)
   - Query retrieval time ($\text{sec}$)
   - Total execution time ($\text{sec}$)
   - Evaluated candidate volume
5. **Metric Aggregation**:
   - **Macro-average**: Unweighted arithmetic mean across projects:
     $$\text{Macro-}M = \frac{1}{|P|} \sum_{p \in P} M_p$$
     Treats each software project as an equal unit of observation.
   - **Micro-average (Pooled)**: Query-weighted average pooled across all queries in all projects:
     $$\text{Micro-}M = \frac{1}{\sum_{p} |Q_p|} \sum_{p \in P} \sum_{q \in Q_p} \text{Metric}(q)$$
     Reflects global query-level retrieval accuracy.

---

## External Benchmark Integration: iTrust (Milestone 4C / 4C-R)

### 1. Benchmark Variant & Provenance
The external software engineering benchmark integrated into TraceWise is the **iTrust req2code benchmark variant sourced from the LiSSA ICSE 2025 replication package**:
- **Source Repository:** `ardoco/Replication-Package-ICSE25_LiSSA-Toward-Generic-Traceability-Link-Recovery-through-RAG` (Zenodo DOI: [10.5281/zenodo.14714706](https://doi.org/10.5281/zenodo.14714706))
- **Repository Commit:** `a8e652f29bbdcc4bdcd3d98cd85aa4a37cb65480` (tagged `v1.0.0`)
- **Exact Subdirectory:** `LiSSA-RATLR-V2/lissa/datasets/req2code/iTrust/`
- **Canonical Checksum (UC2JAVA.csv):** `36e57100b6fa0066252b0b147bc79f5424e1fe739ca4c50d66f67fbbba9a6acd`

> [!IMPORTANT]
> **Variant Disclaimer:** Different processed iTrust variants exist in the literature and research repositories (e.g., Asuncion et al. 2010, Gethers et al. 2011, TEFSE 2011, Ben Charrada et al., and historical CoEST dumps with differing use-case subsets). TraceWise intentionally uses the LiSSA req2code variant and **does not claim equivalence with every published iTrust benchmark**.

### 2. Licensing & Redistribution Audit
- **LiSSA Tooling License:** MIT License (`Copyright (c) 2025 ArDoCo`).
- **Third-Party iTrust Assets:** The original software application and requirements were authored at North Carolina State University (NCSU CSC326) and curated by CoEST. The raw files bundled in the replication package lack an explicit, standalone license header.
- **Redistribution Policy:** Because third-party redistribution rights for the raw iTrust files cannot be established confidently from upstream headers, TraceWise does not claim unrestricted redistribution. The raw dataset directories are excluded via `.gitignore`, and reproducible setup is supported via `scripts/setup_itrust.py` and manual placement.

### 3. Measured Scale & Dimensions
TraceWise avoids describing iTrust as "large-scale" and instead characterizes it as:
> **An external real-world traceability benchmark of moderate size relative to the current synthetic fixture.**
The purpose is external validation and independent ground truth, not proof of large-scale scalability.

Measured dimensions:
- **Total Requirements:** 131 use-case subflows (`UC/*.txt`)
- **Evaluable Requirements ($\ge 1$ gold link):** 105
- **Zero-Link Requirements ($0$ gold links):** 26
- **Source Classes:** 226 Java classes (`CC/*.java`, compilation units)
- **Gold-Standard Trace Links:** 286 unique links (`UC2JAVA.csv`)
- **Disk Footprint:** ~814 KB

### 4. Granularity Alignment & Mapping
- **Requirement Granularity**: Use-Case Scenario / Exception level (e.g., `UC10E1`, `UC1S1`). Extracted via filename stem (`Path(file).stem`).
- **Code Granularity**: Class / Compilation Unit level (e.g., `AddPatientAction`, `PatientDAO`). Each file in `CC/` defines a single class.
- **Structural Chunker**: Implemented `FileChunker(use_stem_as_id=True)`, which wraps each source compilation unit into a deterministic `ArtifactChunk` with `id == stem` and `granularity == "class"`, perfectly aligning target chunk IDs with gold-standard link identifiers.
- **Ground-Truth Adapters**: Implemented `CsvGroundTruthAdapter` (supporting the canonical 2-column `UC2JAVA.csv`) alongside `JsonGroundTruthAdapter`.

### 5. Evaluation Query Denominator & Ranking Semantics
In information retrieval evaluation for requirements traceability, evaluating queries without ground-truth relevant targets creates ambiguity:
- **Total Requirements Ingested:** 131 use-case subflows.
- **Evaluable Requirements ($|Q_{\text{eval}}| = 105$):** Requirements that have $\ge 1$ ground-truth link in `UC2JAVA.csv`.
- **Zero-Link Requirements ($|Q_{\text{zero}}| = 26$):** Requirements present in the specification corpus for which no source code links exist in the gold standard.

According to the TraceWise evaluation protocol, ranking evaluation metrics ($\text{MAP}$, $\text{MRR}$, $\text{Precision}@k$, $\text{Recall}@k$) are defined only over evaluable queries ($N = 105$). Zero-link queries are excluded from ranking metrics according to the TraceWise evaluation protocol because recall is undefined when the gold relevant set is empty; including such queries would change the macro-averaging protocol.

TraceWise strictly documents:
- Metric denominator $N = 105$ for all published ranking metrics.
- Total requirement corpus count ($131$) and zero-link query count ($26$) in evaluation telemetry and summary tables.

### 6. Leakage Controls & Pre-Execution Validation
- **Requirement vs. Source Target Separation**: Requirements are strictly ingested under `ArtifactType.REQUIREMENT` and never indexed as retrieval targets.
- **Test Exclusion**: The 226 source files in `CC/` are production classes; zero test files enter the candidate target corpus.
- **Retriever Isolation**: Retrievers receive only `project.source_artifacts` during `retriever.index()` and query text during `retriever.retrieve()`. Neither ground truth nor candidate ranking feedback enters any retriever.
- **Zero Retuning**: B0, B1, and B2 parameters are identical across synthetic and real benchmarks.

### 7. Empirical Baseline Results on iTrust
Evaluated using `MultiProjectBenchmarkRunner` on Requirements $\to$ Source Code ($N = 105$ evaluable requirements, $226$ candidate source classes, $286$ gold links):
| Model | MAP | MRR | P@1 | P@3 | P@5 | R@1 | R@3 | R@5 | Index Time | Query Time |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **B0 (TF-IDF)** | 0.3006 | 0.4194 | 0.2286 | 0.2413 | 0.2000 | 0.0895 | 0.2825 | 0.3913 | 0.075s | 0.380s |
| **B1 (BM25)** | 0.3718 | 0.5144 | 0.3524 | 0.2984 | 0.2190 | 0.1490 | 0.3554 | 0.4177 | 0.064s | 0.339s |
| **B2 (Semantic)**| 0.0790 | 0.1441 | 0.0571 | 0.0571 | 0.0438 | 0.0162 | 0.0594 | 0.0832 | 13.138s | 3.191s |

### 8. Corrected Interpretation of B2 Semantic Retrieval
The low performance observed for B2 on iTrust (MAP 0.0790 vs BM25 0.3718) requires careful research interpretation:
- **Specific Configuration Finding:** The current B2 configuration (`all-MiniLM-L6-v2` sentence-transformers embedding applied to TraceWise normalized requirement/class text) performs poorly on the selected iTrust benchmark.
- **No Overgeneralization:** This result **must not** be interpreted as evidence that dense semantic retrieval in general fails, nor that modern embedding representations or LLMs cannot trace software requirements.
- **Underlying Cause:** `all-MiniLM-L6-v2` is a general natural-language sentence encoder with a 256-wordpiece context window. It suffers from a pronounced vocabulary and distribution gap when matching clinical medical requirements to Java source code containing camelCase identifiers, SQL queries, and architectural boilerplate, in the absence of code-domain pretraining, fine-tuning, or structural context.

### 9. Synthetic Regression Invariants
The controlled synthetic benchmark (`sample_project`) remains frozen and identical to 4 decimal places:
- **B0 (TF-IDF)**: MAP 0.7485, MRR 0.8500
- **B1 (BM25)**: MAP 0.7030, MRR 0.8033
- **B2 (Semantic)**: MAP 0.7350, MRR 0.8500

---

## External Benchmark Integration: eTour (Milestone 4D)

### 1. Benchmark Variant & Provenance
The second external software engineering benchmark integrated into TraceWise is the **eTour req2code benchmark variant sourced from the LiSSA ICSE 2025 replication package**:
- **Source Repository:** `ardoco/Replication-Package-ICSE25_LiSSA-Toward-Generic-Traceability-Link-Recovery-through-RAG` (Zenodo DOI: [10.5281/zenodo.14714706](https://doi.org/10.5281/zenodo.14714706))
- **Repository Commit:** `a8e652f29bbdcc4bdcd3d98cd85aa4a37cb65480` (tagged `v1.0.0`)
- **Exact Subdirectory:** `LiSSA-RATLR-V2/lissa/datasets/req2code/eTour_en/`
- **Canonical Checksum (UC2CC.csv):** `bb9081ab8b1a0a42614ac25a19b0c044f9ec52323c074d6cd19eee0cd6154fde`

> [!IMPORTANT]
> **Variant Disclaimer:** Multiple processed versions of eTour exist across literature repositories (original Italian requirements vs English translations, character encodings, differing link formatting). TraceWise explicitly uses the English-translated `eTour_en` variant bundled in the LiSSA ICSE 2025 replication package and does not claim equivalence with every published eTour benchmark dataset.

### 2. Licensing & Redistribution Audit
- **LiSSA Tooling License:** MIT License (`Copyright (c) 2025 ArDoCo`).
- **Third-Party eTour Assets:** Developed at the University of Salerno for the TEFSE 2011 academic benchmark and curated by CoEST. The raw files bundled in the replication package lack an explicit standalone license header.
- **Redistribution Policy:** Raw files are excluded via `.gitignore`, with local replication supported through `scripts/setup_etour.py`.

### 3. Measured Scale & Dimensions
- **Dataset Scale:** An external real-world traceability benchmark of moderate size relative to the current synthetic fixture.
- **Total Requirements:** 58 use cases (`UC/*.txt`)
- **Evaluable Requirements ($\ge 1$ gold link):** 57
- **Zero-Link Requirements ($0$ gold links):** 1 (`UC37`)
- **Source Classes:** 116 Java classes (`CC/*.java`, single compilation units)
- **Gold-Standard Trace Links:** 308 unique links (`UC2CC.csv`)

### 4. Empirical Baseline Results on eTour
Evaluated using `MultiProjectBenchmarkRunner` on Requirements $\to$ Source Code ($N = 57$ evaluable requirements, $116$ candidate source classes, $308$ gold links):

| Model | MAP | MRR | P@1 | P@3 | P@5 | R@1 | R@3 | R@5 | Index Time | Query Time |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **B0 (TF-IDF)** | 0.3878 | 0.6636 | 0.5263 | 0.4386 | 0.3509 | 0.1211 | 0.2686 | 0.3686 | 0.014s | 0.021s |
| **B1 (BM25)** | 0.2987 | 0.5994 | 0.4035 | 0.3567 | 0.2772 | 0.0712 | 0.2332 | 0.2969 | 0.012s | 0.019s |
| **B2 (Semantic)**| 0.4329 | 0.6918 | 0.5439 | 0.4620 | 0.4035 | 0.1129 | 0.2685 | 0.3952 | 2.985s | 0.715s |

### 5. Cross-Project Synthesis & Methodological Suitability
Comparing performance across all three benchmarks:

| Project | Domain | Reqs (Eval) | Classes | Links | Density | B0 MAP | B1 MAP | B2 MAP | B3 MAP |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `sample_project` | Financial Auth | 10 (10) | 26 | 16 | 1.60 | 0.7485 | 0.7030 | 0.7350 | 0.3977 |
| `itrust` | Healthcare | 131 (105) | 226 | 286 | 2.72 | 0.3006 | 0.3718 | 0.0790 | 0.1770 |
| `etour` | Tourism Guide | 58 (57) | 116 | 308 | 5.40 | 0.3878 | 0.2987 | 0.4329 | 0.2755 |

**Methodological Suitability for Cross-Project Comparison:**
eTour and iTrust are methodologically suitable because:
1. **Domain Diversity:** Tourism navigation vs medical management vs synthetic finance.
2. **Link Density Variation:** 5.40 links/query on eTour vs 2.72 on iTrust vs 1.60 on synthetic.
3. **Lexical & Identifier Characteristics:** English use cases with Italian/English domain class names test lexical term overlap and semantic generalization under differing linguistic conditions.
4. **Different Relative Model Behaviors:** On iTrust, BM25 outperforms TF-IDF, B3 outperforms B2 (0.1770 vs 0.0790), and Semantic performs poorly. On eTour, Semantic outperforms TF-IDF, which outperforms BM25 and B3.
5. **Research Interpretation:** Cross-project variation in retrieval performance motivates evaluating hybrid retrieval and evidence-backed verification as candidate approaches rather than assuming a single retrieval paradigm is sufficient.

**Artifact-Granularity Caveat & Methodological Notes:**
- `sample_project` is evaluated using Python AST-level source chunks (functions, methods, classes).
- `itrust` and `etour` are evaluated at the Java compilation-unit/class level.
- Therefore, B0 vs B1 vs B2 vs B3 comparisons **within** each project are directly controlled and fair.
- Absolute metric values **across** projects should not be interpreted as directly comparable difficulty scores because artifact granularity differs.
- Cross-project analysis is used primarily to examine relative retriever behavior and robustness trends.

### 6. Frozen Multi-Project Baseline Record

| Parameter / Dimension | B0 (TF-IDF) | B1 (BM25) | B2 (Dense Semantic) | B3 (Structural) |
| :--- | :--- | :--- | :--- | :--- |
| **Model / Algorithm** | Sublinear TF + Smoothed IDF + Cosine | Okapi BM25 ($k_1=1.5, b=0.75$) + Softmax | `all-MiniLM-L6-v2` (ONNX via fastembed) + Cosine | Entity Signatures + Intra-code Dependency Graph ($\alpha=0.5$) |
| **Embedding Dimension** | N/A (sparse lexical) | N/A (sparse probabilistic) | 384 dimensions (dense) | N/A (graph/signature) |
| **Context Window** | Document-level | Document-level | 256 wordpiece tokens | Document-level & corpus dependency graph |
| **Fine-Tuning** | None | None | None (zero target training) | None (zero target training, no ground-truth access) |
| **Preprocessing** | Lowercase, code tokenize, stopwords | Lowercase, code tokenize, stopwords | Normalized text fallback to token join | Code tokenization / identifier splitting |
| **Candidate Tie-Break** | `(-score, target_id)` ascending | `(-score, target_id)` ascending | `(-score, target_id)` ascending | `(-score, target_id)` ascending |
| **Target Exclusion** | Source code only (tests excluded) | Source code only (tests excluded) | Source code only (tests excluded) | Source code only (tests excluded) |
| **Evaluation Denominator**| Evaluable queries ($\ge 1$ gold link). Zero-link queries excluded per protocol | Same | Same | Same |
| **Environment Backend**| Python 3.14, NumPy 2.5.3 | Python 3.14, NumPy 2.5.3 | fastembed 0.8.1, onnxruntime 1.30.0 | Python 3.14, regular expressions |






