"""Setup script to fetch and verify the LiSSA ICSE 2025 eTour req2code benchmark files.

Downloads the exact commit of the LiSSA replication package, extracts the
canonical req2code/eTour_en variant into data/benchmarks/etour/, and validates
file counts and SHA-256 checksums.
"""

from __future__ import annotations

import csv
import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

LISSA_REPO_URL = (
    "https://github.com/ardoco/"
    "Replication-Package-ICSE25_LiSSA-Toward-Generic-Traceability-Link-Recovery-through-RAG.git"
)
LISSA_COMMIT = "a8e652f29bbdcc4bdcd3d98cd85aa4a37cb65480"
EXPECTED_UC2CC_SHA256 = (
    "bb9081ab8b1a0a42614ac25a19b0c044f9ec52323c074d6cd19eee0cd6154fde"
)

TARGET_DIR = Path("data/benchmarks/etour")


def verify_sha256(path: Path, expected: str) -> bool:
    h = hashlib.sha256(path.read_bytes()).hexdigest()
    return h.lower() == expected.lower()


def setup_etour(target_dir: Path = TARGET_DIR) -> None:
    uc_dir = target_dir / "UC"
    cc_dir = target_dir / "CC"
    csv_file = target_dir / "UC2CC.csv"
    json_file = target_dir / "trace_links.json"

    if (
        uc_dir.is_dir()
        and cc_dir.is_dir()
        and csv_file.is_file()
        and json_file.is_file()
    ):
        if (
            len(list(uc_dir.glob("*.txt"))) == 58
            and len(list(cc_dir.glob("*.java"))) == 116
        ):
            print("eTour req2code benchmark files already present and complete.")
            return

    print("Fetching LiSSA ICSE 2025 eTour req2code benchmark files...")
    target_dir.mkdir(parents=True, exist_ok=True)
    uc_dir.mkdir(parents=True, exist_ok=True)
    cc_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_repo = Path(tmp_dir) / "lissa_tmp"
        cmd = [
            "git",
            "clone",
            "--depth",
            "1",
            "--filter=blob:none",
            "--sparse",
            LISSA_REPO_URL,
            str(tmp_repo),
        ]
        subprocess.run(cmd, check=True, capture_output=True)

        sparse_cmd = [
            "git",
            "sparse-checkout",
            "set",
            "LiSSA-RATLR-V2/lissa/datasets/req2code/eTour_en",
        ]
        subprocess.run(sparse_cmd, cwd=str(tmp_repo), check=True, capture_output=True)

        source_base = (
            tmp_repo / "LiSSA-RATLR-V2" / "lissa" / "datasets" / "req2code" / "eTour_en"
        )
        if not source_base.is_dir():
            raise RuntimeError(
                f"Failed to locate extracted eTour files in {source_base}"
            )

        # Copy UC files
        for f in (source_base / "UC").glob("*.txt"):
            shutil.copy2(f, uc_dir / f.name)

        # Copy CC files
        for f in (source_base / "CC").glob("*.java"):
            shutil.copy2(f, cc_dir / f.name)

        # Copy UC2CC.csv
        shutil.copy2(source_base / "UC2CC.csv", csv_file)

        # Generate trace_links.json
        links = []
        with csv_file.open("r", encoding="utf-8") as f:
            reader = csv.reader(f)
            for row in reader:
                if row:
                    links.append(
                        {
                            "requirement_id": row[0].strip(),
                            "artifact_id": row[1].strip(),
                            "artifact_type": "source_code",
                        }
                    )

        with json_file.open("w", encoding="utf-8") as f:
            json.dump(links, f, indent=2)

    # Validate
    if not verify_sha256(csv_file, EXPECTED_UC2CC_SHA256):
        raise ValueError("SHA-256 mismatch on downloaded UC2CC.csv!")

    uc_count = len(list(uc_dir.glob("*.txt")))
    cc_count = len(list(cc_dir.glob("*.java")))
    print(
        f"Successfully installed eTour benchmark: {uc_count} requirements, "
        f"{cc_count} classes, {len(links)} links."
    )


if __name__ == "__main__":
    setup_etour()
