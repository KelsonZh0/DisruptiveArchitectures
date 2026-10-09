# Bem vindo disciplina de Disruptive Architectures: IA e IoT

Olá pessoal, bem vindos!! Neste repositório você irá encontrar os conteúdos ministrados em sala de aula assim como dicas, exemplos e laboratórios. 

## Para acompanhar os roteiros práticos 

Acesse o site:

- [website: https://arnaldojr.github.io/DisruptiveArchitectures/](https://arnaldojr.github.io/DisruptiveArchitectures/)


## Como clonar o repositório

``` bash
$ # no terminal digite
$ git clone https://github.com/arnaldojr/DisruptiveArchitectures/

```

## Assistente RAG — etapa 2

A etapa 2 prepara a extração do material (Markdown e notebooks), a geração de
embeddings e o schema inicial do banco. A extração é local e não executa
células dos notebooks. Há migrations separadas para PostgreSQL e Oracle.

### Conferir a extração local

No PowerShell, a partir da raiz do repositório:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r scripts\requirements.txt
python scripts\ingest.py `
  --material-dir material `
  --base-url https://kelsonzh0.github.io/DisruptiveArchitectures `
  --output scripts\chunks.jsonl
```

O arquivo `scripts/chunks.jsonl` terá um chunk JSON por linha. Para conferir a
quantidade gerada:

```powershell
(Get-Content scripts\chunks.jsonl).Count
```

### Gerar embeddings e arquivo do Vectorize

Configure o Account ID e o token Cloudflare no terminal (não os coloque em
arquivos commitados) e rode:

```powershell
$env:CF_ACCOUNT_ID = "SEU_ACCOUNT_ID"
$env:CF_API_TOKEN = "SEU_TOKEN"
python scripts\embed_with_workers_ai.py `
  --input scripts\chunks.jsonl `
  --output scripts\chunks_embedded.jsonl
python scripts\build_vectorize_ndjson.py `
  --input scripts\chunks_embedded.jsonl `
  --output scripts\vectors.ndjson
```

Esses dois últimos comandos fazem chamadas ao Cloudflare Workers AI. O workflow
do GitHub também os executa após push. Configure os secrets
`CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN`, `ORACLE_USER` e
`ORACLE_PASSWORD` no repositório. Se necessário, configure também
`ORACLE_HOST`, `ORACLE_PORT`, `ORACLE_SID` ou `ORACLE_SERVICE_NAME`. O workflow
sincroniza os chunks no Oracle, atualiza o Vectorize e remove os IDs que saíram
do material.

### Carregar os chunks no Oracle

Depois de gerar `scripts/chunks.jsonl`, configure as variáveis Oracle como na
etapa 3 e execute:

```powershell
python scripts\load_chunks_oracle.py --input scripts\chunks.jsonl
```

O script cria uma versão de ingestão e sincroniza os chunks em `reindex_runs` e
`chunks`, removendo da tabela os chunks que já não aparecem na extração. Ele não
envia embeddings ao Vectorize; essa é uma etapa separada.
Se a geração de embeddings falhar e deixar um JSONL parcial, repita o comando
de embeddings acrescentando `--resume`; o script valida e preserva os chunks
já processados e informa o ID do chunk caso a Cloudflare rejeite um texto.

Para o backend pesquisar e para publicar os vetores, o token usado pelo projeto
precisa também das permissões `Vectorize Read` e `Vectorize Edit`, além de
`Workers AI Read` e `Workers AI Edit`. O Account ID e o token podem ser
configurados nas variáveis `CLOUDFLARE_ACCOUNT_ID` e `CLOUDFLARE_API_TOKEN`; os
scripts de embedding também aceitam os aliases `CF_ACCOUNT_ID` e `CF_API_TOKEN`.

### Preparar o Oracle da FIAP

O backend usa o Oracle Database da FIAP. Confirme com a faculdade se o acesso
externo está liberado e se a conexão deve usar SID (`orcl`) ou service name.
Conecte no SQL Developer com o usuário da aplicação e execute
`backend/migrations/oracle_001_initial_schema.sql`. A conta precisa poder criar
tabelas e índices. A migration ainda não carrega os chunks automaticamente.

## Assistente RAG — etapa 3 (API)

O backend oferece POST /ask, GET /health e GET /conversas/{id}. Para instalar
e iniciar no PowerShell, a partir da raiz do repositório:

~~~powershell
py -3.12 -m pip install --user -r requirements.txt
$env:ORACLE_USER = "SEU_USUARIO_FIAP"
$env:ORACLE_PASSWORD = "SUA_SENHA"
$env:ORACLE_HOST = "oracle.fiap.com.br"
$env:ORACLE_PORT = "1521"
$env:ORACLE_SID = "orcl"
# Se a FIAP fornecer service name, use-o no lugar do SID:
# $env:ORACLE_SERVICE_NAME = "SERVICE_NAME_FORNECIDO"
$env:GEMINI_API_KEY = "SUA_CHAVE_GEMINI" # opcional se GROQ_API_KEY estiver configurada
$env:GROQ_API_KEY = "SUA_CHAVE_GROQ" # fallback ou provedor único
$env:ALLOWED_ORIGIN = "http://127.0.0.1:8001" # site MkDocs local
$env:PYTHONPATH = (Get-Location).Path
py -3.12 -m uvicorn backend.app.main:app --reload --port 8000
~~~

Abra http://127.0.0.1:8000/health para conferir o processo. O endpoint /ask só
funcionará quando houver dados no Oracle e as variáveis de ambiente
estiverem configuradas: ORACLE_USER, ORACLE_PASSWORD, um provedor de geração
(`GEMINI_API_KEY` ou `GROQ_API_KEY`), CLOUDFLARE_ACCOUNT_ID e
CLOUDFLARE_API_TOKEN. Configure as chaves no terminal ou em um `.env` local
que não seja commitado. O driver `python-oracledb` usa Thin
mode por padrão e não exige Oracle Client para uma conexão TCP normal. Para
consultas ao Vectorize, o token também precisa de `Vectorize Read`; para
publicar embeddings no índice, precisa de `Vectorize Edit`. A chave do Gemini
é obtida separadamente no Google AI Studio.

O Gemini usa `gemini-3.8-flash` como modelo principal. Se houver erro de limite
ou cota, tenta em sequência `gemini-3.7-flash`, `gemini-3.6-flash`,
`gemini-3.5-flash` e `gemini-3.5-flash-lite`. Para mudar a seleção, defina
`GEMINI_MODEL` e `GEMINI_FALLBACK_MODELS` no PowerShell antes de iniciar o
backend. Separe os fallbacks por vírgula. Isso ajuda quando o limite específico
do modelo acaba; não resolve uma cota ou limite de gastos esgotado para todo o
projeto Google.
Depois de esgotar os modelos Gemini por cota, limite ou indisponibilidade
temporária, o backend tenta `openai/gpt-oss-20b` pela API Groq quando
`GROQ_API_KEY` está configurada. Se `GEMINI_API_KEY` não estiver configurada,
o Groq é usado diretamente. Esse modelo suporta saída JSON estruturada;
os limites e a disponibilidade dependem da conta Groq. O nome do modelo pode
ser alterado com `GROQ_MODEL`.

O workflow de publicação do MkDocs publica apenas o site estático, não o
backend. Em desenvolvimento local, o widget usa automaticamente
`http://127.0.0.1:8000/ask`.

### Publicar a API no Vercel

A raiz do repositório está configurada para o Vercel executar
`backend.app.main:app` como uma função Python. O arquivo `requirements.txt`
contém as dependências da API; `docs-requirements.txt` contém as dependências
do MkDocs. Para publicar a API:

1. Instale o Vercel CLI (`npm install --global vercel`) e autentique com
   `vercel login`.
2. Na raiz do repositório, execute `vercel link` e associe o projeto à sua
   conta/equipe Vercel.
3. No painel do projeto Vercel, cadastre as variáveis abaixo nos ambientes
   **Production** e **Preview**. Use os valores secretos diretamente no painel;
   não os coloque no Git nem os envie pelo chat.

   - `ORACLE_USER`, `ORACLE_PASSWORD`, `ORACLE_HOST`, `ORACLE_PORT` e
     `ORACLE_SID` ou `ORACLE_SERVICE_NAME`
   - `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN`
   - `GEMINI_API_KEY` e/ou `GROQ_API_KEY`
   - `ALLOWED_ORIGIN=https://arnaldojr.github.io`

   O Oracle da FIAP precisa aceitar conexões externas originadas da Vercel.
   Se a rede ou política da FIAP bloquear esse acesso, a API hospedada não
   conseguirá consultar os dados, mesmo com as credenciais corretas.
4. Publique primeiro um preview com `vercel deploy`. Confira
   `https://<url-do-preview>/health` (deve retornar `{"status":"ok"}`) e
   `https://<url-do-preview>/docs`. Depois de configurar e validar as variáveis,
   publique em produção com `vercel deploy --prod`.
5. Copie a URL HTTPS de produção para `window.DA_RAG_API_URL` em
   `material/js/chat-config.js`, acrescentando `/ask` ao final. Faça commit e
   push para atualizar o site GitHub Pages; a API e o site são deploys
   separados.

As variáveis do Vercel só ficam disponíveis em novos deploys: depois de alterar
uma variável, gere outro deploy. A publicação no Vercel ainda depende de acesso
à conta Vercel e de conectividade externa do Oracle da FIAP.

Para instalar as dependências do site localmente, use
`python -m pip install -r docs-requirements.txt` e rode `python -m mkdocs serve`.

Para executar os testes automatizados:

~~~powershell
$env:PYTHONPATH = (Get-Location).Path
python -m pytest backend\tests -q
~~~

Os testes usam doubles para não chamar Gemini, Cloudflare ou Oracle. Eles
cobrem ingestão, slugs e IDs, fusão RRF, validação de citações, contrato dos
handlers, limite de requisições e prompt estruturado.
