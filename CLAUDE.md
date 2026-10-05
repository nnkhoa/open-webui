# AI for BI — fork context

Ask a database a question in Vietnamese or English and get an answer. This repo
is the chat UI: a fork of [Open WebUI](https://github.com/open-webui/open-webui)
carrying the AI4BI customizations.

## Branch layout

| Branch | Upstream base | What it is |
|---|---|---|
| `nbc/v0.10.2` | `v0.10.2` | May Nhà Bè (NBC): `merge/v0.10.2` + Data Portal, NBC branding |
| `merge/v0.10.2` | `v0.10.2` | Upstream v0.10.2 + the AI4BI customizations |
| `merge/v0.11.4` | `v0.11.4` | Upstream bump only, no customizations yet |
| `stable_0.8.5` | `v0.8.12` | The previous production branch; the customizations came from here |

Remotes: `origin` is the fork, `upstream` is `open-webui/open-webui`.

## Working here

This repo lives inside the `ai-for-bi` workspace (`../../`), whose `CLAUDE.md` holds the
cross-repo rules. In short:

- Fixes for the NBC deployment are committed directly on `nbc/v0.10.2`; other work goes on a
  `feat/<topic>` branch and is merged into `merge/vX.Y.Z` (workspace ADR 0002).
- Every customization commit carries an `Fpt-Feature: <id>` trailer, and the feature ledger is
  `../../docs/forks/open-webui.md` (workspace repo) — add or update its row in the same change.
- Put fork logic in new modules (e.g. `utils/tool_loop.py`) and keep edits to upstream core files
  (`middleware.py`, `config.py`, `main.py`, `Sidebar.svelte`) to a few call-site lines.
- Code identifiers in English; comments, UI text and user-facing messages may be Vietnamese.
- Done means `../../scripts/test.sh fast --only owui-backend,owui-lint,owui-frontend` passes, and
  every new feature or bug fix comes with a test (see Tests).

## What is customized

Everything else is upstream. `git diff v0.10.2..HEAD --stat` is the authoritative list.

### Schema preload (`backend/open_webui/utils/schema_context.py`)

On every chat request, tables matching `_meta_%` in the connected database are
read through the DBHub MCP server and prepended to the system prompt, so the
model knows the schema without spending a tool call on it. The result is cached
in memory (or Redis when configured) per user and set of servers.

- Hooked in `routers/openai.py` → `generate_chat_completion`, via the
  `schema_block` argument of `apply_system_prompt_to_body`.
- Warmed in `routers/chats.py` → `create_new_chat`.
- DBHub servers are discovered from the `tool_server.connections` config and
  filtered by each connection's `access_grants`; admins see all of them.

Env: `AI4BI_SCHEMA_INJECTION`, `AI4BI_METADATA_PATTERN` (default `_meta_%`),
`AI4BI_SCHEMA_TTL` (seconds), `AI4BI_DBHUB_URL_FALLBACK`.

### Project config and branding

Admin-editable logo, brand color, org name and subtitle, app name, model display
names, and the "new chat on model change" switch.

- `backend/open_webui/routers/project_config.py` — `/api/v1/configs/project`
- Served to the frontend pre-auth in the `aibi` block of `/api/config`
- `src/lib/stores/projectConfig.ts`, `src/lib/components/admin/ProjectConfig.svelte`,
  `src/routes/(app)/admin/project/+page.svelte`
- `static/static/nbc-logo.png` — the NBC logo at the top of the sidebar

Env seeds (config wins once set in the admin page): `AIBI_PROJECT_LOGO`,
`AIBI_BRAND_COLOR`, `AIBI_ORG_NAME`, `AIBI_ORG_SUBTITLE`, `AIBI_APP_NAME`,
`AIBI_MODEL_DISPLAY_NAMES` (JSON), `ENABLE_NEW_CHAT_ON_MODEL_CHANGE`.

### Data Portal (`backend/open_webui/data_portal`)

Excel upload for NBC: check the file, write bronze → silver → gold in Postgres,
reconcile, roll back, browse data. The spec is
`DacTa_GiaoDien_DataPortal_OpenWebUI.md`; the API contract is
`data_portal/api/README_API.md`.

- Backend: a FastAPI sub-app mounted at `/api/v1/data-portal` in `main.py`,
  sharing `app.state`. Callers are the signed-in Open WebUI user
  (`get_verified_user`); roles `admin` and `data_uploader` only.
- Started in `lifespan` on a worker thread (opens the SQLite notebook, syncs
  the form registry, connects to the warehouse, applies migrations).
- Storage: `{DATA_DIR}/data_portal/catalog.db` and `uploads/`; the warehouse
  address lives in the notebook, seeded once from `DATA_PORTAL_DATABASE_URL`.
- Forms and groups: `data_portal/definitions/`; migrations:
  `data_portal/migrations/`. After editing a form run
  `python -m open_webui.data_portal.manage makemigration` from `backend/`.
- Frontend: `src/routes/(app)/data-portal/`, `src/lib/components/data-portal/`,
  `src/lib/apis/data-portal/`, `src/lib/stores/dataPortal.ts`; sidebar group in
  `Sidebar.svelte`. Role `data_uploader` ("Data Loader") is accepted wherever
  `user` is.

### Token usage analytics

`GET /api/v1/analytics/chats/{chat_id}/usage` and
`/api/v1/analytics/models/{model_id}/totals`, backed by
`ChatMessages.get_chat_usage_aggregate` and `get_model_totals`. Shown by
`src/lib/components/admin/Analytics/ChatUsage.svelte` under the Analytics tab.
`routers/openai.py` sets `stream_options.include_usage` so streamed replies
report tokens at all.

### Chat behaviour (`backend/open_webui/utils/middleware.py`)

- A turn that only ran tools and streamed no text shows what the tools reported
  instead of an empty bubble (`build_tool_result_fallback_message`).
- A tool reporting a permission error stops the loop with a refusal, rather than
  letting the model retry a denied resource. Only tool *error fields* are
  inspected — see `extract_tool_error_text`.
- Large tool output raises the delta chunk size; pending deltas flush after 50ms
  so uneven streams don't arrive in bursts.
- Responses API connections (`api_type: responses`) get the turn's raw output items back on
  every tool round — reasoning with `encrypted_content`, `function_call` with its `id`, tool
  outputs — so the model keeps its chain of thought (`utils/tool_loop.py`:
  `uses_responses_api`, `responses_replay_items`; `RESPONSES_ALLOWED_FIELDS['reasoning']` in
  `routers/openai.py`). Upstream's `convert_output_to_messages` drops reasoning.
- A tool round that fails (stream error, upstream HTTP ≥ 400) logs a traceback, keeps the
  earlier rounds in the saved message and shows the error in chat instead of an empty answer
  (`tool_loop_http_error`, `tool_loop_exception_error`).
- Deployments must set `CHAT_STREAM_RESPONSE_CHUNK_MAX_BUFFER_SIZE` (32 MiB): the Responses API
  `response.completed` line exceeds aiohttp's 128 KB readline limit at high reasoning effort.

### Per-group tool filtering

`resolve_function_name_filter_list` in `utils/tools.py` reads
`function_name_filters_by_group` from a tool server's config and unions the
entries for the user's groups. Applied both in `get_tools` and on the MCP path
in `middleware.connect_mcp_server`.

### Other

- Stream keepalive in `utils/session_pool.py` (`STREAM_KEEPALIVE_INTERVAL`,
  default 15s) so proxies don't drop slow responses.
- `max_http_buffer_size=10MB` on the socket.io server for large tool results.
- Navbar has no temporary-chat, Controls or user-avatar buttons; settings are
  reached through the user menu at the bottom of the sidebar.
- BuildKit cache mounts in the `Dockerfile` for npm, pip and uv.
- Reasoning display (`src/lib/components/chat/Messages/structuredOutput.ts`): consecutive
  reasoning items merge into one "Thought" block, finished empty ones are hidden, summary parts
  are separated by a blank line.
- `vite.config.ts` proxies `/api` to `:8080` under `vite dev` only, so relative links such as
  file downloads work on `:5173`.

## Config in v0.10.2 — read this before touching settings

v0.10.2 removed `PersistentConfig` and `app.state.config`. Settings now live in
the database, one row per key:

```python
from open_webui.models.config import Config

value = await Config.get('aibi.project.org_name')
values = await Config.get_many('aibi.project.logo_url', 'aibi.project.brand_color')
await Config.upsert({'aibi.project.org_name': 'ACME'})
```

Defaults are registered in the `DEFAULT_CONFIG` dict in `backend/open_webui/config.py`.
The AI4BI keys deliberately keep their 0.8.x names (`aibi.project.*`,
`ui.enable_new_chat_on_model_change`) so the legacy config import carries old
settings over.

Model methods and most router helpers are `async` now, including
`apply_system_prompt_to_body` and everything on `ChatMessageTable`.

## Development

Use the workspace scripts; they set the data dir, secrets, static dir and GPU env for you:

```bash
../../scripts/dev-data.sh        # once: copy the NBC Open WebUI volume to backend/data/nhabe
../../scripts/dev-backend.sh     # backend :8080, hot reload on backend/open_webui/*.py
../../scripts/dev-frontend.sh    # frontend :5173 (Vite HMR)
```

Do not run `uvicorn` by hand from `backend/`: without `DATA_DIR`/`STATIC_DIR` it migrates
`backend/data/webui.db` and rewrites `backend/open_webui/static/`.

## Tests

```bash
../../scripts/test.sh fast --only owui-backend,owui-lint,owui-frontend   # what the pre-push hook runs
cd backend && .venv/bin/python -m pytest open_webui/test/util -q          # backend unit tests
node_modules/.bin/vitest run --dir src                                     # frontend unit tests
```

- Backend tests live in `backend/open_webui/test/util/test_<topic>.py` (file names must be unique —
  there is no `__init__.py`). `test/conftest.py` points `DATA_DIR`, `STATIC_DIR` and
  `FRONTEND_BUILD_DIR` at a temp dir before anything imports `open_webui.config`, so running
  pytest directly is safe. pytest-asyncio is not installed: drive coroutines with `asyncio.run`;
  monkeypatch lazily imported helpers on their home module.
- Frontend logic worth testing goes in plain `.ts` modules with a colocated `*.test.ts`
  (vitest, node environment, no DOM).

## Lint

- Python: the upstream CI rules on changed files —
  `ruff check --select=F --ignore=F401,F403,F405,F541,F811,F841` and `ruff format --check`
  (ruff 0.16.10, line length 120, single quotes). `data_portal/` keeps
  its own double-quote style and are excluded from the format check.
- Frontend: `prettier --check` on changed files (tabs, single quotes, width 100). Never run
  `npm run format` or `npm run lint:frontend` — they rewrite the whole tree.

Landmines worth knowing:

1. **Importing `open_webui.config` wipes `backend/open_webui/static/`**, repopulates it from
   `FRONTEND_BUILD_DIR/static`, runs `alembic upgrade` on `DATABASE_URL` and opens the vector DB
   under `DATA_DIR`. Always set those three (the dev scripts and the test conftest do).
2. **`npm run build` needs more than 4GB of heap.** Use
   `NODE_OPTIONS=--max-old-space-size=7168`. The `Dockerfile` sets its own value;
   check it before building an image.
3. **`npm run dev` rewrites `static/pyodide/pyodide-lock.json`.** Don't commit that change.
4. **The NBC volume was once opened by 0.11.4**: if a DB reports `Can't locate revision`, see
   "DB lệch phiên bản" in `../../docs/forks/open-webui.md` (downgrade with the 0.11.4 scripts).

## Upgrading to a newer upstream

```bash
git fetch upstream --tags
git switch -c merge/vX.Y.Z
git merge vX.Y.Z
```

Expect conflicts in `middleware.py`, `Sidebar.svelte` and `config.py`. Port
feature by feature rather than replaying the old commits: use
`git diff v0.10.2..merge/v0.10.2 -- <path>` as the source of truth for what each
customization actually is.
