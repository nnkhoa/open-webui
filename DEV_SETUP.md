# Open WebUI Development Environment Setup

This guide helps you set up a complete development environment for Open WebUI with:
- **PostgreSQL** - Production-ready database
- **dbhub (Bytebase)** - Database IDE for managing your PostgreSQL database
- **LiteLLM** - LLM proxy server for testing various models
- **Redis** - Caching and session management
- **Open WebUI** - Main application

## Quick Start

### 1. Start all services

```bash
docker compose -f docker-compose.dev.yaml up -d
```

This will:
- Start PostgreSQL on port 5432
- Start dbhub (Bytebase) on port 5000
- Start Redis on port 6379
- Start LiteLLM proxy on port 4000
- Start MySQL mock database on port 3307

### 2. Start Open WebUI backend

```bash
cd backend
conda activate openwebui  # or your Python environment
python -m open_webui
```

The backend will start on port 8080 by default.

### 3. Start Open WebUI frontend

```bash
npm run dev
```

The frontend will start on port 5173.

### 4. Access the application

- **Open WebUI**: http://localhost:5173
- **dbhub (Bytebase IDE)**: http://localhost:5000
- **LiteLLM API**: http://localhost:4000

## Service Details

### PostgreSQL
- **Host**: localhost:5432
- **Database**: openwebui
- **User**: webui
- **Password**: webui_dev_password

Connect directly:
```bash
docker exec -it open-webui-postgres-dev psql -U webui -d openwebui
```

### dbhub (Bytebase Database IDE)
- **URL**: http://localhost:5000

dbhub là Database IDE của Bytebase, cho phép bạn:
- Quản lý database PostgreSQL/MySQL thông qua giao diện web
- Chạy SQL queries
- Xem database schema
- Quản lý data

**Kết nối dbhub đến PostgreSQL:**
1. Mở http://localhost:5000
2. Thêm connection mới với thông tin:
   - Host: `postgres` (Docker internal)
   - Port: `5432`
   - Database: `openwebui`
   - User: `webui`
   - Password: `webui_dev_password`

**Kết nối dbhub đến MySQL (mock database):**
1. Thêm connection mới với thông tin:
   - Host: `mock_database` (Docker internal)
   - Port: `3306`
   - Database: `lc_aibi`
   - User: `root`
   - Password: `root`

### LiteLLM Proxy
- **URL**: http://localhost:4000
- **Config**: litellm.config.yaml

LiteLLM proxy supports multiple LLM providers including:
- **FPT AI** - Gemma models (configured in litellm.config.yaml)
- OpenAI, Anthropic, Google, and more

### Redis
- **Host**: localhost:6379

Connect directly:
```bash
docker exec -it open-webui-redis-dev redis-cli
```

### MySQL Mock Database
- **Host**: localhost:3307
- **Database**: lc_aibi
- **User**: root
- **Password**: root

Connect directly:
```bash
docker exec -it mock_database mysql -u root -p
```

## Configuration

### Environment Variables

Set up your local environment:

```bash
# LiteLLM as model provider
export OPENAI_API_BASE_URL=http://localhost:4000
export OPENAI_API_KEY=sk-litellm-dev-key

# Database URLs (optional, uses defaults)
export DATABASE_URL=postgresql://webui:webui_dev_password@localhost:5432/openwebui

# MCP Server for dbhub MySQL access
export TOOL_SERVER_CONNECTIONS='[{"type":"mcp","url":"http://localhost:5001/mcp","auth_type":"none","info":{"id":"dbhub-mysql","name":"DBHub MySQL Server","description":"MCP server for lc_aibi MySQL database access"}}]'
```

### LiteLLM Configuration

Edit [litellm.config.yaml](litellm.config.yaml) to add or modify models:

```yaml
model_list:
  - model_name: fpt-gemma-4-31b
    litellm_params:
      model: openai/gemma-4-31B-it
      api_key: os.environ/FPT_API_KEY
      api_base: https://mkp-api.fptcloud.com/v1
      temperature: 0.7
      top_p: 0.9
      max_tokens: 256000
```

