-- Schema inicial do assistente RAG. Compatível com PostgreSQL/Supabase.
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS reindex_runs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    versao text NOT NULL UNIQUE,
    status text NOT NULL DEFAULT 'processing'
        CHECK (status IN ('processing', 'syncing_vectors', 'active', 'failed')),
    total_chunks integer NOT NULL DEFAULT 0 CHECK (total_chunks >= 0),
    erro text,
    iniciado_em timestamptz NOT NULL DEFAULT now(),
    concluido_em timestamptz
);

CREATE TABLE IF NOT EXISTS chunks (
    id text PRIMARY KEY,
    titulo text NOT NULL,
    secao text NOT NULL DEFAULT '',
    url text NOT NULL,
    origem text NOT NULL,
    indice integer NOT NULL CHECK (indice >= 0),
    texto text NOT NULL,
    versao_ingestao text NOT NULL REFERENCES reindex_runs(versao),
    busca tsvector GENERATED ALWAYS AS (
        setweight(to_tsvector('portuguese', coalesce(titulo, '')), 'A') ||
        setweight(to_tsvector('portuguese', coalesce(secao, '')), 'A') ||
        setweight(to_tsvector('portuguese', coalesce(texto, '')), 'B')
    ) STORED,
    criado_em timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS chunks_busca_idx ON chunks USING gin (busca);
CREATE INDEX IF NOT EXISTS chunks_versao_idx ON chunks (versao_ingestao);
CREATE INDEX IF NOT EXISTS chunks_origem_idx ON chunks (origem);

CREATE TABLE IF NOT EXISTS conversas (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    token_hash bytea NOT NULL,
    criada_em timestamptz NOT NULL DEFAULT now(),
    atualizada_em timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS mensagens (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    conversa_id uuid NOT NULL REFERENCES conversas(id) ON DELETE CASCADE,
    papel text NOT NULL CHECK (papel IN ('user', 'assistant')),
    conteudo text NOT NULL,
    criada_em timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS mensagens_conversa_ordem_idx ON mensagens (conversa_id, criada_em, id);

CREATE TABLE IF NOT EXISTS interaction_logs (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    conversa_id uuid REFERENCES conversas(id) ON DELETE SET NULL,
    pergunta text NOT NULL,
    resposta text,
    chunks_recuperados jsonb NOT NULL DEFAULT '[]'::jsonb,
    latencia_ms integer CHECK (latencia_ms IS NULL OR latencia_ms >= 0),
    tokens_entrada integer CHECK (tokens_entrada IS NULL OR tokens_entrada >= 0),
    tokens_saida integer CHECK (tokens_saida IS NULL OR tokens_saida >= 0),
    erro text,
    criada_em timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS interaction_logs_conversa_idx ON interaction_logs (conversa_id, criada_em DESC);

-- Busca híbrida lexical. Os scores serão combinados com os ranks vetoriais pela aplicação.
CREATE OR REPLACE FUNCTION buscar_chunks_texto(
    consulta text,
    limite integer DEFAULT 20
) RETURNS TABLE (
    id text,
    titulo text,
    secao text,
    url text,
    texto text,
    score real
) LANGUAGE sql STABLE AS $$
    SELECT c.id, c.titulo, c.secao, c.url, c.texto,
           ts_rank_cd(c.busca, websearch_to_tsquery('portuguese', consulta)) AS score
    FROM chunks AS c
    WHERE c.busca @@ websearch_to_tsquery('portuguese', consulta)
    ORDER BY score DESC, c.id
    LIMIT greatest(1, least(limite, 100));
$$;

