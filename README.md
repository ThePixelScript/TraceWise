# TraceWise

An intelligent platform for automated requirements traceability and change impact analysis across software artifacts.

## Status

Active development:
- **Milestone 0 (Project Foundation):** Complete
- **Milestone 1A (Artifact Ingestion):** Complete
- **Milestone 1B (Python Artifact Chunk Extraction):** Complete
- **Synthetic Evaluation Fixtures (PR #1):** Complete
- **Milestone 1C (Text Preprocessing):** Next in progress

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
  - `preprocessing/`: Text normalization, code tokenization, and vocabulary extraction (Milestone 1C)
  - `retrieval/`: Candidate retrieval strategies (TF-IDF, BM25, semantic embeddings)
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