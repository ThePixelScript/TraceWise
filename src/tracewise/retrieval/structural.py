"""Structure-guided identifier + dependency retrieval baseline (Milestone B3).

Extracts and scores code artifacts based on declared structural entity signatures
and an intra-code dependency graph (parent-child ownership, imports, inheritance,
and intra-corpus symbol references).
"""

from __future__ import annotations

import keyword
import re
from collections.abc import Sequence

from tracewise.preprocessing.models import ProcessedText
from tracewise.preprocessing.tokenizer import split_identifier
from tracewise.retrieval.base import BaseRetriever
from tracewise.retrieval.exceptions import NotIndexedError
from tracewise.retrieval.models import RetrievalCandidate

# Standard Java and Python reserved words / keywords to exclude from entity matching

_JAVA_KEYWORDS: frozenset[str] = frozenset(
    {
        "abstract",
        "assert",
        "boolean",
        "break",
        "byte",
        "case",
        "catch",
        "char",
        "class",
        "const",
        "continue",
        "default",
        "do",
        "double",
        "else",
        "enum",
        "extends",
        "final",
        "finally",
        "float",
        "for",
        "goto",
        "if",
        "implements",
        "import",
        "instanceof",
        "int",
        "interface",
        "long",
        "native",
        "new",
        "package",
        "private",
        "protected",
        "public",
        "return",
        "short",
        "static",
        "strictfp",
        "super",
        "switch",
        "synchronized",
        "this",
        "throw",
        "throws",
        "transient",
        "try",
        "void",
        "volatile",
        "while",
        "true",
        "false",
        "null",
    }
)

_PYTHON_KEYWORDS: frozenset[str] = frozenset(
    set(keyword.kwlist)
    | {
        "self",
        "cls",
        "none",
        "true",
        "false",
        "__init__",
        "__str__",
        "__repr__",
    }
)

_RESERVED_IDENTIFIERS: frozenset[str] = frozenset(
    _JAVA_KEYWORDS | _PYTHON_KEYWORDS | {"get", "set", "run", "is", "to"}
)


