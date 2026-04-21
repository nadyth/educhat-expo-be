# Edu Chat BE

## Tech Stack

- **Framework:** FastAPI
- **Database:** PostgreSQL (via asyncpg)
- **ORM:** SQLAlchemy 2.x (async)
- **Migrations:** Alembic
- **Package Manager:** uv

## Environment Variables

Create a `.env` file with the following variables:

```env
SECRET_KEY=<your-secret-key>
GOOGLE_CLIENT_ID=<your-google-client-id>
GOOGLE_CLIENT_SECRET=<your-google-client-secret>
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/edu_chat
DEBUG=true
OLLAMA_ENDPOINT=https://ollama.com
OLLAMA_API_KEY=<your-ollama-api-key>
TUNNEL=true
```

## Local Development (without Docker)

```bash
# Install dependencies
uv sync

# Start a local PostgreSQL instance (or use an existing one)
# Then run migrations
uv run alembic upgrade head

# Start the server
uv run serve
```

Server starts at `http://localhost:8000`.

## Docker Development

Uses hot reload — source changes are reflected instantly.

```bash
# Build and start all services (PostgreSQL + App)
docker compose up --build

# Stop all services
docker compose down

# Stop and remove volumes (resets the database)
docker compose down -v
```

The app runs on `http://localhost:18000` (mapped from container port 8000).

### Run Migrations in Docker

```bash
docker compose exec app alembic upgrade head
```

### Database Mangement

```bash
# Connect to PostgreSQL shell
docker compose exec postgres psql -U postgres -d edu_chat
```

## Docker Production

Uses an optimized multi-stage build with no volume mounts and multiple workers.

```bash
# Build and start production services
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

# Stop production services
docker compose -f docker-compose.yml -f docker-compose.prod.yml down
```

## Alembic Migrations

Alembic manages all database schema changes. Tables are **not** auto-created on startup — you must run migrations manually or in your CI pipeline.

### Common Commands

```bash
# Apply all pending migrations
alembic upgrade head

# Apply migrations up to a specific revision
alembic upgrade <revision_id>

# Create a new migration from model changes (auto-generate)
alembic revision --autogenerate -m "description of change"

# Create an empty migration (for manual SQL)
alembic revision -m "description of change"

# Downgrade by one migration
alembic downgrade -1

# Downgrade to a specific revision
alembic downgrade <revision_id>

# Show current migration version
alembic current

# Show migration history
alembic history

# Show pending migrations (not yet applied)
alembic history -r head:1
```

### New Database Setup

When setting up a fresh database (e.g., after `docker compose down -v` or on a new server):

```bash
# Create all tables from scratch
alembic upgrade head
```

### After Model Changes

Whenever you add or modify a SQLAlchemy model in `app/models/`:

1. Make your model changes
2. Generate a migration:
   ```bash
   alembic revision --autogenerate -m "add description field to users"
   ```
3. Review the generated migration in `alembic/versions/`
4. Apply the migration:
   ```bash
   alembic upgrade head
   ```

### In Docker

Prefix any alembic command with `docker compose exec app`:

```bash
docker compose exec app alembic upgrade head
docker compose exec app alembic revision --autogenerate -m "description"
docker compose exec app alembic downgrade -1
```

## Tunneling (Public URL)

To expose your local server on a live domain, set `TUNNEL=true` in `.env`:

```bash
TUNNEL=true uv run serve
```

This requires `cloudflared`. Install it with:

**macOS:**
```bash
brew install cloudflared
```

**Linux:**
```bash
# Debian/Ubuntu
curl -fsSL https://pkg.cloudflare.com/cloudflared-stable-linux-amd64.deb -o cloudflared.deb
sudo dpkg -i cloudflared.deb && rm cloudflared.deb
```

**Windows:**
```powershell
winget install Cloudflare.cloudflared
```

No Cloudflare account needed — the free quick tunnel gives you a random `*.trycloudflare.com` URL printed on startup.

## Debug Endpoints

When `DEBUG=true` is set in `.env`:

- `GET /auth/gen-token` — Returns access & refresh tokens for a test user (`test@local.dev`)
- `GET /auth/gen-google-auth` — Starts Google OAuth flow to obtain an ID token for testing `/auth/login`