**FPT AI API Key:**
Set in environment or docker-compose.dev.yaml:
```yaml
environment:
  - FPT_API_KEY=your_fpt_api_key_here
```

## Available Models (via LiteLLM)

### FPT AI Models
- fpt-gemma-4-31b - Gemma 4 31B (256K context)

### OpenAI Models
- gpt-4
- gpt-3.5-turbo

### Anthropic Models
- claude-3-opus
- claude-3-sonnet

### Google Models
- gemini-pro

### Local Models (Ollama)
- ollama/llama2
- ollama/mistral

### Embedding Models
- text-embedding-ada-002
- text-embedding-3-small

### Image Generation
- dall-e-3

## Development Workflow

### Service Management

```bash
# Start all services
docker compose -f docker-compose.dev.yaml up -d

# Stop all services
docker compose -f docker-compose.dev.yaml down

# Restart a specific service
docker compose -f docker-compose.dev.yaml restart litellm

# View logs
docker compose -f docker-compose.dev.yaml logs -f litellm

# Check service status
docker ps
```

### Backend Development

```bash
cd backend
conda activate openwebui

# Start backend with auto-reload
uvicorn open_webui.main:app --host 0.0.0.0 --port 8080 --reload
```

### Frontend Development

```bash
# Start dev server
npm run dev

# Build for production
npm run build

# Run type checking
npm run check
```

## Testing

### Manual Testing

1. **Test Open WebUI UI**: Open http://localhost:5173

2. **Test LiteLLM Models**:
```bash
curl -X POST http://localhost:4000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer sk-litellm-dev-key" \
  -d '{
    "model": "fpt-gemma-4-31b",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

3. **Test Database Connection**:
```bash
# PostgreSQL
docker exec open-webui-postgres-dev psql -U webui -d openwebui -c "SELECT version();"

# MySQL
docker exec mock_database mysql -u root -proot -e "SELECT VERSION();"
```

4. **Test MCP Server**:
Check if dbhub MCP server is accessible:
```bash
curl http://localhost:5001/mcp
```

## Troubleshooting

### Services not starting

Check Docker is running:
```bash
docker ps
```

Check service logs:
```bash
docker compose -f docker-compose.dev.yaml logs
```

### Database connection errors

Verify PostgreSQL is ready:
```bash
docker exec open-webui-postgres-dev pg_isready -U webui
```

Verify MySQL is ready:
```bash
docker exec mock_database mysqladmin ping -h localhost
```

### LiteLLM not responding

Check LiteLLM health:
```bash
curl http://localhost:4000/health
```

View LiteLLM logs:
```bash
docker logs open-webui-litellm-dev
```

### Frontend not building

Clear cache and rebuild:
```bash
rm -rf node_modules/.vite
npm run dev
```

### Port conflicts

If ports are already in use, modify them in [docker-compose.dev.yaml](docker-compose.dev.yaml):
```yaml
ports:
  - "3001:8080"  # Change 3000 to 3001
```

## Cleaning Up

### Stop services (preserving data)
```bash
docker compose -f docker-compose.dev.yaml down
```

### Stop and remove all data
```bash
docker compose -f docker-compose.dev.yaml down -v
```

### Remove specific volumes
```bash
docker volume rm open-webui-dev_pgdata
docker volume rm open-webui-dev_redisdata
```

## Production Deployment

For production, use the main [docker-compose.yaml](docker-compose.yaml) and:
1. Change all passwords
2. Use proper SSL certificates
3. Configure persistent volumes
4. Set up proper backup strategies
5. Use environment-specific configuration

## Additional Resources

- [Open WebUI Documentation](https://docs.openwebui.com)
- [LiteLLM Documentation](https://docs.litellm.ai)
- [PostgreSQL Documentation](https://www.postgresql.org/docs)
- [FPT AI Documentation](https://fpt.ai)

## Support

For issues related to:
- **Open WebUI**: Open an issue on GitHub
- **LiteLLM**: Check [LiteLLM GitHub](https://github.com/BerriAI/litellm)
- **Docker**: Check [Docker Documentation](https://docs.docker.com)
