"""Tests for friday.memory.semantic — semantic memory + embeddings."""

import tempfile
from unittest.mock import MagicMock, AsyncMock
import pytest

from friday.memory.semantic import SemanticMemory, Fact, _cosine_similarity


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d


class TestCosineSimilarity:
    """Test the cosine similarity helper."""

    def test_identical_vectors(self):
        a = [1.0, 2.0, 3.0]
        assert abs(_cosine_similarity(a, a) - 1.0) < 0.001

    def test_orthogonal_vectors(self):
        a = [1.0, 0.0]
        b = [0.0, 1.0]
        assert abs(_cosine_similarity(a, b)) < 0.001

    def test_opposite_vectors(self):
        a = [1.0, 1.0]
        b = [-1.0, -1.0]
        assert abs(_cosine_similarity(a, b) - (-1.0)) < 0.001

    def test_empty_vectors(self):
        assert _cosine_similarity([], []) == 0.0
        assert _cosine_similarity([1.0], []) == 0.0

    def test_mismatched_length(self):
        assert _cosine_similarity([1.0, 2.0], [1.0]) == 0.0


class TestSemanticMemoryLexical:
    """Test semantic memory with lexical fallback (no embeddings)."""

    def test_add_and_search_lexical(self, tmp_dir):
        """Without embeddings, falls back to lexical search."""
        sem = SemanticMemory(f"{tmp_dir}/sem.json")
        assert sem.has_embeddings is False

        sem.add_fact(Fact(content="Python is a programming language", category="general"))
        sem.add_fact(Fact(content="Paris is the capital of France", category="general"))

        results = sem.search("programming language")
        assert len(results) >= 1
        assert "Python" in results[0].content

    def test_categories(self, tmp_dir):
        """Facts can be filtered by category."""
        sem = SemanticMemory(f"{tmp_dir}/sem.json")
        sem.add_fact(Fact(content="User prefers dark mode", category="preference"))
        sem.add_fact(Fact(content="Gmail compose is top-left", category="app"))

        prefs = sem.get_user_preferences()
        assert len(prefs) == 1
        assert "dark mode" in prefs[0].content

    def test_total_facts(self, tmp_dir):
        sem = SemanticMemory(f"{tmp_dir}/sem.json")
        sem.add_fact(Fact(content="fact 1"))
        sem.add_fact(Fact(content="fact 2"))
        assert sem.total_facts == 2

    def test_add_multiple(self, tmp_dir):
        sem = SemanticMemory(f"{tmp_dir}/sem.json")
        ids = sem.add_facts([
            Fact(content="a"),
            Fact(content="b"),
            Fact(content="c"),
        ])
        assert len(ids) == 3
        assert sem.total_facts == 3

    def test_persistence(self, tmp_dir):
        path = f"{tmp_dir}/sem.json"
        sem1 = SemanticMemory(path)
        sem1.add_fact(Fact(content="persistent fact", category="general"))

        sem2 = SemanticMemory(path)
        assert sem2.total_facts == 1


