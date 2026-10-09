/*
 * Em localhost, usa automaticamente a API local na porta 8000.
 * Antes de publicar o chat, defina a URL HTTPS da API hospedada, por exemplo:
 * window.DA_RAG_API_URL = "https://api.seu-dominio.com/ask";
 *
 * A action do MkDocs publica somente o site estático; ela não hospeda o backend.
 */
const daLocalHost = ["localhost", "127.0.0.1"].includes(window.location.hostname);
window.DA_RAG_API_URL = window.DA_RAG_API_URL || (daLocalHost ? "http://127.0.0.1:8000/ask" : "");
