# uod-backend

> Instance store & API for the [Universal Ontology Definition](https://github.com/ramphias/universal-ontology-definition) project.

This service owns the **private, queryable instance store**. The class definitions (L0/L1/L2/L3 schema) stay in the public ontology repo; this backend stores the millions of harvested instances and exposes them to Studio and to internal services.

## Architecture

See [`data-architecture.md`](https://github.com/ramphias/universal-ontology-definition/blob/master/docs-site/architecture/data-architecture.md) in the main repo for the full two-tier model.

```
GitHub (universal-ontology-definition)        ← schema + ≤ 5/class demo instances
  ↓ reads class definitions
uod-backend  (this repo)                       ← FastAPI + SQLAlchemy
  ↕
Neon Postgres                                  ← instances, instance_relations, audit_log, harvest_jobs
```

## Stack

| Layer | Tool |
|---|---|
| Language | Python 3.12 |
| Package manager | [`uv`](https://docs.astral.sh/uv/) |
| Web framework | FastAPI |
| DB driver | `asyncpg` |
| ORM | SQLAlchemy 2.0 (async) |
| Migrations | Alembic |
| Validation | Pydantic v2 |
| Auth | NextAuth-compatible JWT (HS256 for now; JWE in Phase A.3) |
| Tests | pytest + testcontainers-postgres |
| Lint / format | ruff |
| Container | Multi-stage Dockerfile |
| Deploy | Fly.io |

## Local development

Requires Python 3.12 and either Docker (for testcontainers) or a running Postgres.

```bash
# 1. Install deps
uv sync

# 2. Start Postgres (choose one)
docker run --rm -d --name uod-pg -p 5432:5432 -e POSTGRES_PASSWORD=dev postgres:16
# ...or use Neon, or a system Postgres

# 3. Configure env
cp .env.example .env
# edit .env: set DATABASE_URL and NEXTAUTH_SECRET (≥ 32 random bytes)

# 4. Run migrations
uv run alembic upgrade head

# 5. Start the API
uv run uvicorn app.main:app --reload
# → http://localhost:8000/docs
```

## Run tests

```bash
uv run pytest               # requires Docker for testcontainers-postgres
uv run pytest -v -k auth    # subset
uv run ruff check .         # lint
uv run ruff format --check  # format check
```

Tests skip automatically if Docker is unavailable.

## API overview

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/` | public | metadata + docs link |
| GET | `/health` | public | liveness + DB ping |
| GET | `/docs` | public | OpenAPI UI |
| GET | `/instances` | viewer+ | list + filter + search |
| GET | `/instances/{id}` | viewer+ | get one |
| POST | `/instances` | editor+ | create candidate |
| PATCH | `/instances/{id}` | editor+ | partial update |
| DELETE | `/instances/{id}` | admin | hard delete (logged) |
| POST | `/instances/{id}/verify` | admin | accept candidate |
| POST | `/instances/{id}/reject` | admin | reject with reason |

All writes append a row to `audit_log` (action, actor, before, after, timestamp).

## Database schema

Tables created by `alembic/versions/001_initial.py`:

- `instances` — entity rows with provenance (`source`, `source_url`, `confidence`, etc.)
- `instance_relations` — typed edges (`source_id`, `relation_id`, `target_id`)
- `audit_log` — append-only history of every write
- `harvest_jobs` — one row per harvester run

## Deployment

### One-time setup

1. Sign up for [Neon](https://neon.tech) — free tier covers a 0.5 GB DB. Grab the connection URL, rewrite scheme to `postgresql+asyncpg://`.
2. Sign up for [Fly.io](https://fly.io). Install `flyctl`.
3. `flyctl auth login`
4. `flyctl launch --copy-config --no-deploy` (creates the app from `fly.toml`)
5. `flyctl secrets set DATABASE_URL='postgresql+asyncpg://...' NEXTAUTH_SECRET='...'`
6. In GitHub repo settings, add `FLY_API_TOKEN` secret (`flyctl tokens create deploy`).

### Subsequent deploys

Every push to `main` triggers `.github/workflows/deploy.yml`, which:

1. Builds the Docker image (multi-stage, Python 3.12 slim).
2. Pushes to Fly's registry.
3. Runs `alembic upgrade head` as the release command.
4. Starts new machines, drains old ones.

## Auth model

The backend trusts JWTs signed with `NEXTAUTH_SECRET` — the **same secret** as the Studio Next.js app. This lets a user sign into Studio via GitHub OAuth and have the same session work against this API.

Token payload expected:

```json
{
  "login": "octocat",
  "role":  "viewer" | "editor" | "admin",
  "iat":   1700000000,
  "exp":   1700003600
}
```

Phase A.2 (this scaffold) uses HS256 JWS. Phase A.3 will upgrade to NextAuth's JWE format (`A256GCM`) so Studio cookies work without a token-exchange step.

## License

Apache 2.0 — same as the main project.
