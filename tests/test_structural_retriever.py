"""Unit tests for StructuralRetriever baseline (Milestone B3)."""

from pathlib import Path

import pytest

from tracewise.preprocessing.models import ProcessedText
from tracewise.retrieval.exceptions import NotIndexedError
from tracewise.retrieval.models import RetrievalCandidate
from tracewise.retrieval.structural import StructuralRetriever


def make_doc(
    source_id: str,
    original_text: str,
    name: str | None = None,
    parent_id: str | None = None,
    tokens: list[str] | None = None,
) -> ProcessedText:
    """Helper to construct ProcessedText with structural metadata."""
    metadata = {}
    if name is not None:
        metadata["name"] = name
    if parent_id is not None:
        metadata["parent_id"] = parent_id

    toks = tokens or [t.lower() for t in original_text.split()]
    return ProcessedText(
        source_id=source_id,
        original_text=original_text,
        normalized_text=original_text.lower(),
        tokens=toks,
        metadata=metadata,
    )


class TestStructuralRetrieverInitialization:
    """Tests parameter initialization and validation."""

    def test_default_initialization(self):
        retriever = StructuralRetriever()
        assert retriever.alpha == 0.5
        assert retriever.retriever_name == "structural"
        assert retriever.is_indexed is False

    def test_custom_alpha(self):
        retriever = StructuralRetriever(alpha=0.3)
        assert retriever.alpha == 0.3

        retriever_zero = StructuralRetriever(alpha=0.0)
        assert retriever_zero.alpha == 0.0

        retriever_one = StructuralRetriever(alpha=1.0)
        assert retriever_one.alpha == 1.0

    def test_invalid_alpha_raises_value_error(self):
        with pytest.raises(ValueError, match="alpha must be between 0.0 and 1.0"):
            StructuralRetriever(alpha=-0.1)

        with pytest.raises(ValueError, match="alpha must be between 0.0 and 1.0"):
            StructuralRetriever(alpha=1.1)


class TestStructuralRetrieverIndexing:
    """Tests corpus indexing, signature extraction, and graph construction."""

    def test_index_empty_sequence_raises(self):
        retriever = StructuralRetriever()
        with pytest.raises(ValueError, match="Cannot index an empty document"):
            retriever.index([])

    def test_index_duplicate_source_id_raises(self):
        retriever = StructuralRetriever()
        docs = [
            make_doc("target_1", "code", name="target_1"),
            make_doc("target_1", "duplicate code", name="target_1"),
        ]
        with pytest.raises(ValueError, match="Duplicate document source_id"):
            retriever.index(docs)

    def test_reindexing_replaces_index(self):
        retriever = StructuralRetriever()
        docs_1 = [
            make_doc("A", "code A", name="A"),
            make_doc("B", "code B", name="B"),
        ]
        retriever.index(docs_1)
        assert retriever.is_indexed is True
        assert len(retriever._target_ids) == 2

        docs_2 = [
            make_doc("X", "code X", name="X"),
            make_doc("Y", "code Y", name="Y"),
            make_doc("Z", "code Z", name="Z"),
        ]
        retriever.index(docs_2)
        assert len(retriever._target_ids) == 3
        assert retriever._target_ids == ["X", "Y", "Z"]

    def test_structural_feature_and_edge_extraction(self):
        retriever = StructuralRetriever()
        # Class AuthService and its method authenticate
        # plus a helper function HashPassword referenced in AuthService
        doc_service = make_doc(
            "src/auth/service.py#AuthService",
            "class AuthService:\n"
            "    def authenticate(self):\n"
            "        return HashPassword()",
            name="AuthService",
        )

        doc_method = make_doc(
            "src/auth/service.py#AuthService.authenticate",
            "def authenticate(self):\n    return HashPassword()",
            name="authenticate",
            parent_id="src/auth/service.py#AuthService",
        )
        doc_helper = make_doc(
            "src/auth/hash.py#HashPassword",
            "def HashPassword(): pass",
            name="HashPassword",
        )

        retriever.index([doc_service, doc_method, doc_helper])
        assert retriever.is_indexed is True

        # Check target terms
        # doc_method should have terms from authenticate AND parent AuthService
        method_idx = retriever._target_ids.index(
            "src/auth/service.py#AuthService.authenticate"
        )
        method_terms = retriever._target_terms[method_idx]
        assert "authenticate" in method_terms
        assert "auth" in method_terms
        assert "service" in method_terms

        # Check graph adjacency
        service_idx = retriever._target_ids.index("src/auth/service.py#AuthService")
        helper_idx = retriever._target_ids.index("src/auth/hash.py#HashPassword")

        # service and method should be connected (parent-child)
        assert method_idx in retriever._adjacency[service_idx]
        assert service_idx in retriever._adjacency[method_idx]

        # service references HashPassword -> edge between service and helper
        assert helper_idx in retriever._adjacency[service_idx]
        assert service_idx in retriever._adjacency[helper_idx]


