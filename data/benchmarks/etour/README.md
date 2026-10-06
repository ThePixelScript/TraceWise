# eTour Requirements-to-Code Traceability Benchmark

## 1. Benchmark Identification & Provenance

* **Dataset Variant:** eTour req2code benchmark variant sourced from the LiSSA ICSE 2025 replication package.
* **Source Repository:** [`ardoco/Replication-Package-ICSE25_LiSSA-Toward-Generic-Traceability-Link-Recovery-through-RAG`](https://github.com/ardoco/Replication-Package-ICSE25_LiSSA-Toward-Generic-Traceability-Link-Recovery-through-RAG)
* **Repository Commit:** `a8e652f29bbdcc4bdcd3d98cd85aa4a37cb65480` (tagged `v1.0.0`, Zenodo DOI: [`10.5281/zenodo.14714706`](https://doi.org/10.5281/zenodo.14714706))
* **Exact Subdirectory:** `LiSSA-RATLR-V2/lissa/datasets/req2code/eTour_en/`
* **Canonical Checksum:** `UC2CC.csv` SHA-256 = `bb9081ab8b1a0a42614ac25a19b0c044f9ec52323c074d6cd19eee0cd6154fde`
* **Original Application:** Electronic Tourist guide (eTour) system developed by students at the University of Salerno (Italy).
* **Traceability Challenge:** Originally presented as part of the TEFSE 2011 Traceability Challenge (The 6th International Workshop on Traceability in Emerging Forms of Software Engineering) and curated by CoEST.
* **Translation:** Translated to English for international traceability research (use cases translated to English, source code identifiers in Italian/English).

> [!IMPORTANT]
> **Variant Disclaimer:** Multiple processed versions of eTour exist across literature repositories (original Italian requirements vs English translations, character encodings, differing link formatting). TraceWise explicitly uses the English-translated `eTour_en` variant bundled in the LiSSA ICSE 2025 replication package and does not claim equivalence with every published eTour benchmark dataset.

---

## 2. Licensing & Redistribution Audit

* **LiSSA Tooling Framework:** MIT License (`Copyright (c) 2025 ArDoCo`).
* **Third-Party eTour Assets:** Developed at the University of Salerno for the TEFSE 2011 academic benchmark and curated by CoEST. The raw files bundled in the replication package lack an explicit, standalone open-source license header.
* **TraceWise Redistribution Policy:** Because third-party redistribution terms cannot be established with certainty from upstream headers, TraceWise excludes raw files (`UC/`, `CC/`, `UC2CC.csv`, `trace_links.json`) from Git via `.gitignore`.
* **Automated Setup:** Users can obtain the exact replication dataset locally by running:
  ```bash
  python scripts/setup_etour.py
  ```

---

## 3. Scale, Granularity & Denominator

* **Dataset Scale:** An external real-world traceability benchmark of moderate size relative to the current synthetic fixture (intended for external validation and cross-project comparison, not proof of large-scale scalability).
* **Requirement Granularity:** Use-Case level (`UC1.txt` ... `UC58.txt`). Total: **58** requirements.
* **Code Granularity:** Class / Compilation Unit level (`CC/*.java`). Total: **116** Java classes.
* **Ground-Truth Links:** **308** links mapping use-case IDs to Java class names (`UC2CC.csv`).
* **Evaluation Query Denominator:**
  * **Total Requirements:** 58
  * **Evaluable Requirements ($|Q_{\text{eval}}| = 57$):** Requirements that have $\ge 1$ gold link.
  * **Zero-Link Requirements ($|Q_{\text{zero}}| = 1$):** `UC37` has zero links in the gold standard.
  * Zero-link queries are excluded from ranking metrics according to the TraceWise evaluation protocol (ranking metrics evaluated with denominator $N = 57$).

---

## 4. Empirical Baseline Results

Evaluated using `MultiProjectBenchmarkRunner` with frozen retriever configurations on Requirements $\to$ Source Code ($N = 57$ evaluable queries, 116 candidate classes, 308 gold links):

| Model | MAP | MRR | P@1 | P@3 | P@5 | R@1 | R@3 | R@5 | Index Time | Query Time |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **B0 (TF-IDF)** | 0.3878 | 0.6636 | 0.5263 | 0.4386 | 0.3509 | 0.1211 | 0.2686 | 0.3686 | 0.014s | 0.021s |
| **B1 (BM25)** | 0.2987 | 0.5994 | 0.4035 | 0.3567 | 0.2772 | 0.0712 | 0.2332 | 0.2969 | 0.012s | 0.019s |
| **B2 (Semantic)** | 0.4329 | 0.6918 | 0.5439 | 0.4620 | 0.4035 | 0.1129 | 0.2685 | 0.3952 | 2.985s | 0.715s |
