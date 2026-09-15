"""Abstract base retriever for TraceWise."""

from abc import ABC, abstractmethod
from collections.abc import Sequence

from tracewise.retrieval.models import ProcessedText, RetrievalCandidate


class BaseRetriever(ABC):
    """Abstract base class for all retrieval strategies."""

    @property
    @abstractmethod
    def is_indexed(self) -> bool:
        """Whether the retriever has an active index ready for querying."""
        ...

    @abstractmethod
    def index(self, documents: Sequence[ProcessedText]) -> None:
        """Build or replace the retriever's target index with documents.

        Calling index again must replace the previous index completely.

        Args:
            documents: Sequence of preprocessed text documents to index.
        """
        ...

    @abstractmethod
    def retrieve(
        self,
        query: ProcessedText,
        top_k: int | None = None,
    ) -> list[RetrievalCandidate]:
        """Retrieve candidate matches for a query from the indexed corpus.

        Candidates must be sorted in descending order of relevance score,
        with ties broken deterministically by target_id ascending:
            key=lambda candidate: (-candidate.score, candidate.target_id)
        Ranks must be 1-based and consecutive (1, 2, 3, ...).

        Args:
            query: Preprocessed query to search against the indexed documents.
            top_k: Optional maximum number of candidates to return.
                If None, returns all candidates for the query.

        Returns:
            List of RetrievalCandidate objects ordered by descending score.

        Raises:
            NotIndexedError: If retrieve is called before index.
            ValueError: If top_k is less than or equal to 0.
        """
        ...
