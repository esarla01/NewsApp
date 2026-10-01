# Aries News

Search recent Guardian articles, get an AI summary and sentiment for any of them, and browse every analysis stored so far.

**Live app:** https://newsapp-production-f342.up.railway.app

## Features

- **Search** recent news by keyword, optionally within a section (World, Politics, Technology and so on). Results are newest first and exclude live blogs.
- **Analyse** any result with one click. OpenAI (`gpt-4.1-nano`) returns a short summary, a sentiment (positive, neutral or negative) and a one-sentence rationale. The button shows a loading state until the result replaces it.
- **No duplicate work.** Each analysis is stored. Analysing the same article again returns the stored result without calling OpenAI, and search results show existing analyses straight away.
- **History** of every analysed article, filterable by sentiment and keyword. It refreshes by itself after each new analysis.

## Tech stack

| Area | Choice |
| --- | --- |
| Backend | Python 3.13, FastAPI, SQLAlchemy 2, Alembic |
| Database | PostgreSQL 16 |
| External APIs | Guardian Open Platform (via `httpx`), OpenAI Responses API |
| Frontend | Jinja2 templates, htmx, Pico.css (no build step) |
| Tooling | uv, pytest, ruff |
| Hosting | Railway (app + Postgres) |

## Running locally

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
cp .env.example .env          # then add your Guardian and OpenAI keys
uv sync
uv run alembic upgrade head   # create the tables
uv run uvicorn app.main:app --reload
```

The app runs at http://localhost:8000, and interactive API docs are at http://localhost:8000/docs.

## Tests

```bash
uv run pytest
uv run ruff check .
```

Tests run against a real Postgres database (`TEST_DATABASE_URL`), rebuilt from the migrations at the start of each run, so they also check that the migrations work. The Guardian and OpenAI are replaced with fakes, so tests run offline and use no API quota.

## Project structure

```
app/
├── main.py              FastAPI app, routers and error handlers
├── config.py            settings from environment variables
├── db.py                database engine and session
├── models.py            Article and Analysis tables
├── schemas.py           JSON shapes returned by the API
├── dependencies.py      shared Guardian and OpenAI clients
├── clients/             all communication with external APIs
│   ├── guardian.py
│   └── openai_client.py
├── services/            business logic, shared by the API and the web pages
│   ├── search.py        Guardian search, caching, attaching stored analyses
│   └── analysis.py      analysing an article, listing analyses
├── routers/
│   ├── api.py           JSON API under /api
│   └── pages.py         HTML page and htmx partials
└── templates/           Jinja2 templates
alembic/                 database migrations
tests/
```

Requests flow in one direction: **routers** handle HTTP, **services** hold the logic, and **clients** are the only code that talks to the Guardian or OpenAI. The JSON API and the web pages call the same services, so no logic is duplicated.

## API

| Method | Endpoint | Description |
| --- | --- | --- |
| `GET` | `/api/articles/search?q=&section=` | Search the Guardian. Each result includes its stored analysis, or `null`. |
| `POST` | `/api/analyses` | Analyse an article by `guardian_id`. Returns `201` if new, `200` if it already existed. |
| `GET` | `/api/analyses?sentiment=&q=` | Stored analyses, newest first, filterable by sentiment and keyword. |
| `GET` | `/api/analyses/{id}` | One stored analysis. |

Every endpoint returns the same shape, an article with its analysis:

```bash
curl -X POST localhost:8000/api/analyses \
  -H "Content-Type: application/json" \
  -d '{"guardian_id": "world/2026/oct/01/example-article"}'
```

```json
{
  "article": {
    "guardian_id": "world/2026/oct/01/example-article",
    "web_url": "https://www.theguardian.com/world/2026/oct/01/example-article",
    "headline": "...",
    "standfirst": "...",
    "section_name": "World news",
    "byline": "...",
    "thumbnail_url": "...",
    "published_at": "2026-10-01T09:00:00Z"
  },
  "analysis": {
    "id": 1,
    "summary": "...",
    "sentiment": "neutral",
    "rationale": "...",
    "model": "gpt-4.1-nano",
    "created_at": "2026-10-01T10:15:00Z"
  }
}
```

Errors return `{"detail": "..."}`: `422` for invalid input, `404` for an unknown article, `429` when the Guardian rate limit is reached, and `502` when the Guardian or OpenAI fails.

## How an analysis works

1. Look for an existing analysis of the article. If there is one, return it.
2. End the read transaction, so no database connection is held during the slow API calls.
3. Fetch the full article text from the Guardian.
4. Send the headline and text to OpenAI, which must reply in a fixed JSON schema (validated with Pydantic).
5. Save the article and its analysis together in one short transaction.

If two requests analyse the same article at the same time, the unique constraint on `guardian_id` rejects the second insert, and that request returns the analysis the first one saved. If the Guardian or OpenAI fails, nothing has been saved, so the user can simply try again.

## Design decisions

- **Articles are stored only once analysed.** Articles and analyses are separate tables, and the database never contains half-finished records. Analyses live in their own table so re-analysis or other models could be added later by dropping one unique constraint.
- **Idempotency is enforced by the database**, through unique constraints on `articles.guardian_id` and `analyses.article_id`, not just by application checks.
- **Search fetches only what the cards need.** The full text is fetched only when an article is analysed, which keeps searches small and fast.
- **Guardian search results are cached in memory for 10 minutes**, keyed by query and section. Stored analyses are attached from the database on every request, so a cached result never shows an outdated status.
- **Article text is truncated to 12,000 characters** before it is sent to OpenAI, to keep latency and cost predictable.
- **Synchronous endpoints.** FastAPI runs each request in its thread pool, so a slow OpenAI call does not block other users. At this scale that is simpler than async and behaves the same.
- **Server-rendered HTML with htmx** instead of a JavaScript framework. There is one deployable with no build step, and the pages reuse the same services as the API. Errors are shown inside the page rather than as failed requests.
- **Migrations run as a Railway pre-deploy step.** If a migration fails, the deploy stops and the previous version keeps running.

## Limitations and next steps

- **Analysis happens inside the request**, which takes around 4 to 5 seconds. At higher traffic this would move to a background job queue, with the UI polling for the result.
- **The cache is per process.** Running several instances would call for a shared cache such as Redis. Old cache entries are replaced but never removed, which is fine at this scale.
- **Search shows the first 10 results only.** Pagination would be a small addition to the client and the page.
- **There is no authentication or rate limiting on this app's own endpoints**, so anyone with the link can trigger OpenAI calls. A public version would need per-user limits.
- **AI query understanding** (turning a question such as "good news about renewable energy this week" into structured Guardian search parameters) would plug into the existing search service: every search already goes through it, so only its parameters would need extending.

## Deployment (Railway)

Deploy settings live in `railway.json`: a pre-deploy step runs `alembic upgrade head`, then uvicorn starts the app, and Railway health-checks `/health`.

Service variables:

| Variable | Value |
| --- | --- |
| `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` (reference to the Railway Postgres service) |
| `GUARDIAN_API_KEY` | Guardian Open Platform key |
| `OPENAI_API_KEY` | OpenAI key |
