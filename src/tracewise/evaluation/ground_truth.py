"""Ground-truth traceability dataset loader and adapters."""

import json
from collections.abc import Callable
from pathlib import Path


def load_ground_truth(
    file_path: Path | str,
    artifact_type: str | None = None,
    query_key_fn: Callable[[str], str] | None = None,
) -> dict[str, set[str]]:
    """Load ground-truth traceability links from a JSON dataset into a query mapping.

    The returned structure maps each query (e.g. requirement ID) to a set of
    relevant target IDs:
        ``dict[query_id, set[target_id]]``

    Args:
        file_path: Path to the ground-truth JSON file (e.g. trace_links.json).
        artifact_type: Optional filter for artifact_type (e.g. 'source_code',
            'test_case'). If None, all links are loaded regardless of type.
        query_key_fn: Optional function to transform the requirement_id into
            the expected query key format. If None, the raw requirement_id is used.

    Returns:
        Deterministic dictionary mapping query_id to sets of exact target IDs.

    Raises:
        FileNotFoundError: If file_path does not exist.
        ValueError: If file content is not a valid list of trace link objects
            or required fields are missing.
    """
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"Ground-truth file not found: {path}")

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as err:
        msg = f"Failed to parse ground-truth JSON from {path}: {err}"
        raise ValueError(msg) from err

    if not isinstance(data, list):
        raise ValueError(
            f"Expected list of trace link records in {path}, got {type(data).__name__}."
        )

    mapping: dict[str, set[str]] = {}

    for idx, entry in enumerate(data):
        if not isinstance(entry, dict):
            raise ValueError(f"Record at index {idx} in {path} is not a dictionary.")

        req_id = entry.get("requirement_id")
        art_id = entry.get("artifact_id")

        if not req_id or not isinstance(req_id, str):
            raise ValueError(
                f"Record at index {idx} in {path} missing valid 'requirement_id'."
            )
        if not art_id or not isinstance(art_id, str):
            raise ValueError(
                f"Record at index {idx} in {path} missing valid 'artifact_id'."
            )

        entry_type = entry.get("artifact_type")
        if artifact_type is not None and entry_type != artifact_type:
            continue

        query_key = query_key_fn(req_id) if query_key_fn is not None else req_id
        target_id = art_id.strip()

        mapping.setdefault(query_key, set()).add(target_id)

    # Return deterministically sorted dictionary
    return {k: mapping[k] for k in sorted(mapping.keys())}


__all__ = ["load_ground_truth"]
