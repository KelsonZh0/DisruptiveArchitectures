"""Cloudflare Workers AI embeddings, matching the ingestion model."""

import httpx


class EmbeddingService:
    def __init__(self, account_id: str, token: str, timeout: float = 30) -> None:
        self.account_id = account_id
        self.token = token
        self.timeout = timeout

    def embed(self, text: str) -> list[float]:
        if not self.account_id or not self.token:
            raise RuntimeError("Cloudflare Workers AI não está configurado")
        url = f"https://api.cloudflare.com/client/v4/accounts/{self.account_id}/ai/run/@cf/baai/bge-m3"
        response = httpx.post(url, headers={"Authorization": f"Bearer {self.token}"}, json={"text": [text]}, timeout=self.timeout)
        response.raise_for_status()
        body = response.json()
        if not body.get("success") or not body.get("result", {}).get("data"):
            raise RuntimeError("Workers AI não retornou embedding")
        vector = body["result"]["data"][0]
        if len(vector) != 1024:
            raise RuntimeError(f"Dimensão inesperada de embedding: {len(vector)}")
        return vector
