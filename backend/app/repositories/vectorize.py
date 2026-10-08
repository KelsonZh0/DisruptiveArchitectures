"""Cloudflare Vectorize REST adapter."""

import httpx

from backend.app.schemas.chat import Chunk


class VectorizeRepository:
    def __init__(self, account_id: str, token: str, index: str, timeout: float = 30) -> None:
        self.account_id, self.token, self.index, self.timeout = account_id, token, index, timeout

    def search(self, vector: list[float], top_k: int) -> list[Chunk]:
        url = f"https://api.cloudflare.com/client/v4/accounts/{self.account_id}/vectorize/v2/indexes/{self.index}/query"
        response = httpx.post(url, headers={"Authorization": f"Bearer {self.token}"}, json={"vector": vector, "topK": top_k, "returnMetadata": "all"}, timeout=self.timeout)
        response.raise_for_status()
        body = response.json()
        if not body.get("success"):
            raise RuntimeError("Vectorize retornou uma falha")
        chunks = []
        for match in body.get("result", {}).get("matches", []):
            metadata = match.get("metadata") or {}
            chunks.append(Chunk(id=match["id"], titulo=metadata.get("titulo", "Material do curso"), secao=metadata.get("secao", ""), url=metadata.get("url", "https://kelsonzh0.github.io/DisruptiveArchitectures/"), texto="", score=float(match.get("score", 0))))
        return chunks
