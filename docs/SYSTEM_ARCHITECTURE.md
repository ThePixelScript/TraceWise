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
Preprocessed Tokens / Normalized Text
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

## Retrieval Layer Contracts

### 1. Scope & Package Location
The retrieval contracts reside in `src/tracewise/retrieval/`:
- `models.py`: `RetrievalCandidate`, `ProcessedText`
- `base.py`: `BaseRetriever` abstract base class
- `exceptions.py`: `RetrieverError`, `NotIndexedError`

### 2. Architectural Flow
The retrieval layer sits between text preprocessing and evaluation / link creation:
```
ProcessedText (query / corpus)
    ↓
BaseRetriever.index(documents) / retrieve(query, top_k)
    ↓
RetrievalCandidate[] (query_id, target_id, score, rank, retriever_name)
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

### 5. Future Concrete Implementations
Concrete retrieval algorithms (such as TF-IDF, BM25, and dense semantic embeddings) will implement `BaseRetriever` in upcoming milestones.
