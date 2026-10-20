# TraceWise Dataset Audit Report: Provenance, Artifact Inventory & Ground-Truth Verification

**Report Version:** 1.0.0  
**Audit Date:** October 20, 2026  
**Auditor:** TraceWise Research & Evaluation Team (Nannan)  
**Base Commit Reference:** `102721a6a5fd280132d6647316041a14f3ac6031`  
**Target Branch:** `research/dataset_audit`  
**Downstream Reviewers:** Arun (`research/evaluation_protocol`), Divesh (`feature/evaluation_instrumentation`)

---

## 1. Executive Summary & Purpose

### 1.1 Objective & Context
This audit provides an exhaustive, source-verified accounting of the three software datasets currently integrated into the TraceWise traceability and change impact analysis platform:
1. **`sample_project`** (Synthetic Python Microservice Baseline)
2. **`itrust`** (Real-World Academic Java EHR Benchmark, LiSSA ICSE 2025 variant)
3. **`etour`** (Real-World Academic Java Tourism Benchmark, LiSSA ICSE 2025 variant)

As TraceWise transitions from retrieval baseline benchmarking (Milestones B0–B5) to human-in-the-loop developer evaluation (Milestone B6) and automated instrumentation (Milestone B7), every empirical assertion must rest upon unambiguous provenance, verified artifact inventories, mathematically sound denominators, and validated ground-truth link sets.

### 1.2 Key Audit Findings
- **Zero Integrity Violations:** All three benchmark datasets pass automated integrity validation (`validate_benchmark_project()` in `src/tracewise/evaluation/validation.py`) with **zero errors and zero warnings**.
- **100% Ground-Truth Reachability:** Every single ground-truth traceability link in `sample_project` (16 links), `iTrust` (286 links), and `eTour` (308 links) maps to a strictly valid requirement identifier and an existing target source code chunk. There are no orphan links or unresolved file paths.
- **Explicit Denominator Specification:**
  - `sample_project` contains **10 requirements**, all **10 evaluable** (100% evaluable, 0 zero-link queries).
  - `iTrust` contains **131 requirements**, of which **105 are evaluable** ($\ge 1$ gold link) and **26 are zero-link queries** (0 gold links).
  - `eTour` contains **58 requirements**, of which **57 are evaluable** ($\ge 1$ gold link) and **1 is a zero-link query** (`UC37`).
  - TraceWise ranking metrics (MAP, MRR, P@k, R@k) strictly evaluate across evaluable queries ($N=10, 105, 57$), completely excluding zero-link queries from the ranking denominator to prevent undefined recall and skewed macro-averaging.
- **Granularity Disparity Identified:** `sample_project` is chunked at the fine-grained Python AST level (classes, top-level functions, and class methods), whereas `iTrust` and `eTour` are chunked at the coarse-grained Java compilation unit (class file) level.
- **Licensing & Hygiene Isolation:** Raw academic assets for `iTrust` and `eTour` reside under local directory caches excluded from Git tracking via `.gitignore`, accompanied by deterministic automated setup scripts (`scripts/setup_itrust.py`, `scripts/setup_etour.py`) with enforced SHA-256 integrity verification.

---

## 2. Dataset Provenance & Legal/Redistribution Audit

### 2.1 Synthetic Baseline: `sample_project`
* **Origin & Authority:** Artificially constructed in-house by the TraceWise engineering team as a controlled test fixture for ingestion, AST chunking, preprocessing, and Change Impact Analysis (CIA).
* **Domain:** RESTful microservice for user authentication, token management, credential hashing, profile retrieval, and rate limiting.
* **Source Location:** `data/fixtures/sample_project/`
* **Language & Runtime:** Python 3.10+ (Standard Library only; no third-party package dependencies).
* **Licensing Status:** Internal project asset; fully licensed under the TraceWise repository open-source terms.
* **Experimental Purpose:**
  - Fast, deterministic unit and regression testing.
  - Verification of Python AST chunking boundaries (`PythonChunker`).
  - Verification of intentionally ambiguous cross-module vocabulary (e.g., `user` shared between `AuthenticationService`, `UserService`, and `RateLimiter`).
  - Validation of change scenarios (`data/fixtures/sample_project/change_scenarios.json`).
