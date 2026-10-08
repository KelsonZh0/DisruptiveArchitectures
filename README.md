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
embeddings e o schema inicial do PostgreSQL. A extração é local e não executa
células dos notebooks. O schema SQL ainda precisa ser aplicado a um banco; a
carga PostgreSQL e a API serão implementadas nas próximas etapas.

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

Configure `CF_ACCOUNT_ID` e `CF_API_TOKEN` no terminal (não os coloque em
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
do GitHub também os executa após push, usando os secrets configurados no
repositório. O arquivo final pode ser enviado ao índice Vectorize pelo Wrangler
com o comando configurado no workflow; isso altera o índice remoto.

### Preparar o PostgreSQL

Crie um projeto PostgreSQL/Supabase e execute
`backend/migrations/001_initial_schema.sql` no SQL Editor. A migration cria as
tabelas e a função de busca textual. Ela ainda não carrega os chunks: essa parte
será conectada ao banco na próxima etapa.

## Assistente RAG — etapa 3 (API local)

O backend oferece POST /ask, GET /health e GET /conversas/{id}. Para instalar
e iniciar no PowerShell, a partir da raiz do repositório:

~~~powershell
py -3.11 -m venv backend\.venv
.\backend\.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt
$env:PYTHONPATH = (Get-Location).Path
uvicorn backend.app.main:app --reload
~~~

Abra http://127.0.0.1:8000/health para conferir o processo. O endpoint /ask só
funcionará quando houver dados no PostgreSQL e as variáveis de ambiente
estiverem configuradas: DATABASE_URL, GEMINI_API_KEY, CLOUDFLARE_ACCOUNT_ID e
CLOUDFLARE_API_TOKEN. Configure-as apenas no terminal ou em um .env local que
não seja commitado. A carga dos chunks para PostgreSQL ainda precisa ser ligada
ao pipeline de ingestão.

Para executar os testes automatizados:

~~~powershell
$env:PYTHONPATH = (Get-Location).Path
python -m pytest backend\tests -q
~~~

Os testes usam doubles para não chamar Gemini, Cloudflare ou PostgreSQL. Eles
cobrem ingestão, slugs e IDs, fusão RRF, validação de citações, contrato dos
handlers, limite de requisições e prompt estruturado.
