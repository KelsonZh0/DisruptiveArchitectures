-- Schema inicial do assistente RAG para Oracle Database.
-- Execute conectado ao schema/usuário que será usado pela aplicação.

CREATE TABLE reindex_runs (
    id VARCHAR2(36) DEFAULT RAWTOHEX(SYS_GUID()) PRIMARY KEY,
    versao VARCHAR2(255) NOT NULL UNIQUE,
    status VARCHAR2(32) DEFAULT 'processing' NOT NULL
        CHECK (status IN ('processing', 'syncing_vectors', 'active', 'failed')),
    total_chunks NUMBER(10) DEFAULT 0 NOT NULL CHECK (total_chunks >= 0),
    erro CLOB,
    iniciado_em TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
    concluido_em TIMESTAMP WITH TIME ZONE
);

CREATE TABLE chunks (
    id VARCHAR2(255) PRIMARY KEY,
    titulo NVARCHAR2(1000) NOT NULL,
    secao NVARCHAR2(1000) DEFAULT ' ' NOT NULL,
    url VARCHAR2(2000) NOT NULL,
    origem VARCHAR2(1000) NOT NULL,
    indice NUMBER(10) NOT NULL CHECK (indice >= 0),
    texto CLOB NOT NULL,
    versao_ingestao VARCHAR2(255) NOT NULL REFERENCES reindex_runs(versao),
    criado_em TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL
);

CREATE INDEX chunks_versao_idx ON chunks (versao_ingestao);
CREATE INDEX chunks_origem_idx ON chunks (origem);

CREATE TABLE conversas (
    id VARCHAR2(36) DEFAULT RAWTOHEX(SYS_GUID()) PRIMARY KEY,
    token_hash VARCHAR2(64) NOT NULL,
    criada_em TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
    atualizada_em TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL
);

CREATE TABLE mensagens (
    id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    conversa_id VARCHAR2(36) NOT NULL REFERENCES conversas(id) ON DELETE CASCADE,
    papel VARCHAR2(16) NOT NULL CHECK (papel IN ('user', 'assistant')),
    conteudo CLOB NOT NULL,
    criada_em TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL
);

CREATE INDEX mensagens_conversa_ordem_idx ON mensagens (conversa_id, criada_em, id);

CREATE TABLE interaction_logs (
    id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    conversa_id VARCHAR2(36) REFERENCES conversas(id) ON DELETE SET NULL,
    pergunta CLOB NOT NULL,
    resposta CLOB,
    chunks_recuperados CLOB DEFAULT '[]' NOT NULL CHECK (chunks_recuperados IS JSON),
    latencia_ms NUMBER(10) CHECK (latencia_ms IS NULL OR latencia_ms >= 0),
    tokens_entrada NUMBER(10) CHECK (tokens_entrada IS NULL OR tokens_entrada >= 0),
    tokens_saida NUMBER(10) CHECK (tokens_saida IS NULL OR tokens_saida >= 0),
    erro CLOB,
    criada_em TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL
);

CREATE INDEX interaction_logs_conversa_idx ON interaction_logs (conversa_id, criada_em);



SELECT table_name
FROM user_tables
WHERE table_name IN (
  'REINDEX_RUNS',
  'CHUNKS',
  'CONVERSAS',
  'MENSAGENS',
  'INTERACTION_LOGS'
)
ORDER BY table_name;
