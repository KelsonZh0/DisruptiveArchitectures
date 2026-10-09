/*
 * Em localhost, usa automaticamente a API local na porta 8000.
 * No site publicado, usa a API de produção do Vercel.
 * Para trocar de hospedagem, defina window.DA_RAG_API_URL antes deste arquivo.
 *
 * A action do MkDocs publica somente o site estático; a API é hospedada no Vercel.
 */
const daLocalHost = ["localhost", "127.0.0.1"].includes(window.location.hostname);
window.DA_RAG_API_URL = window.DA_RAG_API_URL || (
  daLocalHost
    ? "http://127.0.0.1:8000/ask"
    : "https://disruptive-architectures-rag.vercel.app/ask"
);
