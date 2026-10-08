from backend.app.schemas.chat import Chunk
from backend.app.services.retrieval import reciprocal_rank_fusion

def make_chunk(identifier: str) -> Chunk:
    return Chunk(id=identifier, titulo=identifier, url="https://kelsonzh0.github.io/DisruptiveArchitectures/", texto="evidência")

def test_rrf_promotes_items_in_both_ranked_lists() -> None:
    ranked = reciprocal_rank_fusion([[make_chunk("a"), make_chunk("b")], [make_chunk("b"), make_chunk("c")]], k=60)
    assert [item.id for item in ranked] == ["b", "a", "c"]
    assert ranked[0].ranks == {"vector": 2, "text_1": 1}

def test_rrf_deduplicates_repeated_ids() -> None:
    ranked = reciprocal_rank_fusion([[make_chunk("a"), make_chunk("a")]], k=60)
    assert len(ranked) == 1
    assert ranked[0].score == 1 / 61
