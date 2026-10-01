# Aries News

Search recent Guardian articles, get an AI summary and sentiment for any article, and browse every stored analysis.

Stack: FastAPI, SQLAlchemy, PostgreSQL, Jinja2 + htmx, OpenAI `gpt-4.1-nano`.

## Local setup

Requirements: [uv](https://docs.astral.sh/uv/) and [Homebrew](https://brew.sh/).

PostgreSQL 16 matches the version used on Railway:

```bash
brew install postgresql@16
brew services start postgresql@16
export PATH="$(brew --prefix postgresql@16)/bin:$PATH"   # postgresql@16 is keg-only

createdb newsapp          # development
createdb newsapp_test     # tests
```

Then run the app:

```bash
cp .env.example .env      # then add your Guardian and OpenAI keys
uv sync
uv run alembic upgrade head   # create the tables
uv run uvicorn app.main:app --reload
```

The app runs at http://localhost:8000.

## Tests

```bash
uv run pytest
uv run ruff check .
```

Tests use `TEST_DATABASE_URL`, so they never touch development data.
