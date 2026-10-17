# disruption-api

Small REST API to track flight disruptions (delays, cancellations, diversions) the way an
airline operations control centre would. **All data is synthetic.** Built as a backend practice
project: Flask, SQLAlchemy 2.0, PostgreSQL, Alembic, Pydantic v2, Celery/Redis, pytest, Docker, CI.

## What it does

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | liveness check |
| POST | `/airports` | register an airport (`iata`, `name`, `is_hub`) |
| POST | `/flights` | create a flight (validated with Pydantic) |
| GET | `/flights/<id>` | read a flight |
| POST | `/disruptions` | record a disruption; returns `202` and queues the impact calculation |
| GET | `/disruptions?status=&kind=&limit=&offset=` | list and filter, paginated (`limit` 1-200, default 50); returns `{items, total, limit, offset}` |
| GET | `/disruptions/<id>` | read one |
| PATCH | `/disruptions/<id>/resolve` | mark as resolved |
| POST | `/disruptions/<id>/actions` | log a recovery action (rebooking, crew swap...) |
| GET | `/stats/delays` | median and p90 delay per origin airport (pandas) |

All endpoints except `/health` require an `X-API-Key` header (`401` otherwise). Only SHA-256 hashes of
the keys are configured, in `API_KEY_HASHES`. Create one with `python -m disruption_api.auth`.

Errors are JSON: `422` for invalid input, `404` for missing resources, `409` for conflicts.

## How the pieces fit

- `disruption_api/models.py`: SQLAlchemy models with constraints and indexes.
- `disruption_api/schemas.py`: Pydantic models for input and output.
- `disruption_api/routes.py`: Flask blueprint, one session per request.
- `disruption_api/services.py`: business logic (impact estimate, statistics), no HTTP.
- `disruption_api/tasks.py`: Celery task that fills `affected_connections` and `impact_score` after the request returns.
- `migrations/`: Alembic migrations (`0001` airports/flights, `0002` disruptions, `0003` impact columns + index).

## Run it

```bash
cp .env.example .env
docker compose up --build
docker compose exec api alembic upgrade head
curl localhost:8000/health
```

## Develop and test

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt pytest pytest-cov ruff mypy pandas-stubs
ruff check . && ruff format --check . && mypy && pytest
```

Tests use in-memory SQLite and a mocked Celery `.delay`, so they need no services. A separate
test runs the real Alembic migrations up and down. CI also applies the migrations to a real
PostgreSQL service and builds the Docker image.

## Configuration

Everything comes from environment variables (`DATABASE_URL`, `CELERY_BROKER_URL`,
`CELERY_RESULT_BACKEND`); see `.env.example`. No secrets are committed.

## Limits

The impact estimate uses simple, documented assumptions (share of connecting passengers, severity
by type and delay) and is not a real operations model. Authentication is a static API key per client, with no roles or rate limiting.
