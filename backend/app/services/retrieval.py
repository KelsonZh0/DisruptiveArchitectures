"""Hybrid search ranking helpers."""

from collections.abc import Sequence

from backend.app.schemas.chat import Chunk


def reciprocal_rank_fusion(result_lists: Sequence[Sequence[Chunk]], k: int = 60) -> list[Chunk]:
    """Combine ranked lists without treating raw scores as confidence."""
    fused: dict[str, Chunk] = {}
    fusion_scores: dict[str, float] = {}
    ranks_by_id: dict[str, dict[str, int]] = {}
    for list_index, results in enumerate(result_lists):
        source = "vector" if list_index == 0 else f"text_{list_index}"
        seen: set[str] = set()
        for rank, chunk in enumerate(results, start=1):
            if chunk.id in seen:
                continue
            seen.add(chunk.id)
            fusion_scores[chunk.id] = fusion_scores.get(chunk.id, 0) + 1 / (k + rank)
            ranks_by_id.setdefault(chunk.id, {})[source] = rank
            fused.setdefault(chunk.id, chunk)
    return [
        fused[chunk_id].model_copy(update={"score": score, "ranks": ranks_by_id[chunk_id]})
        for chunk_id, score in sorted(fusion_scores.items(), key=lambda item: (-item[1], item[0]))
    ]
