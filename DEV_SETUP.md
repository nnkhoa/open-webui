# Development setup

How to run this fork locally. For what is customized and why, read `Claude.md`.

## Prerequisites

- Node 22 and npm
- Python 3.11 with [uv](https://docs.astral.sh/uv/)
- Docker, for the LLM gateway and the database stack

## Run it

### 1. Backend

```bash
cd backend
uv sync
WEBUI_SECRET_KEY=dev-secret uv run uvicorn open_webui.main:app --reload --port 8080
```

SQLite under `backend/data/` is the default, which is fine for development.
Alembic migrations run on startup.

> Importing `open_webui.config` **empties `backend/open_webui/static/`** and
> refills it from `build/static`. With no frontend build present, that leaves the
> directory empty and `git status` full of deleted icons. When running backend
> scripts or tests without a build, point it elsewhere:
> `STATIC_DIR=/tmp/ow-static uv run ...`

### 2. Frontend

```bash
npm install
npm run dev          # http://localhost:5173, proxies the API to :8080
```

For a production build:

```bash
NODE_OPTIONS=--max-old-space-size=7168 npm run build
```

4GB of heap is not enough for this codebase — the build dies with
"Ineffective mark-compacts near heap limit". The `Dockerfile` carries its own
`NODE_OPTIONS`; raise it there too before building an image.

`npm ci` is per branch. Switching between `merge/v0.10.2` and `merge/v0.11.4`
without reinstalling gives "Rollup failed to resolve import", because their
dependency sets differ.

### 3. The rest of the stack

LiteLLM, Postgres, Cube and the DBHub MCP servers live in the parent repo, not
here:

```bash
cd ..                 # ai-for-bi/
docker compose -f docker-compose.yml -f docker-compose.mem.yml up -d
```

Each stack directory (for example `nhabe/`) has its own compose file and needs
its own `.env` — Compose reads `.env` next to the compose file, never from the
parent directory. A missing `.env` shows up as `No connected db` from LiteLLM,
because the master key arrives empty and every request is treated as a virtual
key.

Model routing is configured in `../config/litellm_config.yaml`.

## Point the UI at the stack

First run, as admin:

1. Settings → Connections → add an OpenAI connection with base URL
   `http://litellm:4000/v1` (or `http://localhost:5441/v1` from the host) and the
   master key from `.env`.
2. Settings → Tools → add the DBHub MCP server, for example
   `http://dbhub:5001/mcp`, auth `None`.
3. Admin → Project Config → set the logo, brand color and organization name.

Restricting tools per group: on the tool server connection's config, set

```json
{
  "function_name_filters_by_group": {
    "<group_id>": "execute_sql,search_objects"
  }
}
```

A user in several listed groups gets the union. Admins with
`BYPASS_ADMIN_ACCESS_CONTROL` skip filtering entirely.

## Useful environment variables

| Variable | Default | What it does |
|---|---|---|
| `AI4BI_SCHEMA_INJECTION` | `true` | Preload `_meta_*` metadata into the system prompt |
| `AI4BI_METADATA_PATTERN` | `_meta_%` | LIKE pattern for metadata tables |
| `AI4BI_SCHEMA_TTL` | `3600` | Metadata cache TTL, seconds |
| `STREAM_KEEPALIVE_INTERVAL` | `15` | SSE keepalive interval; `0` disables it |
| `AIBI_ORG_NAME` / `AIBI_ORG_SUBTITLE` / `AIBI_APP_NAME` | empty | Branding seeds, overridden by the admin page |
| `ENABLE_NEW_CHAT_ON_MODEL_CHANGE` | `true` | Switching model inside a chat starts a new one |

## Tests

```bash
cd backend
STATIC_DIR=/tmp/ow-static WEBUI_SECRET_KEY=dev uv run pytest open_webui/test/util -q
```

`open_webui/test/util/test_tool_result_fallback.py` covers the tool-result
fallback and the permission-error detection, including the case where query data
merely contains words like "forbidden".
