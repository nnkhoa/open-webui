# AI for BI — fork context

Ask a database a question in Vietnamese or English and get an answer. This repo
is the chat UI: a fork of [Open WebUI](https://github.com/open-webui/open-webui)
carrying the AI4BI customizations.

## Branch layout

| Branch | Upstream base | What it is |
|---|---|---|
| `merge/v0.10.2` | `v0.10.2` | Current work: upstream v0.10.2 + the AI4BI customizations |
| `merge/v0.11.4` | `v0.11.4` | Upstream bump only, no customizations yet |
| `stable_0.8.5` | `v0.8.12` | The previous production branch; the customizations came from here |

Remotes: `origin` is the fork, `upstream` is `open-webui/open-webui`.

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
- `src/lib/components/layout/NovaHeader.svelte` — the fixed 56px topbar with the
  customer logo and the user menu

Env seeds (config wins once set in the admin page): `AIBI_PROJECT_LOGO`,
`AIBI_BRAND_COLOR`, `AIBI_ORG_NAME`, `AIBI_ORG_SUBTITLE`, `AIBI_APP_NAME`,
`AIBI_MODEL_DISPLAY_NAMES` (JSON), `ENABLE_NEW_CHAT_ON_MODEL_CHANGE`.

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
  reached through the gear icon in NovaHeader.
- BuildKit cache mounts in the `Dockerfile` for npm, pip and uv.

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

```bash
# Backend (from backend/)
WEBUI_SECRET_KEY=dev uv run uvicorn open_webui.main:app --reload --port 8080

# Frontend
npm install
npm run dev
```

Two landmines worth knowing:

1. **Importing `open_webui.config` wipes `backend/open_webui/static/`** and
   repopulates it from `build/static`. Run backend commands with
   `STATIC_DIR=/tmp/somewhere` when there is no fresh frontend build, or you will
   commit a deleted icon set.
2. **`npm run build` needs more than 4GB of heap.** Use
   `NODE_OPTIONS=--max-old-space-size=7168`. The `Dockerfile` sets its own value;
   check it before building an image.

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
