"""
Unit tests for web chain deduplication (persist-side and retrieval-side).
"""

import sys
from pathlib import Path

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import numpy as np
import pytest


# ── Persist-side clustering tests ──────────────────────────────────────────

from web_chain_persistence import _cluster_vectors


def _make_vector(vec_id: str, embedding: list, mechanism: str = "") -> dict:
    """Helper to build a vector dict matching the persist_web_chains format."""
    return {
        "id": vec_id,
        "values": embedding,
        "metadata": {
            "what_happened": f"cause_{vec_id} -> effect_{vec_id}",
            "interpretation": mechanism,
            "category": "web_chain",
        },
    }


class TestClusterVectors:
    def test_single_vector_unchanged(self):
        """Single vector passes through with validation_count=1."""
        v = _make_vector("a", [1.0, 0.0, 0.0], "some mechanism")
        result = _cluster_vectors([v], threshold=0.85)
        assert len(result) == 1
        assert result[0]["metadata"]["validation_count"] == 1

    def test_empty_list(self):
        result = _cluster_vectors([], threshold=0.85)
        assert result == []

    def test_identical_vectors_clustered(self):
        """Two identical embeddings collapse into one cluster."""
        v1 = _make_vector("a", [1.0, 0.0, 0.0], "short")
        v2 = _make_vector("b", [1.0, 0.0, 0.0], "longer mechanism text")
        result = _cluster_vectors([v1, v2], threshold=0.85)
        assert len(result) == 1
        assert result[0]["metadata"]["validation_count"] == 2
        # Picks the one with the longer interpretation
        assert result[0]["metadata"]["interpretation"] == "longer mechanism text"

    def test_orthogonal_vectors_separate(self):
        """Orthogonal vectors stay in separate clusters."""
        v1 = _make_vector("a", [1.0, 0.0, 0.0], "mech a")
        v2 = _make_vector("b", [0.0, 1.0, 0.0], "mech b")
        result = _cluster_vectors([v1, v2], threshold=0.85)
        assert len(result) == 2
        for r in result:
            assert r["metadata"]["validation_count"] == 1

    def test_high_similarity_clustered(self):
        """Vectors with cosine > 0.85 end up in the same cluster."""
        # cos(a, b) ≈ 0.995 for [1,0,0] and [0.99,0.1,0]
        v1 = _make_vector("a", [1.0, 0.0, 0.0], "short")
        v2 = _make_vector("b", [0.99, 0.1, 0.0], "this is much longer mechanism")
        result = _cluster_vectors([v1, v2], threshold=0.85)
        assert len(result) == 1
        assert result[0]["metadata"]["validation_count"] == 2

    def test_cluster_of_five(self):
        """Five near-duplicate embeddings collapse into one cluster with count=5."""
        base = np.array([1.0, 0.0, 0.0])
        vectors = []
        for i in range(5):
            # Add tiny noise — cosine stays very high
            noisy = base + np.random.default_rng(i).normal(0, 0.01, 3)
            mechanism = "m" * (i + 1)  # index 4 has longest
            vectors.append(_make_vector(f"v{i}", noisy.tolist(), mechanism))

        result = _cluster_vectors(vectors, threshold=0.85)
        assert len(result) == 1
        assert result[0]["metadata"]["validation_count"] == 5

    def test_two_distinct_clusters(self):
        """Mix of two groups: 3 similar to [1,0,0] and 2 similar to [0,1,0]."""
        group_a = [
            _make_vector("a1", [1.0, 0.01, 0.0], "m"),
            _make_vector("a2", [0.99, 0.02, 0.0], "mm"),
            _make_vector("a3", [0.98, 0.03, 0.0], "mmm"),
        ]
        group_b = [
            _make_vector("b1", [0.0, 1.0, 0.01], "x"),
            _make_vector("b2", [0.01, 0.99, 0.02], "xx"),
        ]
        result = _cluster_vectors(group_a + group_b, threshold=0.85)
        assert len(result) == 2
        counts = sorted([r["metadata"]["validation_count"] for r in result])
        assert counts == [2, 3]

    def test_original_metadata_not_mutated(self):
        """Clustering should not mutate the original vector dicts."""
        v1 = _make_vector("a", [1.0, 0.0, 0.0], "mech a")
        v2 = _make_vector("b", [1.0, 0.0, 0.0], "longer mech b")
        original_meta_a = dict(v1["metadata"])
        _cluster_vectors([v1, v2], threshold=0.85)
        # Original should be untouched
        assert "validation_count" not in v1["metadata"] or v1["metadata"] == original_meta_a


# ── Retrieval-side dedup tests ─────────────────────────────────────────────

from vector_search import _dedup_web_chain_results


def _make_chunk(chunk_id: str, score: float, what_happened: str, validation_count: int = 1) -> dict:
    """Helper to build a Pinecone result chunk."""
    return {
        "id": chunk_id,
        "score": score,
        "metadata": {
            "what_happened": what_happened,
            "category": "web_chain",
            "validation_count": validation_count,
        },
    }


