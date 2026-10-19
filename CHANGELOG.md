# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

## [0.1.0] - 2026-10-19

First release.

### Added
- REST API for airports, flights, disruptions (delay, cancellation, diversion) and recovery actions, with
  Pydantic v2 validation and consistent JSON errors (422, 404, 409).
- SQLAlchemy 2.0 models on PostgreSQL, versioned with Alembic migrations `0001` to `0004`.
- Background impact estimation with Celery and Redis; `POST /disruptions` answers `202`.
- Pagination and filters on `GET /disruptions` (`limit`, `offset`, `status`, `kind`) returning `{items, total, limit, offset}`.
- API key authentication through the `X-API-Key` header; only SHA-256 hashes are configured, compared in constant time.
- Aircraft rotations: flights can carry a `tail_number` and `scheduled_arrival`; a delay propagates to the later
  flights of the same aircraft as knock-on disruptions, readable at `GET /disruptions/<id>/cascade`.
- Delay statistics per origin airport (median and p90) at `GET /stats/delays`.
- `GET /health` and `GET /health/ready` (database check), both public.
- OpenAPI 3 spec at `/openapi.json` and Swagger UI at `/docs`, with a test that keeps them in sync with the routes.
- Dockerfile and `docker-compose.yml` (API, worker, PostgreSQL, Redis).
- GitHub Actions: lint (ruff), strict typing (mypy), migrations applied up, down and up on PostgreSQL, tests on
  SQLite and PostgreSQL, Docker build, and an end-to-end job that runs the compose stack.