* **Limitations:** Small scale (10 requirements, 8 source files, 26 chunks); shallow call graph; no third-party library calls.

### 2.2 External Benchmark: `iTrust`
* **Canonical Identification:** iTrust `req2code` benchmark variant sourced from the LiSSA ICSE 2025 replication package.
* **Upstream Source Repository:** [`ardoco/Replication-Package-ICSE25_LiSSA-Toward-Generic-Traceability-Link-Recovery-through-RAG`](https://github.com/ardoco/Replication-Package-ICSE25_LiSSA-Toward-Generic-Traceability-Link-Recovery-through-RAG)
* **Replication DOI:** [10.5281/zenodo.14714706](https://doi.org/10.5281/zenodo.14714706)
* **Pinned Commit:** `a8e652f29bbdcc4bdcd3d98cd85aa4a37cb65480` (tagged `v1.0.0`)
* **Extracted Subdirectory:** `LiSSA-RATLR-V2/lissa/datasets/req2code/iTrust/`
* **Historical Origin:** North Carolina State University (NCSU, CSC326 course project), curated by the Center of Excellence for Software & Systems Traceability (CoEST).
* **Domain:** Electronic Health Records (EHR) and clinical patient management system.
* **Source Location:** `data/benchmarks/itrust/`
* **Language & Runtime:** Java (J2EE web application structure).
* **Canonical Checksums (SHA-256):**
  - `UC2JAVA.csv`: `36e57100b6fa0066252b0b147bc79f5424e1fe739ca4c50d66f67fbbba9a6acd`
  - `source_req.xml`: `2f2ffef238a2f59ddecaf59a88cd7d0fad890c0d7ea6725feff640cf46cc9026`
  - `target_JavaCode.xml`: `10b808194aca1f2f02e5d856bcb7996fddbc75aabb714f936a293064ad879cc2`
* **Licensing & Redistribution Audit:**
  - The LiSSA replication tooling framework is released under the **MIT License** (`Copyright (c) 2025 ArDoCo`).
  - However, third-party redistribution terms for the underlying NCSU/CoEST iTrust Java source code and requirement specifications cannot be established with certainty from upstream file headers.
  - **TraceWise Policy:** To maintain strict copyright compliance, TraceWise **does not track or redistribute raw iTrust source files** in the public Git tree. Raw dataset directories (`data/benchmarks/itrust/UC/`, `CC/`, `UC2JAVA.csv`, `trace_links.json`) are strictly excluded via `.gitignore`.
  - **Automated Acquisition:** The script `scripts/setup_itrust.py` performs a shallow, sparse git clone of commit `a8e652f`, copies the canonical files, generates `trace_links.json`, and verifies the SHA-256 hash.
* **Variant Disambiguation Notice:** Multiple non-identical variants of iTrust exist in the traceability literature (Asuncion et al. 2010, Gethers et al. 2011, TEFSE 2011). TraceWise explicitly evaluates the LiSSA ICSE 2025 `req2code` variant and does not assert equivalence with historical variants.

### 2.3 External Benchmark: `eTour`
* **Canonical Identification:** eTour `req2code` benchmark variant sourced from the LiSSA ICSE 2025 replication package.
* **Upstream Source Repository:** [`ardoco/Replication-Package-ICSE25_LiSSA-Toward-Generic-Traceability-Link-Recovery-through-RAG`](https://github.com/ardoco/Replication-Package-ICSE25_LiSSA-Toward-Generic-Traceability-Link-Recovery-through-RAG)
* **Replication DOI:** [10.5281/zenodo.14714706](https://doi.org/10.5281/zenodo.14714706)
* **Pinned Commit:** `a8e652f29bbdcc4bdcd3d98cd85aa4a37cb65480` (tagged `v1.0.0`)
* **Extracted Subdirectory:** `LiSSA-RATLR-V2/lissa/datasets/req2code/eTour_en/`
* **Historical Origin:** Developed by software engineering students at the University of Salerno (Italy), introduced at TEFSE 2011 (6th International Workshop on Traceability in Emerging Forms of Software Engineering), and archived by CoEST.
* **Domain:** Electronic Tourist Guide (eTour) mobile/desktop tourism and point-of-interest management.
* **Source Location:** `data/benchmarks/etour/`
* **Language & Runtime:** Java (client/server architecture; Italian source identifiers with English requirement translations).
* **Canonical Checksum (SHA-256):**
  - `UC2CC.csv`: `bb9081ab8b1a0a42614ac25a19b0c044f9ec52323c074d6cd19eee0cd6154fde`
* **Licensing & Redistribution Audit:**
  - Upstream tooling framework is MIT-licensed.
  - Original TEFSE academic dataset files lack explicit standalone redistribution headers.
  - **TraceWise Policy:** Raw files (`data/benchmarks/etour/UC/`, `CC/`, `UC2CC.csv`, `trace_links.json`) are excluded from Git tracking via `.gitignore`.
  - **Automated Acquisition:** The script `scripts/setup_etour.py` performs a shallow, sparse git clone of commit `a8e652f`, copies the canonical English-translated use cases and class files, generates `trace_links.json`, and verifies the SHA-256 hash.
* **Variant Disambiguation Notice:** TraceWise explicitly targets the English-translated `eTour_en` variant bundled in LiSSA ICSE 2025.

---

## 3. Manifest & Artifact Inventory

### 3.1 Declarative Manifest Configuration
Every benchmark project in TraceWise is defined by a declarative manifest (`benchmark_manifest.json`) adhering to `BenchmarkProjectManifest` (`src/tracewise/evaluation/manifest.py`).

| Configuration Field | `sample_project` | `itrust` | `etour` |
| :--- | :--- | :--- | :--- |
| **`project_id`** | `sample_project` | `itrust` | `etour` |
| **`project_name`** | Sample Project (Synthetic IDP Baseline) | iTrust (LiSSA ICSE 2025 req2code variant) | eTour (LiSSA ICSE 2025 req2code variant) |
| **`requirement_source`** | `requirements/*.md` | `UC/*.txt` | `UC/*.txt` |
| **`source_path`** | `src/**/*.py` | `CC/*.java` | `CC/*.java` |
| **`ground_truth_path`** | `trace_links.json` | `UC2JAVA.csv` | `UC2CC.csv` |
| **`ground_truth_format`** | `json` | `csv` | `csv` |
| **`requirement_artifact_type`** | `requirement` | `requirement` | `requirement` |
| **`source_artifact_type`** | `source_code` | `source_code` | `source_code` |
| **`chunking_config.strategy`** | *(implicit AST)* | `file` | `file` |
| **`chunking_config.granularity`** | `python_ast` | `class` | `class` |
| **`chunking_config.use_stem_as_id`** | N/A | `true` | `true` |
| **`preprocessing_config.normalize`** | `true` | `true` | `true` |
| **`preprocessing_config.tokenize_code`** | `true` | `true` | `true` |

### 3.2 Comprehensive Artifact Inventory
The table below compares the audited structural dimensions across all three datasets:

| Metric / Dimension | `sample_project` | `itrust` | `etour` | Benchmark Suite Total |
| :--- | :---: | :---: | :---: | :---: |
| **Programming Language** | Python 3.10+ | Java | Java | Multi-language |
| **Requirement Format** | Markdown (`.md`) | Plain Text (`.txt`) | Plain Text (`.txt`) | 199 text/markdown specs |
| **Total Requirement Files** | **10** | **131** | **58** | **199 requirements** |
| **Evaluable Requirements ($\ge 1$ Gold Link)** | **10** (100.0%) | **105** (80.15%) | **57** (98.28%) | **172 evaluable** (86.43%) |
| **Zero-Link Requirements ($0$ Gold Links)** | **0** (0.0%) | **26** (19.85%) | **1** (1.72%) | **27 zero-link** (13.57%) |
| **Total Source Files Ingested** | **8** files | **226** files | **116** files | **350 source files** |
| **Total Target Chunks Evaluated** | **26** chunks | **226** classes | **116** classes | **368 code targets** |
| **Chunking Granularity** | Method/Function AST | Compilation Unit (Class) | Compilation Unit (Class) | Mixed granularities |
| **Raw Ground-Truth Records** | 33 records (16 code, 17 tests) | 286 records | 308 records | 627 raw records |
| **Valid Code Ground-Truth Links** | **16** links | **286** links | **308** links | **610 code links** |
| **Distinct Target Chunks in Gold Standard** | 11 chunks | 87 classes | 89 classes | 187 distinct targets |
| **Unlinked Source Target Chunks** | 15 chunks | 139 classes | 27 classes | 181 distractor targets |
| **Target Corpus Coverage by Gold Links** | 42.31% (11/26) | 38.50% (87/226) | 76.72% (89/116) | 50.82% overall |
| **Average Gold Links per Evaluable Req** | 1.60 links/req | 2.72 links/req | 5.40 links/req | 3.55 links/req |

### 3.3 Detailed Breakdown by Dataset

#### A. `sample_project` Breakdown
* **Requirements (10 files):** `REQ-001.md` through `REQ-010.md`. Each file contains structured Markdown with headers (`# REQ-XXX`, `## Title`, `## Description`, `## Acceptance Criteria`).
* **Source Files (8 files):**
  - `src/auth/__init__.py`, `src/auth/password.py`, `src/auth/service.py`, `src/auth/token.py`
  - `src/security/__init__.py`, `src/security/rate_limiter.py`
  - `src/users/__init__.py`, `src/users/service.py`
* **Source Chunks (26 chunks):**
  - `PythonChunker` extracts structural elements via Python `ast.parse`:
    - Top-level functions: e.g., `src/auth/password.py#hash_password`, `src/auth/password.py#verify_password`, `src/auth/token.py#generate_token`, `src/auth/token.py#decode_token`, `src/auth/token.py#is_token_expired`.
    - Class definitions: e.g., `src/auth/service.py#AuthenticationResult`, `src/auth/service.py#AuthenticationService`, `src/security/rate_limiter.py#RateLimiter`, `src/users/service.py#UserProfile`, `src/users/service.py#UserService`.
    - Class methods: e.g., `src/auth/service.py#AuthenticationService.authenticate_user`, `src/auth/service.py#AuthenticationService._record_attempt`, `src/auth/service.py#AuthenticationService.get_auth_log`, `src/security/rate_limiter.py#RateLimiter.record_failure`, `src/security/rate_limiter.py#RateLimiter.is_blocked`, `src/security/rate_limiter.py#RateLimiter.reset`, `src/security/rate_limiter.py#RateLimiter.get_failure_count`, `src/users/service.py#UserService.get_user_profile`, `src/users/service.py#UserService.find_user_by_email`, `src/users/service.py#UserService.list_user_ids`.
  - Notice: All three `__init__.py` files contain no function or class definitions, resulting in 0 chunks extracted from them.
* **Test Files (Excluded from Source Benchmark):**
  - 4 test files (`test_authentication.py`, `test_tokens.py`, `test_users.py`, `test_rate_limiter.py`) containing 25 test functions and 17 test trace links. These are correctly excluded from the source-code benchmark.

#### B. `iTrust` Breakdown
* **Requirements (131 files):** Located in `data/benchmarks/itrust/UC/`. Filenames follow use-case flow nomenclature:
  - Primary flows: e.g., `UC1S1.txt` (Use Case 1 Scenario 1), `UC10S1.txt`, `UC11S1.txt`, `UC13.txt`.
  - Alternative / exceptional flows: e.g., `UC1E1.txt`, `UC10E1.txt`, `UC11E1.txt`, `UC16E1.txt`.
* **Source Files & Chunks (226 files / 226 chunks):**
  - Located in `data/benchmarks/itrust/CC/`. All files end with `.java`.
  - Ingestion uses `FileChunker(use_stem_as_id=True)`. Each `.java` file represents an entire class compilation unit.
  - Chunk IDs match class names exactly without directory prefixes or `.java` extensions (e.g., `AddPatientAction`, `AuthDAO`, `EditOfficeVisitAction`, `PatientDAO`).

#### C. `eTour` Breakdown
* **Requirements (58 files):** Located in `data/benchmarks/etour/UC/`. Filenames range from `UC1.txt` to `UC58.txt`. Each contains structured English use case text (`Use case name: ...`, `Description: ...`, `Participating Actor: ...`).
* **Source Files & Chunks (116 files / 116 chunks):**
  - Located in `data/benchmarks/etour/CC/`. All files end with `.java`.
  - Ingestion uses `FileChunker(use_stem_as_id=True)`, producing chunk IDs matching the Java class names (e.g., `CulturalHeritage`, `CulturalHeritageAgencyManager`, `DBCulturalHeritage`, `BeanTourist`, `TouristAgencyManager`).

---

## 4. Ground-Truth Links & Artifact Mapping Verification

### 4.1 Resolution Architecture
TraceWise employs a deterministic pipeline to parse, normalize, and match ground-truth trace links:

```
Raw Ground Truth File (.json or .csv)
               │
               ▼
┌────────────────────────────────────────┐
│  JsonGroundTruthAdapter /               │  Strips whitespace, extracts requirement_id
│  CsvGroundTruthAdapter                  │  and artifact_id pairs, filters artifact_type
└──────────────────┬─────────────────────┘
                   │
                   ▼
┌────────────────────────────────────────┐
│  RawTraceLinkRecord Validation         │  Validates non-empty IDs; detects exact
│  (src/tracewise/evaluation/adapters.py)│  duplicate pairs before set consolidation
└──────────────────┬─────────────────────┘
                   │
                   ▼
┌────────────────────────────────────────┐
│  Path & ID Normalization               │  • Java: FileChunker stem matching (e.g., 'AuthDAO')
│  (src/tracewise/ingestion/path_utils)  │  • Python: POSIX chunk ID (e.g., 'src/...py#Class.method')
└──────────────────┬─────────────────────┘
                   │
                   ▼
┌────────────────────────────────────────┐
│  Integrity Validation Invariants       │  Enforces non-empty corpora, unique IDs,
│  (src/tracewise/evaluation/validation) │  100% ID referential integrity, no test leaks
└────────────────────────────────────────┘
```

1. **JSON Datasets (`sample_project`):** `JsonGroundTruthAdapter` loads `trace_links.json`, validates each dictionary record, and filters by `artifact_type="source_code"`. Chunk IDs follow the POSIX pattern `<relative_file_path>#<symbol>`.
2. **CSV Datasets (`iTrust`, `eTour`):** `CsvGroundTruthAdapter` inspects `UC2JAVA.csv` and `UC2CC.csv`. Both files are headerless comma-separated pairs: `RequirementID,ClassStem` (e.g., `UC1S1,AddPatientAction`). The adapter strips whitespace and maps requirement IDs to class stems.
3. **Target Chunk ID Resolution:** `FileChunker(use_stem_as_id=True)` ensures that the ingested Java file `CC/AddPatientAction.java` is assigned the chunk ID `AddPatientAction`, creating an exact string match with the CSV ground truth.

### 4.2 Comprehensive Audit & Integrity Verification Results
Running `validate_benchmark_project()` across all three projects verified the following invariants:

| Validation Rule | `sample_project` | `iTrust` | `eTour` | Status |
| :--- | :---: | :---: | :---: | :---: |
| **1. Non-empty requirement corpus** | 10 reqs | 131 reqs | 58 reqs | **PASSED** |
| **2. Non-empty target corpus** | 26 chunks | 226 classes | 116 classes | **PASSED** |
| **3. Requirement ID uniqueness** | 10/10 unique | 131/131 unique | 58/58 unique | **PASSED** |
| **4. Target chunk ID uniqueness** | 26/26 unique | 226/226 unique | 116/116 unique | **PASSED** |
| **5. Referential integrity (Requirements)**| 16/16 valid | 286/286 valid | 308/308 valid | **PASSED** (0 missing) |
| **6. Referential integrity (Code Targets)**| 16/16 valid | 286/286 valid | 308/308 valid | **PASSED** (0 missing) |
| **7. No test artifact leakage** | 0 test chunks | 0 test chunks | 0 test chunks | **PASSED** |
| **8. No duplicate raw links** | 0 duplicates | 0 duplicates | 0 duplicates | **PASSED** |

### 4.3 Zero-Link Requirement Analysis

In software traceability benchmarks, requirements that have zero ground-truth links represent a critical evaluation edge case:

1. **`sample_project` (0 zero-link requirements):** Every requirement specifies an operational feature implemented in `src/`.
2. **`iTrust` (26 zero-link requirements):**
   - The 26 requirements with 0 ground-truth links are:
     `UC16E1`, `UC19S3`, `UC1E2`, `UC1S2`, `UC22E1`, `UC22E2`, `UC22S1`, `UC22S2`, `UC22S3`, `UC25E1`, `UC30S6`, `UC30S7`, `UC31S2`, `UC32E1`, `UC32S1`, `UC33E1`, `UC33E2`, `UC33S3`, `UC40S1`, `UC40S2`, `UC40S3`, `UC40S4`, `UC40S5`, `UC40S6`, `UC40S7`, `UC4E2`.
   - **Semantic Justification:** In iTrust, use cases are segmented into scenarios (`S`) and exception paths (`E`). Many exception paths (e.g., `UC1E2`: "The patient chosen is not the desired patient") or secondary UI confirmation screens were either handled by generic JSP view scripts or never received dedicated Java action/DAO backend classes in the original student implementation.
3. **`eTour` (1 zero-link requirement):**
   - Requirement `UC37` has 0 ground-truth links in `UC2CC.csv`.
   - **Semantic Justification:** In the TEFSE 2011 benchmark, `UC37` specifies an administrative reporting feature that lacked an underlying implementation in the student codebase.

#### Evaluation Protocol Rule on Denominators
In accordance with standard IR literature and the TraceWise evaluation harness (`src/tracewise/evaluation/metrics.py`), **ranking metrics (MAP, MRR, P@k, R@k) are calculated strictly over evaluable requirements ($\ge 1$ gold link)**:
$$\text{Evaluable Denominators}: \quad N_{\text{sample}} = 10, \quad N_{\text{iTrust}} = 105, \quad N_{\text{eTour}} = 57$$
Including zero-link queries in ranking metrics would create undefined recall ($\frac{0}{0}$) and artificially deflate MAP and P@k. They are preserved in the requirement corpus for negative testing and developer investigation tasks.

### 4.4 Unlinked Source Artifact Analysis (Distractor Pool)
Source artifacts that do not appear in any ground-truth link form the natural "distractor pool" encountered during IR candidate retrieval:
- **`sample_project` (15 unlinked chunks):** Administrative or utility methods such as `UserService.list_user_ids`, `UserService.find_user_by_email`, `UserProfile`, `RateLimiter.get_failure_count`, and class headers.
- **`iTrust` (139 unlinked classes):** Data beans, hospital configuration entities, and helper DAOs that are not mapped in the LiSSA `req2code` gold standard.
- **`eTour` (27 unlinked classes):** GUI dialog helpers, database connection pool utilities, and general helpers (e.g., `DBConnectionPool`, `DeskManager`, `Category`, `TestoNewsRendererTest`, `Authentication`, `HelpManager`). Note that `GlobalConstants` is not unlinked—it is an authoritative ground-truth target linked to `UC17`, `UC19`, and `UC20`.

---

## 5. Exclusions & Ingestion Rules

TraceWise enforces multi-tiered exclusion rules to guarantee data hygiene, avoid benchmark leakage, and ensure cross-platform reproducibility:

### 5.1 Ingestor-Level Global Exclusions (`src/tracewise/ingestion/ingestor.py`)
1. **Directory Blacklist (`DEFAULT_EXCLUDED_DIRS`):**
   - Strictly defined as `frozenset({".git", ".venv", "__pycache__", "node_modules"})` in `src/tracewise/ingestion/ingestor.py:21-23`.
   - Note that plain `venv/` is ignored by Git via `.gitignore:6` rather than `DEFAULT_EXCLUDED_DIRS`.
   - Dynamic directory pruning during `os.walk` (`src/tracewise/ingestion/ingestor.py:91`) explicitly filters out directories in `self.excluded_dirs` as well as any directory name beginning with `.git` (`not d.startswith(".git")`).
   - In-place directory list pruning (`dirnames[:] = [...]`) prevents descending into virtual environments, cache directories, or Git internal objects.
2. **Supported File Extension Whitelist (`SUPPORTED_EXTENSIONS`):**
   - Whitelist: `{".txt", ".md", ".py", ".java"}`.
   - Any file with an unlisted extension (e.g., `.class`, `.pyc`, `.json`, `.csv`, `.xml`, `.png`, `.db`) is skipped during artifact traversal.
3. **Encoding Enforcement:**
   - Files are strictly read as binary bytes and decoded via UTF-8.
   - Any file containing invalid UTF-8 byte sequences raises an explicit `IngestionEncodingError`.

### 5.2 Benchmark Rule & Pattern Constraints (`src/tracewise/ingestion/rules.py`)
1. **Disjoint Glob Patterns:**
   - Ingestion rules map POSIX glob patterns to `ArtifactType` (`REQUIREMENT`, `SOURCE_CODE`, `TEST_CASE`).
   - If any discovered file matches multiple conflicting rules, `ArtifactIngestor` immediately raises `AmbiguousRuleError`.
2. **Strict Test Separation (Rule 7 Invariant):**
   - In any Requirements $\to$ Source Code benchmark, test artifacts are strictly prohibited from entering the target corpus.
   - The validation rule scans all chunks; if any chunk ID begins with `tests/` or `test/`, or if `metadata["artifact_type"] == "test_case"`, validation halts with an error.

### 5.3 Chunker-Level Rules (`python_chunker.py` and `file_chunker.py`)
1. **Empty File Handling:**
   - Files that are empty or contain only whitespace yield an empty list of chunks (`[]`).
   - In `sample_project`, packages contain `__init__.py` files for Python module resolution. Because these files contain no function or class definitions, `PythonChunker` extracts zero chunks, preventing empty modules from polluting the retrieval index.
2. **Class-Level Compaction (`FileChunker`):**
   - In Java benchmarks (`iTrust`, `eTour`), `FileChunker(use_stem_as_id=True)` treats the entire compilation unit as a single chunk identified by its filename stem, ensuring complete alignment with class-level ground truth.

### 5.4 Repository Scope & `.gitignore` Exclusions
In compliance with project governance and legal requirements, the following directories and files are strictly ignored:
- `data/benchmarks/itrust/UC/`, `CC/`, `UC2JAVA.csv`, `trace_links.json`
- `data/benchmarks/etour/UC/`, `CC/`, `UC2CC.csv`, `trace_links.json`
- `experiments/results/` (precomputed B5 candidate checkpoints and benchmark summaries)
- `data/reviews/` (developer review database `reviews.db`)

---

## 6. Audit Conclusion & Recommendations

1. **Benchmark Infrastructure Integrity:** The TraceWise ingestion, chunking, and validation pipelines are mathematically and architecturally sound.
2. **Ground-Truth Readiness:** All 16 synthetic links, 286 iTrust links, and 308 eTour links are 100% verified against actual repository files.
3. **Recommendation for Arun (Protocol):** The evaluation protocol must explicitly declare the denominator convention ($N=10, 105, 57$) in all published metrics to prevent confusion with full-corpus BM25 calculations.
4. **Recommendation for Divesh (Instrumentation):** Instrumentation should log participant verification actions across both evaluable and zero-link requirements to record negative-rejection effort.