class TestDedupWebChainResults:
    def test_single_chunk_unchanged(self):
        chunk = _make_chunk("c1", 0.8, "AI disruption -> SaaS selloff")
        result = _dedup_web_chain_results([chunk], threshold=0.60)
        assert len(result) == 1

    def test_empty_list(self):
        result = _dedup_web_chain_results([], threshold=0.60)
        assert result == []

    def test_identical_text_clustered(self):
        """Same what_happened text → single cluster, highest score kept."""
        c1 = _make_chunk("c1", 0.7, "AI disruption -> SaaS selloff", validation_count=1)
        c2 = _make_chunk("c2", 0.9, "AI disruption -> SaaS selloff", validation_count=2)
        result = _dedup_web_chain_results([c1, c2], threshold=0.60)
        assert len(result) == 1
        assert result[0]["id"] == "c2"  # higher score
        assert result[0]["metadata"]["validation_count"] == 3  # 1 + 2
        assert result[0]["metadata"]["similar_count"] == 2

    def test_overlapping_text_clustered(self):
        """High word overlap → same cluster."""
        # Jaccard: {AI,disruption,SaaS,software,selloff,stocks} / {AI,disruption,SaaS,software,selloff,stocks,sector} = 6/7 ≈ 0.86
        c1 = _make_chunk("c1", 0.8, "AI disruption SaaS software stocks selloff")
        c2 = _make_chunk("c2", 0.7, "AI disruption SaaS software selloff stocks sector")
        result = _dedup_web_chain_results([c1, c2], threshold=0.60)
        assert len(result) == 1
        assert result[0]["id"] == "c1"  # higher score

    def test_different_topics_separate(self):
        """Unrelated what_happened → separate clusters."""
        c1 = _make_chunk("c1", 0.8, "AI disruption -> SaaS selloff")
        c2 = _make_chunk("c2", 0.7, "Fed rate cut -> bond rally treasury yields")
        result = _dedup_web_chain_results([c1, c2], threshold=0.60)
        assert len(result) == 2

    def test_five_near_duplicates_to_one(self):
        """5 near-duplicate AI disruption chains → 1 representative."""
        # All share core tokens {AI, disruption, SaaS, software, selloff} with minor additions
        chunks = [
            _make_chunk("c1", 0.85, "AI disruption SaaS software stocks selloff"),
            _make_chunk("c2", 0.82, "AI disruption SaaS selloff software stocks"),
            _make_chunk("c3", 0.90, "AI disruption SaaS software selloff"),
            _make_chunk("c4", 0.78, "AI disruption SaaS software stocks selloff pressure"),
            _make_chunk("c5", 0.75, "AI disruption SaaS software selloff impact"),
        ]
        result = _dedup_web_chain_results(chunks, threshold=0.60)
        assert len(result) == 1
        assert result[0]["id"] == "c3"  # highest score
        assert result[0]["metadata"]["validation_count"] == 5
        assert result[0]["metadata"]["similar_count"] == 5

    def test_two_clusters_from_mixed_input(self):
        """Mix of AI + CAPEX chains → 2 clusters."""
        chunks = [
            _make_chunk("ai1", 0.85, "AI disruption causes SaaS software selloff"),
            _make_chunk("ai2", 0.80, "AI disruption leads SaaS selloff software"),
            _make_chunk("capex1", 0.75, "hyperscaler CAPEX overspending value destruction"),
            _make_chunk("capex2", 0.70, "CAPEX overspending hyperscaler value destruction ROI"),
        ]
        result = _dedup_web_chain_results(chunks, threshold=0.60)
        assert len(result) == 2
        ids = {r["id"] for r in result}
        assert "ai1" in ids   # highest in AI cluster
        assert "capex1" in ids  # highest in CAPEX cluster

    def test_validation_count_summed_across_cluster(self):
        """validation_count from all cluster members are summed."""
        c1 = _make_chunk("c1", 0.9, "AI disruption SaaS selloff", validation_count=3)
        c2 = _make_chunk("c2", 0.7, "AI disruption SaaS selloff stocks", validation_count=2)
        result = _dedup_web_chain_results([c1, c2], threshold=0.60)
        assert len(result) == 1
        assert result[0]["metadata"]["validation_count"] == 5


# ── Converter pass-through tests ───────────────────────────────────────────

from knowledge_gap_detector import _convert_saved_chunks_to_web_chains


class TestConvertSavedChunksPassthrough:
    def test_validation_count_passed_through(self):
        """validation_count and similar_count from metadata appear in output chain."""
        import json
        chunk = {
            "id": "web_abc123",
            "score": 0.8,
            "metadata": {
                "source": "Yahoo Finance",
                "validation_count": 5,
                "similar_count": 3,
                "extracted_data": json.dumps({
                    "logic_chains": [{
                        "steps": [{
                            "cause": "AI disruption",
                            "effect": "SaaS selloff",
                            "mechanism": "replacement fear",
                        }],
                        "source": "Yahoo Finance",
                    }],
                }),
            },
        }
        chains = _convert_saved_chunks_to_web_chains([chunk])
        assert len(chains) == 1
        assert chains[0]["validation_count"] == 5
        assert chains[0]["similar_count"] == 3

    def test_defaults_to_one(self):
        """When metadata lacks validation_count/similar_count, defaults to 1."""
        import json
        chunk = {
            "id": "web_xyz",
            "score": 0.6,
            "metadata": {
                "source": "Reuters",
                "extracted_data": json.dumps({
                    "logic_chains": [{
                        "steps": [{"cause": "A", "effect": "B", "mechanism": "M"}],
                    }],
                }),
            },
        }
        chains = _convert_saved_chunks_to_web_chains([chunk])
        assert len(chains) == 1
        assert chains[0]["validation_count"] == 1
        assert chains[0]["similar_count"] == 1

    def test_fallback_path_also_passes_counts(self):
        """When extracted_data is empty, fallback path also includes counts."""
        chunk = {
            "id": "web_fallback",
            "score": 0.5,
            "metadata": {
                "cause": "rate hike",
                "effect": "bond selloff",
                "source": "Bloomberg",
                "validation_count": 2,
                "similar_count": 2,
            },
        }
        chains = _convert_saved_chunks_to_web_chains([chunk])
        assert len(chains) == 1
        assert chains[0]["validation_count"] == 2
        assert chains[0]["similar_count"] == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
