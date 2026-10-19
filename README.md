# disruption-api

[![CI](https://github.com/1lauraog15-cloud/disruption-api/actions/workflows/ci.yml/badge.svg)](https://github.com/1lauraog15-cloud/disruption-api/actions/workflows/ci.yml)

REST API to track flight disruptions (delays, cancellations, diversions) the way an airline
operations control centre would. **All data is synthetic.** It is a backend practice project:
Flask, SQLAlchemy 2.0, PostgreSQL, Alembic, Pydantic v2, Celery/Redis, pytest, Docker and GitHub Actions.

Interactive documentation is served at `/docs` (Swagger UI) from the machine-readable spec at `/openapi.json`.

## Architecture

```mermaid
flowchart LR
    Client -->|"X-API-Key"| API["Flask API<br/>(Pydantic validation)"]
    API -->|SQLAlchemy| DB[("PostgreSQL")]
    API -->|"enqueue impact task"| Redis[("Redis")]
    Redis --> Worker["Celery worker"]
    Worker -->|"write impact"| DB
    Alembic["Alembic migrations"] -.-> DB
```

1. A client records a disruption with `POST /disruptions`. The API validates it, stores it and answers `202`.
2. A Celery task estimates the impact (affected connections and a score) and writes it back to the row.
3. Clients read the result with `GET /disruptions/<id>`, and see aggregated delays at `/stats/delays`.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | liveness (public) |
| GET | `/health/ready` | readiness: `200` if the database answers, `503` otherwise (public) |
| GET | `/docs`, `/openapi.json` | Swagger UI and OpenAPI spec (public) |
| POST | `/airports` | register an airport (`iata`, `name`, `is_hub`) |
| POST | `/flights` | create a flight |
| GET | `/flights/<id>` | read a flight |
| POST | `/disruptions` | record a disruption; returns `202` and queues the impact calculation |
| GET | `/disruptions?status=&kind=&limit=&offset=` | list, filter and paginate (`limit` 1-200, default 50); returns `{items, total, limit, offset}` |
| GET | `/disruptions/<id>` | read one |
| PATCH | `/disruptions/<id>/resolve` | mark as resolved |
| POST | `/disruptions/<id>/actions` | log a recovery action (rebooking, crew swap...) |
| GET | `/stats/delays` | median and p90 delay per origin airport (pandas) |

Everything except the public endpoints requires an `X-API-Key` header (`401` otherwise). Only SHA-256
hashes of keys are configured, in `API_KEY_HASHES`. Other errors are JSON: `422` invalid input, `404` missing
resource, `409` conflict, `503` database unavailable.

## Quick start

```bash
cp .env.example .env
python -m disruption_api.auth      # prints a new key and its hash
# put the hash in API_KEY_HASHES (in .env), then:
docker compose up --build
docker compose exec api alembic upgrade head
```

```bash
KEY=<the key printed above>
curl -s -H "X-API-Key: $KEY" -X POST localhost:8000/airports \
  -H 'Content-Type: application/json' -d '{"iata":"BCN","name":"Barcelona"}'
curl -s -H "X-API-Key: $KEY" -X POST localhost:8000/airports \
  -H 'Content-Type: application/json' -d '{"iata":"MAD","name":"Madrid","is_hub":true}'
curl -s -H "X-API-Key: $KEY" -X POST localhost:8000/flights \
  -H 'Content-Type: application/json' \
  -d '{"number":"XY123","origin":"BCN","destination":"MAD","scheduled_departure":"2026-11-01T08:30:00+00:00","passengers":180}'
curl -s -H "X-API-Key: $KEY" -X POST localhost:8000/disruptions \
  -H 'Content-Type: application/json' \
  -d '{"flight_id":1,"kind":"delay","delay_minutes":90,"reason":"weather"}'
curl -s -H "X-API-Key: $KEY" "localhost:8000/disruptions?status=open&limit=10"
```

## Project layout

- `disruption_api/models.py`: SQLAlchemy models with constraints and indexes.
- `disruption_api/schemas.py`: Pydantic models for input and output.
- `disruption_api/routes.py`: Flask blueprint, one database session per request.
- `disruption_api/services.py`: business logic (impact estimate, statistics), no HTTP.
- `disruption_api/tasks.py`: Celery task that fills `affected_connections` and `impact_score`.
- `disruption_api/auth.py`: API key hashing and constant-time verification.
- `disruption_api/openapi.py`: OpenAPI spec and Swagger UI.
- `migrations/`: Alembic migrations (`0001` airports/flights, `0002` disruptions, `0003` impact columns and index).

## Develop and test

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt pytest pytest-cov ruff mypy pandas-stubs
ruff check . && ruff format --check . && mypy && pytest
```

By default tests use in-memory SQLite and a mocked Celery `.delay`, so they need no services. Set
`TEST_DATABASE_URL` to run the same suite on PostgreSQL. CI runs both, applies the migrations up, down and up
again on PostgreSQL, checks that the OpenAPI spec lists exactly the routes the app serves, and builds the
Docker image.

## Configuration

Everything comes from environment variables (`DATABASE_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`,
`API_KEY_HASHES`); see `.env.example`. No secrets are committed.

## Limits

The impact estimate uses simple, documented assumptions (share of connecting passengers, severity by type and
delay) and is not a real operations model. Authentication is one static key per client, with no roles or rate
limiting.