class TestStructuralRetrieverRetrieval:
    """Tests query retrieval, ranking, tie-breaking, and scoring logic."""

    def test_retrieve_before_index_raises(self):
        retriever = StructuralRetriever()
        query = make_doc("req1", "user login", tokens=["user", "login"])
        with pytest.raises(NotIndexedError, match="cannot retrieve before indexing"):
            retriever.retrieve(query)

    def test_invalid_top_k_raises(self):
        retriever = StructuralRetriever()
        retriever.index([make_doc("A", "code", name="A")])
        query = make_doc("req1", "login", tokens=["login"])

        with pytest.raises(ValueError, match="top_k must be strictly positive"):
            retriever.retrieve(query, top_k=0)

        with pytest.raises(ValueError, match="top_k must be strictly positive"):
            retriever.retrieve(query, top_k=-2)

    def test_empty_query_returns_zero_scores_with_deterministic_sort(self):
        retriever = StructuralRetriever()
        retriever.index(
            [
                make_doc("Z_target", "code", name="Z_target"),
                make_doc("A_target", "code", name="A_target"),
                make_doc("M_target", "code", name="M_target"),
            ]
        )
        query = make_doc("req_empty", "", tokens=[])
        candidates = retriever.retrieve(query)

        assert len(candidates) == 3
        # Tied at 0.0 score, so order must be A_target, M_target, Z_target
        assert [c.target_id for c in candidates] == [
            "A_target",
            "M_target",
            "Z_target",
        ]
        assert all(c.score == 0.0 for c in candidates)
        assert [c.rank for c in candidates] == [1, 2, 3]

    def test_direct_seed_and_graph_propagation(self):
        # Target A: AddPatientAction
        # Target B: PatientDAO (referenced in AddPatientAction)
        # Target C: BillingManager (unrelated)
        retriever = StructuralRetriever(alpha=0.5)
        doc_a = make_doc(
            "AddPatientAction",
            "public class AddPatientAction { PatientDAO dao = new PatientDAO(); }",
            name="AddPatientAction",
        )
        doc_b = make_doc(
            "PatientDAO",
            "public class PatientDAO { void save() {} }",
            name="PatientDAO",
        )
        doc_c = make_doc(
            "BillingManager",
            "public class BillingManager { void bill() {} }",
            name="BillingManager",
        )

        retriever.index([doc_a, doc_b, doc_c])

        # Query matches terms of AddPatientAction ("add", "patient", "action")
        # Query does NOT match "dao"
        query = make_doc(
            "UC1",
            "add patient into system",
            tokens=["add", "patient", "into", "system"],
        )
        candidates = retriever.retrieve(query)

        cand_dict = {c.target_id: c for c in candidates}
        cand_a = cand_dict["AddPatientAction"]
        cand_b = cand_dict["PatientDAO"]
        cand_c = cand_dict["BillingManager"]

        # A has direct match on "add" and "patient"
        assert cand_a.metadata["seed_score"] > 0.0
        assert cand_a.score > 0.0

        # B also has direct match on "patient" (seed_score > 0)
        # AND receives graph propagation from A (graph_score > 0)
        assert cand_b.metadata["graph_score"] > 0.0

        # C has no direct match and no graph link to A or B
        assert cand_c.score == 0.0
        assert cand_c.metadata["seed_score"] == 0.0
        assert cand_c.metadata["graph_score"] == 0.0

        # Rank of A and B must be ahead of C
        assert cand_a.rank < cand_c.rank
        assert cand_b.rank < cand_c.rank

    def test_top_k_limiting(self):
        retriever = StructuralRetriever()
        docs = [
            make_doc(f"target_{i:02d}", "code", name=f"target_{i:02d}")
            for i in range(10)
        ]
        retriever.index(docs)

        query = make_doc("req1", "target_05", tokens=["target", "05"])
        res = retriever.retrieve(query, top_k=3)
        assert len(res) == 3
        assert [c.rank for c in res] == [1, 2, 3]

    def test_candidate_contract_compliance(self):
        retriever = StructuralRetriever()
        docs = [make_doc("target_1", "code", name="target_1")]
        retriever.index(docs)

        query = make_doc("req_1", "query text", tokens=["target", "1"])
        candidates = retriever.retrieve(query)
        assert len(candidates) == 1
        cand = candidates[0]

        assert isinstance(cand, RetrievalCandidate)
        assert cand.query_id == "req_1"
        assert cand.target_id == "target_1"
        assert cand.retriever_name == "structural"
        assert 0.0 <= cand.score <= 1.0
        assert cand.rank == 1
        assert "seed_score" in cand.metadata
        assert "graph_score" in cand.metadata
        assert "degree" in cand.metadata


class TestDeterministicTieBreaking:
    """Verifies that ties are deterministically resolved by target_id ascending."""

    def test_exact_tie_broken_by_target_id_alphabetical(self):
        retriever = StructuralRetriever()
        docs = [
            make_doc("zeta", "code", name="zeta"),
            make_doc("beta", "code", name="beta"),
            make_doc("alpha", "code", name="alpha"),
        ]
        retriever.index(docs)

        # Query that matches none of them
        query = make_doc("q", "nomatch", tokens=["unrelated"])
        candidates = retriever.retrieve(query)

        assert [c.target_id for c in candidates] == ["alpha", "beta", "zeta"]
        assert [c.rank for c in candidates] == [1, 2, 3]


class TestNoGroundTruthLeakage:
    """Verifies that StructuralRetriever does not access ground truth."""

    def test_no_ground_truth_attributes_or_imports(self):
        retriever = StructuralRetriever()
        # Verify no trace_links or ground_truth references in instance attributes
        for attr in dir(retriever):
            assert "ground_truth" not in attr.lower()
            assert "trace_link" not in attr.lower()
            assert "gold" not in attr.lower()

        # Check source file content does not load ground truth
        src_path = (
            Path(__file__).resolve().parent.parent
            / "src"
            / "tracewise"
            / "retrieval"
            / "structural.py"
        )
        source_code = src_path.read_text(encoding="utf-8")

        assert "trace_links.json" not in source_code
        assert "UC2JAVA.csv" not in source_code
        assert "UC2CC.csv" not in source_code
        assert "load_ground_truth" not in source_code
