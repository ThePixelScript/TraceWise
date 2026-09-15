# Sample Project — Synthetic Traceability Fixture

> **⚠️ SYNTHETIC DATASET** — This is an artificially constructed dataset created
> for controlled experimentation with TraceWise. It does **not** represent real
> industrial data, a production system, or real user requirements.

## Purpose

This sample project provides a small, deterministic, human-readable software
system that TraceWise can use for:

1. **Artifact ingestion testing** — verifying that requirement, source, and test
   files are correctly parsed into `Artifact` objects.
2. **Python chunking testing** — verifying that `PythonChunker` extracts the
   expected functions, classes, and methods from the source and test files.
3. **Preprocessing testing** — verifying tokenization, normalization, and feature
   extraction on controlled inputs with known vocabulary.
4. **Retrieval experiments** — evaluating IR-based trace-link candidate retrieval
   (TF-IDF, BM25, embeddings) against ground-truth links.
5. **Trace-link evaluation** — measuring precision, recall, and F1 using the
   manually curated `trace_links.json` as the gold standard.
6. **Change Impact Analysis testing** — validating CIA logic using the
   hypothetical change scenarios in `change_scenarios.json`.

## System Description

The sample project models a simplified **authentication and user-management
system** with the following capabilities:

- User authentication via email and password
- Access token generation and expiration
- Secure password hashing
- User profile retrieval
- Authentication audit logging
- Rate limiting for failed login attempts

## Directory Structure

```
data/fixtures/sample_project/
├── README.md                  # This file
├── trace_links.json           # Ground-truth traceability links (33 links)
├── change_scenarios.json      # Hypothetical change-impact scenarios (3 scenarios)
├── requirements/              # 10 requirement specification files
│   ├── REQ-001.md             # User authentication via email/password
│   ├── REQ-002.md             # Reject invalid credentials
│   ├── REQ-003.md             # HTTP 401 for failed authentication
│   ├── REQ-004.md             # Generate authentication token
│   ├── REQ-005.md             # Token expiration
│   ├── REQ-006.md             # Retrieve user profile
│   ├── REQ-007.md             # Error for unknown users
│   ├── REQ-008.md             # Secure password storage
│   ├── REQ-009.md             # Record authentication attempts
│   └── REQ-010.md             # Rate limiting failed attempts
├── src/                       # 5 Python source files (+3 __init__.py)
│   ├── auth/
│   │   ├── __init__.py
│   │   ├── service.py         # AuthenticationService, AuthenticationResult
│   │   ├── token.py           # generate_token, decode_token, is_token_expired
│   │   └── password.py        # hash_password, verify_password
│   ├── users/
│   │   ├── __init__.py
│   │   └── service.py         # UserService, UserProfile
│   └── security/
│       ├── __init__.py
│       └── rate_limiter.py    # RateLimiter
└── tests/                     # 4 Python test files
    ├── test_authentication.py # 6 tests for login/auth flows
    ├── test_tokens.py         # 6 tests for token logic
    ├── test_users.py          # 6 tests for user profiles
    └── test_rate_limiter.py   # 7 tests for rate limiting
```

## Artifact Counts

| Category         | Count |
|-----------------|-------|
| Requirements     | 10    |
| Source files     | 5 (+ 3 `__init__.py`) |
| Test files       | 4     |
| Ground-truth trace links | 33 |
| Change scenarios | 3     |

## Ground-Truth Trace Links

The file `trace_links.json` contains **33 manually curated traceability links**
mapping each requirement to its implementing source-code artifacts and
corresponding test cases.

### Link Format

Each entry has the following structure:

```json
{
  "requirement_id": "REQ-001",
  "artifact_id": "src/auth/service.py#AuthenticationService.authenticate_user",
  "artifact_type": "source_code"
}
```

### Artifact ID Convention

Artifact IDs follow the deterministic chunk-ID format produced by TraceWise's
`PythonChunker`:

- **Top-level functions:** `<relative_file_path>#<function_name>`
  - Example: `src/auth/token.py#generate_token`
- **Classes:** `<relative_file_path>#<ClassName>`
  - Example: `src/security/rate_limiter.py#RateLimiter`
- **Methods:** `<relative_file_path>#<ClassName>.<method_name>`
  - Example: `src/auth/service.py#AuthenticationService.authenticate_user`
- **Test functions:** `tests/<file>#<test_function_name>`
  - Example: `tests/test_tokens.py#test_token_generation`

All paths are relative to `data/fixtures/sample_project/`.

### Artifact Types

- `"source_code"` — production implementation artifacts
- `"test_case"` — test functions exercising the requirements

## Intentionally Ambiguous Cases

The dataset is designed so that naive keyword-based retrieval will produce
**false positives**. Specific design choices:

1. **Shared vocabulary across modules:** The word "user" appears in
   `src/auth/service.py`, `src/users/service.py`, `src/security/rate_limiter.py`,
   and multiple test files. A retrieval system matching on "user" alone will
   incorrectly link unrelated artifacts.

2. **`UserService.list_user_ids()`** shares vocabulary with authentication
   requirements (contains "user", "list") but implements an administrative
   function unrelated to authentication or credential verification.

3. **`UserService.find_user_by_email()`** overlaps with REQ-001/REQ-002
   vocabulary ("email", "user", "find") but is a profile-lookup utility, not
   an authentication function.

4. **REQ-007 spans two modules:** "Error for unknown users" relates to both
   `AuthenticationService.authenticate_user` (returns 401 for unknown email)
   and `UserService.get_user_profile` (returns None for unknown user_id).
   A retrieval system must recognize that both modules are relevant.

5. **Overlapping test names:** `test_unknown_user_returns_401` (auth test) and
   `test_unknown_user_returns_none` (user test) share the prefix
   `test_unknown_user` but test different subsystems.

## Change Scenarios

The file `change_scenarios.json` contains **3 hypothetical change-impact
scenarios** for future CIA evaluation:

| Scenario   | Description |
|-----------|------------|
| CHANGE-001 | HTTP 401 → 403 status code change |
| CHANGE-002 | Token format change (colon-delimited → JSON) |
| CHANGE-003 | Password hash algorithm change (SHA-256 → SHA-512) |

Each scenario specifies:
- `changed_artifacts` — the artifacts that are directly modified
- `expected_impacted_artifacts` — artifacts that would need updating
- `expected_impacted_requirements` — requirements affected by the change

## Negative / Non-Link Information

Pairs **not present** in `trace_links.json` should be treated as negatives
(i.e., no true traceability relationship). The dataset contains enough unrelated
artifacts that a retrieval system will encounter meaningful false-positive
candidates.

## Dataset Limitations

1. **Small scale:** 10 requirements, 8 source files, 4 test files. Not suitable
   for evaluating scalability.
2. **Single domain:** Authentication only. No cross-domain traceability
   challenges.
3. **No deep call graphs:** The code has shallow call chains. Real software would
   have deeper transitive dependencies.
4. **No external dependencies:** All code uses Python standard library only.
   Real projects would have third-party imports.
5. **Deterministic by design:** No randomness in structure or naming. Real
   projects have organic, less predictable naming patterns.
6. **No multi-file classes or partial implementations:** Each class is fully
   contained in a single file.
7. **English only:** All identifiers, comments, and requirements are in English.