class TestSemanticMemoryEmbeddings:
    """Test semantic memory with mocked embedding provider."""

    def _make_provider(self, embedding_value=None):
        """Create a mock embedding provider."""
        provider = MagicMock()
        provider.available = True
        # embed returns a simple vector based on text length
        async def fake_embed(text):
            if embedding_value is not None:
                return embedding_value
            # Deterministic fake embedding
            return [float(len(text) % 10), 1.0, 0.5]
        provider.embed = fake_embed
        return provider

    def test_has_embeddings_with_provider(self, tmp_dir):
        provider = self._make_provider()
        sem = SemanticMemory(f"{tmp_dir}/sem.json", embedding_provider=provider)
        assert sem.has_embeddings is True

    def test_add_fact_computes_embedding(self, tmp_dir):
        provider = self._make_provider(embedding_value=[1.0, 0.0, 0.0])
        sem = SemanticMemory(f"{tmp_dir}/sem.json", embedding_provider=provider)

        sem.add_fact(Fact(content="test fact"))

        # Retrieve and check embedding was stored
        facts = sem.get_facts_by_category("general")
        assert len(facts) == 1
        assert facts[0].embedding == [1.0, 0.0, 0.0]

    def test_semantic_search_ranks_by_similarity(self, tmp_dir):
        """Semantic search ranks by cosine similarity."""
        provider = MagicMock()
        provider.available = True

        # Map specific texts to specific embeddings
        embeddings = {
            "cats are animals": [1.0, 0.0, 0.0],
            "dogs are animals": [0.9, 0.1, 0.0],
            "python is code": [0.0, 0.0, 1.0],
        }
        async def fake_embed(text):
            return embeddings.get(text, [0.5, 0.5, 0.5])
        provider.embed = fake_embed

        sem = SemanticMemory(f"{tmp_dir}/sem.json", embedding_provider=provider)
        sem.add_fact(Fact(content="cats are animals"))
        sem.add_fact(Fact(content="dogs are animals"))
        sem.add_fact(Fact(content="python is code"))

        # Query similar to animal facts
        # Mock the query embedding to be close to animals
        embeddings["animal query"] = [0.95, 0.05, 0.0]
        results = sem.search("animal query", top_k=2)

        # Top results should be the animal facts, not python
        assert len(results) == 2
        contents = [r.content for r in results]
        assert "python is code" not in contents


class TestFact:
    """Test Fact dataclass."""

    def test_fact_defaults(self):
        fact = Fact(content="test")
        assert fact.category == "general"
        assert fact.confidence == 1.0
        assert fact.timestamp > 0

    def test_to_memory_entry(self):
        fact = Fact(content="test", category="preference", confidence=0.9)
        entry = fact.to_memory_entry()
        assert entry.content == "test"
        assert "preference" in entry.tags
        assert entry.metadata["confidence"] == 0.9


class TestTemporalEdges:
    """Test temporal validity (Memory OS pattern)."""

    def test_new_fact_is_valid(self):
        fact = Fact(content="test")
        assert fact.is_currently_valid is True
        assert fact.valid_at > 0
        assert fact.invalid_at is None

    def test_invalidate_marks_invalid(self, tmp_dir):
        sem = SemanticMemory(f"{tmp_dir}/sem.json")
        sem.add_fact(Fact(content="The sky is green", category="general"))

        found = sem.invalidate("sky is green")
        assert found is True

        # Default search excludes invalid facts
        results = sem.search("sky")
        assert len(results) == 0

        # But history is preserved
        all_results = sem.search("sky", include_invalid=True)
        assert len(all_results) == 1
        assert all_results[0].is_currently_valid is False

    def test_update_fact_preserves_history(self, tmp_dir):
        sem = SemanticMemory(f"{tmp_dir}/sem.json")
        sem.add_fact(Fact(content="User lives in Mumbai", category="user"))

        updated = sem.update_fact(
            "User lives in Mumbai",
            "User lives in Bangalore",
            category="user",
        )
        assert updated is True

        # Current search returns only the new fact
        results = sem.search("User lives", include_invalid=False)
        valid_contents = [r.content for r in results if r.is_currently_valid]
        assert any("Bangalore" in c for c in valid_contents)
        assert not any("Mumbai" in c and r.is_currently_valid
                       for c, r in zip([x.content for x in results], results)
                       if "Mumbai" in c)

        # History includes the old fact
        all_results = sem.search("User lives", include_invalid=True)
        contents = [r.content for r in all_results]
        assert any("Mumbai" in c for c in contents)
        assert any("Bangalore" in c for c in contents)

    def test_invalidate_nonexistent(self, tmp_dir):
        sem = SemanticMemory(f"{tmp_dir}/sem.json")
        found = sem.invalidate("does not exist")
        assert found is False