class StructuralRetriever(BaseRetriever):
    """Structure-guided identifier + dependency retrieval baseline (Milestone B3).

    Methodology and Scope:
    - Requirement tokens are matched only against declared structural entity /
      identifier terms to create seed activation.
    - Graph dependencies then propagate that seed signal across an intra-code
      dependency graph.
    - Full code-text lexical retrieval is not used; dense embeddings are not used;
      LLM/RAG is not used.
    - B3 is not a completely lexical-free structural method because initial seed
      activation relies on matching requirement tokens against declared entity
      identifiers.

    Graph Extraction Limitation:
    - Reference edges are inferred from explicit symbol-name occurrences in source text
      using deterministic word-boundary matching.
    - This is an approximation of true program dependencies and may include false
      structural edges from textual occurrences; it is not a compiler-verified call
      graph or complete dependency graph.

    Algorithm specification:
    1. Entity Signature Extraction:
       For each indexed target artifact c, extracts its declared identifier terms:
       T_struct(c) from c.metadata['name'] (and parent entity name if hierarchical).
    2. Dependency Graph Construction:
       Builds a deterministic intra-code dependency graph G = (V, E):
       - Hierarchy / Enclosure: Bidirectional edge if parent_id links chunk c.
       - Intra-corpus Reference: Directed edge (u, v) if chunk u references
         the declared entity name of chunk v (excluding language keywords).
       Undirected structural propagation neighborhood:
       N(c) = {u in V | (u, c) in E or (c, u) in E}.
       Node degree: deg(c) = max(1, |N(c)|).
    3. Requirement Query Scoring:
       For a requirement query q with terms T(q):
       - Direct Structural Match (Seed Activation):
         S_seed(q, c) = |T(q) & T_struct(c)| / |T_struct(c)| if |T_struct(c)| > 0
         else 0.0
       - Structural Dependency Propagation (Normalized 1-hop diffusion):
         S_graph(q, c) = (1 / sqrt(deg(c))) * sum_{u in N(c)}
         (S_seed(q, u) / sqrt(deg(u))) if |N(c)| > 0 else 0.0
       - Composite Structural Score:
         S(q, c) = (1 - alpha) * S_seed(q, c) + alpha * S_graph(q, c)
         where alpha = 0.5 is a fixed, a priori equal-weight design choice between
         direct identifier-based seed activation and structural neighbor diffusion.
         It was not tuned using benchmark ground truth.
    4. Deterministic Ranking:
       Candidates sorted by (-score, target_id) with 1-based consecutive ranks.
    """

    retriever_name: str = "structural"

    def __init__(self, alpha: float = 0.5) -> None:
        """Initialize StructuralRetriever with configurable diffusion parameter.

        Args:
            alpha: Weight for structural graph dependency propagation in [0.0, 1.0].
                alpha = 0.5 is a fixed, a priori equal-weight design choice between
                direct identifier-based seed activation and structural neighbor
                diffusion. It was not tuned using benchmark ground truth.

        Raises:
            ValueError: If alpha is not between 0.0 and 1.0.
        """
        if not (0.0 <= alpha <= 1.0):
            raise ValueError(
                f"StructuralRetriever alpha must be between 0.0 and 1.0, got {alpha}."
            )

        self.alpha = float(alpha)
        self._is_indexed: bool = False
        self._target_ids: list[str] = []
        self._target_terms: list[set[str]] = []
        self._adjacency: list[set[int]] = []
        self._degrees: list[int] = []
        self._num_targets: int = 0

    @property
    def is_indexed(self) -> bool:
        """Whether the retriever has an active index ready for querying."""
        return self._is_indexed

    @staticmethod
    def _extract_entity_name(doc: ProcessedText) -> str:
        """Extract declared symbol/entity name from document metadata or identifier."""
        name = doc.metadata.get("name")
        if name and isinstance(name, str) and name.strip():
            return name.strip()
        # Fall back to stem or symbol part of source_id
        sid = doc.source_id
        if "#" in sid:
            tail = sid.split("#")[-1]
            if "." in tail:
                return tail.split(".")[-1].strip()
            return tail.strip()
        return sid.strip()

    def index(self, documents: Sequence[ProcessedText]) -> None:
        """Build or replace the retriever's target index with documents.

        Calling index again replaces the previous index completely. If indexing
        fails for any reason, the prior valid state remains unchanged.

        Args:
            documents: Sequence of preprocessed text documents to index.

        Raises:
            ValueError: If documents is empty or contains duplicate source_ids.
        """
        doc_list = list(documents)
        if not doc_list:
            raise ValueError("Cannot index an empty document sequence.")

        target_ids: list[str] = []
        seen_ids: set[str] = set()
        id_to_idx: dict[str, int] = {}

        for idx, doc in enumerate(doc_list):
            sid = doc.source_id
            if sid in seen_ids:
                raise ValueError(f"Duplicate document source_id found: '{sid}'.")
            seen_ids.add(sid)
            target_ids.append(sid)
            id_to_idx[sid] = idx

        num_targets = len(doc_list)

        # 1. Extract structural entity signatures
        target_terms: list[set[str]] = []
        entity_name_to_indices: dict[str, list[int]] = {}

        for idx, doc in enumerate(doc_list):
            name = self._extract_entity_name(doc)
            terms: set[str] = set()

            if name:
                split_terms = split_identifier(name)
                terms.update(t.lower() for t in split_terms if t)

            # Include enclosing parent entity terms if parent is an indexed target chunk
            pid = doc.metadata.get("parent_id")
            if pid and pid in id_to_idx:
                parent_doc = doc_list[id_to_idx[pid]]
                parent_name = self._extract_entity_name(parent_doc)
                if parent_name:
                    parent_terms = split_identifier(parent_name)
                    terms.update(t.lower() for t in parent_terms if t)

            # Filter generic terms
            terms.difference_update({"init", "str", "repr", "self"})
            target_terms.append(terms)

            # Record non-reserved entity names for code reference extraction
            if (
                name
                and len(name) >= 3
                and name.lower() not in _RESERVED_IDENTIFIERS
                and not name.startswith("__")
            ):
                entity_name_to_indices.setdefault(name, []).append(idx)

        # 2. Build intra-code structural dependency graph
        edges: set[tuple[int, int]] = set()

        for idx, doc in enumerate(doc_list):
            # Enclosure / Hierarchy edges
            pid = doc.metadata.get("parent_id")
            if pid and pid in id_to_idx:
                p_idx = id_to_idx[pid]
                edges.add((p_idx, idx))
                edges.add((idx, p_idx))

            # Code reference edges (doc references declared entity of another chunk)
            code_text = doc.original_text
            if code_text:
                for entity_name, dest_indices in entity_name_to_indices.items():
                    # Word boundary search for the referenced entity identifier
                    if re.search(r"\b" + re.escape(entity_name) + r"\b", code_text):
                        for dest_idx in dest_indices:
                            if dest_idx != idx:
                                edges.add((idx, dest_idx))

        # Adjacency list for undirected propagation
        adjacency: list[set[int]] = [set() for _ in range(num_targets)]
        for u, v in edges:
            adjacency[u].add(v)
            adjacency[v].add(u)

        degrees: list[int] = [max(1, len(adjacency[i])) for i in range(num_targets)]

        # Atomic commit to object state
        self._target_ids = target_ids
        self._target_terms = target_terms
        self._adjacency = adjacency
        self._degrees = degrees
        self._num_targets = num_targets
        self._is_indexed = True

    def retrieve(
        self,
        query: ProcessedText,
        top_k: int | None = None,
    ) -> list[RetrievalCandidate]:
        """Retrieve candidate matches for a query using structural signals.

        Candidates are scored using direct structural seed matching and
        graph dependency propagation, sorted by (-score, target_id) with 1-based ranks.

        Args:
            query: Preprocessed query to search against indexed documents.
            top_k: Optional maximum number of candidates to return.
                If None, returns all candidates for the query.

        Returns:
            List of RetrievalCandidate objects ordered by descending score.

        Raises:
            NotIndexedError: If retrieve is called before index.
            ValueError: If top_k is less than or equal to 0.
        """
        if not self._is_indexed:
            raise NotIndexedError(
                f"Retriever '{self.retriever_name}' cannot retrieve before indexing."
            )

        if top_k is not None and top_k <= 0:
            raise ValueError(f"top_k must be strictly positive, got {top_k}.")

        num_targets = self._num_targets
        if num_targets == 0:
            return []

        query_tokens = {t.lower() for t in query.tokens}

        # Step 1: Direct structural seed matching
        seed_scores = [0.0] * num_targets
        if query_tokens:
            for i, terms in enumerate(self._target_terms):
                if terms:
                    overlap = len(query_tokens & terms)
                    seed_scores[i] = float(overlap) / float(len(terms))

        # Step 2: Structural dependency propagation (1-hop normalized diffusion)
        graph_scores = [0.0] * num_targets
        for i in range(num_targets):
            neighbors = self._adjacency[i]
            if neighbors:
                deg_i = float(self._degrees[i])
                s = sum(
                    seed_scores[u] / (float(self._degrees[u]) ** 0.5) for u in neighbors
                )
                graph_scores[i] = s / (deg_i**0.5)

        # Step 3: Composite score calculation
        alpha = self.alpha
        one_minus_alpha = 1.0 - alpha
        raw: list[tuple[str, float, float, float, int]] = []

        for i, target_id in enumerate(self._target_ids):
            s_seed = seed_scores[i]
            s_graph = graph_scores[i]
            total_score = one_minus_alpha * s_seed + alpha * s_graph
            # Bound score to [0.0, 1.0]
            bounded_score = max(0.0, min(1.0, float(total_score)))
            raw.append((target_id, bounded_score, s_seed, s_graph, self._degrees[i]))

        # Shared contract ordering: (-score, target_id)
        raw.sort(key=lambda item: (-item[1], item[0]))

        if top_k is not None:
            raw = raw[:top_k]

        return [
            RetrievalCandidate(
                query_id=query.source_id,
                target_id=target_id,
                score=score,
                rank=rank,
                retriever_name=self.retriever_name,
                metadata={
                    "seed_score": round(s_seed, 6),
                    "graph_score": round(s_graph, 6),
                    "degree": deg,
                },
            )
            for rank, (target_id, score, s_seed, s_graph, deg) in enumerate(
                raw, start=1
            )
        ]


__all__ = ["StructuralRetriever"]
