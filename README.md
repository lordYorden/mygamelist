# MyGameList

MyGameList is a React + FastAPI + PostgreSQL application. The current slice implements secure authentication with a Backend for Frontend pattern:

- Browser talks to the BFF.
- BFF stores the backend JWT server-side and sets `BFF-SESSION` as an `HttpOnly` cookie.
- Backend API remains stateless and accepts JWT Bearer tokens.
- Passwords are stored as salted Argon2i hashes.
- PostgreSQL and JWT secrets are loaded from LocalStack Secrets Manager in Docker.

## Run With Docker

```bash
docker compose up --build
```

- BFF + React app: http://localhost:8080
- Backend API: http://localhost:8000
- PostgreSQL: localhost:5432
- LocalStack: http://localhost:4566

Local development uses LocalStack secrets seeded from `localstack/init/`:

- `mygamelist/db`
- `mygamelist/db-docker`
- `mygamelist/jwt`

The API container reads `DB_SECRET_NAME` and `JWT_SECRET_NAME` and refuses to start if the configured secrets cannot be loaded.

## Local Tests

```bash
pip install -r api/requirements.txt
pytest api/tests

pip install -r bff/requirements.txt
pytest bff/tests
```
