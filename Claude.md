# AI for BI - AI Helper Context

## Project Overview

**Purpose:** Business Intelligence solution - query databases using natural language (Vietnamese/English)

**Location:** `~/Workspace/git/ai-for-bi/`

**Tech Stack:**
- Open WebUI (Chat UI) - GitHub: https://github.com/nnkhoa/open-webui
- LiteLLM (LLM router) - FPT Gemma 4 31B, GPT-4, Claude, Gemini
- DBHub (MCP servers) - Database access with RBAC
- PostgreSQL (2 containers) - System DBs + Demo DB

---

## Architecture

### Docker Compose Location
```bash
cd ~/Workspace/git/ai-for-bi/stack
```

### Services
| Service | Port | Purpose |
|---------|------|---------|
| Open WebUI | 3000 | Chat UI, user management |
| LiteLLM | 4000 | LLM router |
| aibi-postgres | 5432 | System DBs (litellm, openwebui_app, aibi_demo) |
| aibi-postgres-bi | 5433 | Demo DB with RBAC (aibi_rbac_demo) |
| nova_dbhub_sales | 5101 | Sales MCP server |
| nova_dbhub_finance | 5102 | Finance MCP server |
| nova_dbhub_hr | 5103 | HR MCP server |
| nova_dbhub_exec | 5104 | Executive MCP server |

---

## RBAC Roles (Simplified - Demo Only)

**CRITICAL:** This is HOMELAB DEMO, NOT production. RBAC is simplified.

| Role | Database User | Access |
|------|---------------|--------|
| Sales | aibi_sales | customers, orders, products, order_items |
| Finance | aibi_finance | customers, orders, invoices, expenses |
| HR | aibi_hr | employees, salaries |
| Executive | aibi_exec | ALL tables (full access) |

**Production will have:** Complex RBAC, proper security, real data.

---

## Development Workflow

### Start Stack
```bash
cd ~/Workspace/git/ai-for-bi/stack
docker compose up -d
```

### Check Status
```bash
docker compose ps
docker logs aibi-openwebui --tail 20
docker logs aibi-litellm --tail 20
```

### Restart Services
```bash
docker compose restart open-webui
docker compose restart litellm
```

### Stop Stack
```bash
docker compose down
```

---

## Database Access

### System DB
```bash
psql -h 127.0.0.1 -p 5432 -U aibi -d openwebui_app
psql -h 127.0.0.1 -p 5432 -U aibi -d litellm
```

### Demo DB (RBAC)
```bash
# As executive (full access)
psql -h 127.0.0.1 -p 5433 -U aibi_bi -d aibi_rbac_demo

# As sales (limited access)
psql -h 127.0.0.1 -p 5433 -U aibi_sales -d aibi_rbac_demo
```

---

## Common Tasks

### Test LiteLLM
```bash
curl http://localhost:4000/v1/models \
  -H "Authorization: Bearer sk-litellm-dev-key-2026" | jq '.data[].id'

curl -X POST http://localhost:4000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer sk-litellm-dev-key-2026" \
  -d '{
    "model": "fpt-gemma-4-31b",
    "messages": [{"role": "user", "content": "Xin chào"}],
    "max_tokens": 50
  }'
```

### Test DBHub (MCP)
```bash
# Sales query orders (should succeed)
curl -X POST http://localhost:5101/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "execute_sql",
      "arguments": {
        "sql": "SELECT COUNT(*) FROM orders;"
      }
    }
  }'

# Sales query salaries (should fail - permission denied)
curl -X POST http://localhost:5101/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{
    "jsonrpc": "2.0",
    "id": 2,
    "method": "tools/call",
    "params": {
      "name": "execute_sql",
      "arguments": {
        "sql": "SELECT * FROM salaries;"
      }
    }
  }'
```

### Backup Database
```bash
# System DB
docker exec aibi-postgres pg_dump -U aibi openwebui_app > backup.sql

# Demo DB
docker exec aibi-postgres-bi pg_dump -U aibi_bi aibi_rbac_demo > demo-backup.sql
```

---

## Open WebUI Configuration

### Stashed Changes (Need to Apply)
```bash
cd ~/Workspace/git/open-webui
git stash pop
```

**Changes include:**
- CORS_ALLOW_ORIGIN: https://openweb.nhukhoa-nguyen.org, http://localhost:3000
- DATABASE_URL: postgresql://aibi:aibi_dev_2026@127.0.0.1:5432/openwebui_app
- PORT: 3000 (changed from 8080)

### Configure MCP Servers
Import `mcp-servers-nova.json` or `mcp-servers-nova.yaml` into Open WebUI to connect Nova DBHub instances.

---

## Troubleshooting

### Open WebUI Cannot Connect to Database
- Check aibi-postgres is running: `docker ps | grep aibi-postgres`
- Verify DATABASE_URL in container env: `docker exec aibi-openwebui env | grep DATABASE_URL`
- Test connection: `psql -h 127.0.0.1 -p 5432 -U aibi -d openwebui_app`

### LiteLLM 401 Unauthorized
- Check FPT API key in stack/.env
- Verify litellm_config.yaml model format: `openai/gemma-4-31B-it`
- Restart litellm: `docker compose restart litellm`

### DBHub Unhealthy
- Check logs: `docker logs nova_dbhub_sales`
- Verify database connection: DSN in docker-compose.yml
- Test DB user permissions in database

### Cloudflare Tunnel Down
- Check status: `cloudflared tunnel info homelab`
- Restart: `brew services restart cloudflared`
- Manual start: `cloudflared tunnel run homelab`

---

## Documentation

**Key Files:**
- `stack/docs/DEPLOYMENT.md` - Full deployment guide
- `stack/docs/NOVA_DBHUB_CONFIG.md` - Nova DBHub instances
- `stack/docs/RBAC_PERMISSIONS_SUMMARY.md` - RBAC permissions
- `stack/docs/FPT_GEMMA_CONFIG.md` - FPT AI integration
- `stack/docs/DATABASE_ARCHITECTURE_REFACTOR.md` - Database architecture

---

## Critical Reminders

1. **Homelab != Production** - This is demo/test environment only
2. **RBAC is simplified** - Production will have complex RBAC
3. **Don't use real production data** - This is for testing only
4. **Secrets in .env** - Move to Docker Secrets for production
5. **CORS='*' is bad** - Restrict to specific domains in production
6. **Always backup** before changing database schema
7. **Test RBAC** - Verify users cannot access unauthorized tables

---

## Project Commands Summary

```bash
# Start everything
cd ~/Workspace/git/ai-for-bi/stack && docker compose up -d

# Check status
cd ~/Workspace/git/ai-for-bi/stack && docker compose ps

# View logs
docker logs aibi-openwebui -f
docker logs aibi-litellm -f

# Restart service
docker compose restart open-webui

# Access database
psql -h 127.0.0.1 -p 5432 -U aibi -d openwebui_app
psql -h 127.0.0.1 -p 5433 -U aibi_bi -d aibi_rbac_demo

# Test LiteLLM
curl http://localhost:4000/v1/models -H "Authorization: Bearer sk-litellm-dev-key-2026"

# Backup
docker exec aibi-postgres pg_dump -U aibi openwebui_app > backup.sql

# Apply Open WebUI stashed changes
cd ~/Workspace/git/open-webui && git stash pop
```

---

**Last Updated:** 2026-04-19

**Context Updated:** Homelab demo environment - simplified RBAC, not production-grade.
