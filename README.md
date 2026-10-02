# Aries News

Search recent Guardian articles, get an AI summary and sentiment for any of them, and browse every analysis stored so far.

**Live app:** https://newsapp-production-f342.up.railway.app

## Features

- **Search** recent news by keyword, with optional section, date range and sort order. Live blogs are excluded.
- **Smart search (AI).** Ask in plain English, such as "good news about renewable energy this week", and the page shows how the question was understood.
- **Analyse** any result with one click. OpenAI (`gpt-4.1-nano`) returns a short summary, a sentiment (positive, neutral or negative) and a one-sentence rationale. The button shows a loading state until the result replaces it.
- **No duplicate work.** Analysing the same article again returns the stored result without calling OpenAI, and search results show existing analyses straight away.
- **Analysed articles** page listing every stored analysis, newest first, filterable by sentiment and keyword as you type.

## Tech stack

| Area | Choice |
| --- | --- |
| Backend | Python 3.13, FastAPI, SQLAlchemy 2, Alembic |
| Database | PostgreSQL 16 |
| External APIs | Guardian Content API (via `httpx`), OpenAI Responses API |
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
│   └── pages.py         HTML pages and htmx partials
└── templates/           Jinja2 templates
alembic/                 database migrations
tests/
```

Requests flow in one direction: **routers** handle HTTP, **services** hold the logic, and **clients** are the only code that talks to the Guardian or OpenAI. The JSON API and the web pages call the same services, so no logic is duplicated.

## How search and analysis work

Search and analysis are kept apart on purpose. Search is fast and free, with no AI involved. Analysis is slow and costs money, so it only runs when the user asks for it on a single article.

| | Search | Analysis |
| --- | --- | --- |
| Triggered by | Submitting the search form | Clicking Analyse on one result |
| Endpoint | `GET /api/articles/search` | `POST /api/analyses` |
| Guardian call | `GET /search`, card fields only | `GET /{guardian_id}`, with the full body text |
| OpenAI call | None (smart search makes one) | One, for the summary and sentiment |
| Database | Read only | Read, then write |
| Service | `search_articles`, `attach_analyses` | `analyse_article` |

### Search

1. The router validates the keyword and filters.
2. `search_articles` checks an in-memory cache, keyed by the query and all of its filters. A result less than 10 minutes old is returned without calling the Guardian.
3. Otherwise it calls the Guardian's `GET /search` with `type=article` (which excludes live blogs) and `page-size=10`. It asks only for the fields the cards need, not the body text, which keeps searches small and fast.
4. `attach_analyses` runs one database query to find which of the results already have a stored analysis. This runs on every request, so a cached search never shows an outdated status.

**Smart search** adds one OpenAI call before step 2. The model must reply in a fixed schema: keywords, a section, a time period (`today`, `this_week`, `this_month` or `any`) and a sort order. Code then checks the section against the known list and turns the time period into a start date. The model picks a period rather than a date because gpt-4.1-nano was unreliable at date arithmetic ("since Monday" came back as the wrong day). If OpenAI fails, the question is searched as plain keywords.

### Analysis

1. Look for an existing analysis of the article. If there is one, return it (`200`) without any external calls.
2. End the read transaction, so no database connection is held during the slow API calls.
3. Fetch the article, including its body text, from the Guardian.
4. Send the headline and the first 12,000 characters of the text to OpenAI, which keeps latency and cost predictable. The reply must match a fixed JSON schema (summary, sentiment, rationale), validated with Pydantic.
5. Save the article and its analysis together in one short transaction and return them (`201`).

If the Guardian or OpenAI fails, nothing has been saved, so the user can simply try again. Duplicates are prevented by the database, not just by step 1: unique constraints on `articles.guardian_id` and `analyses.article_id` mean that if two requests analyse the same article at once, the second insert is rejected and that request returns the analysis the first one saved.

## API

The JSON API lives under `/api` ([app/routers/api.py](app/routers/api.py)). Every endpoint returns results as an `ArticleResult`, an article plus its analysis, where `analysis` is `null` if the article has not been analysed yet:

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

| Method | Endpoint | Returns |
| --- | --- | --- |
| `GET` | `/api/articles/search` | Up to 10 `ArticleResult`s from the Guardian. |
| `GET` | `/api/articles/smart-search` | The interpreted filters and the results. |
| `POST` | `/api/analyses` | One `ArticleResult`: `201` if newly analysed, `200` if it already existed. |
| `GET` | `/api/analyses` | Stored analyses, newest first, up to 50. |
| `GET` | `/api/analyses/{id}` | One stored analysis, by `analysis.id`. |

### `GET /api/articles/search`

| Parameter | Required | Description |
| --- | --- | --- |
| `q` | yes | Search keywords. |
| `section` | no | Guardian section id, such as `world`, `politics` or `technology`. |
| `from_date`, `to_date` | no | Publication date range, `YYYY-MM-DD`. |
| `order_by` | no | `newest` (default) or `relevance`. |

```bash
curl "localhost:8000/api/articles/search?q=climate&section=world&from_date=2026-09-01"
```

### `GET /api/articles/smart-search`

Takes a plain-English question in `q`:

```json
{
  "interpreted": {
    "keywords": "renewable energy",
    "section": "environment",
    "from_date": "2026-09-25",
    "order_by": "newest"
  },
  "results": [ ... ]
}
```

### `POST /api/analyses`

```bash
curl -X POST localhost:8000/api/analyses \
  -H "Content-Type: application/json" \
  -d '{"guardian_id": "world/2026/oct/01/example-article"}'
```

`guardian_id` must look like a Guardian path (lower-case letters, digits, `-` and `_`, separated by `/`), so odd input is rejected before it reaches the Guardian.

### `GET /api/analyses`

| Parameter | Required | Description |
| --- | --- | --- |
| `sentiment` | no | `positive`, `neutral` or `negative`. |
| `q` | no | Keyword matched against the headline and summary. |

### Errors

Errors return `{"detail": "..."}`.

| Status | When |
| --- | --- |
| `404` | The article is not on the Guardian, or the analysis id does not exist. |
| `422` | Invalid input, such as an empty `q`, a malformed date, `from_date` after `to_date`, or a malformed `guardian_id`. |
| `429` | The Guardian rate limit was reached. |
| `502` | The Guardian or OpenAI failed. |

### Web routes

These return HTML ([app/routers/pages.py](app/routers/pages.py)). The `/partials` routes are called by htmx and return a piece of HTML that is swapped into the page without a reload. Their errors are shown inside that HTML rather than as error status codes.

| Method | Route | Returns |
| --- | --- | --- |
| `GET` | `/` | The search page. |
| `GET` | `/history` | The Analysed articles page. |
| `GET` | `/partials/search` | The results list. Takes the same filters as the JSON search, plus `smart`. |
| `POST` | `/partials/analyse` | The analysis box for one result. Takes `guardian_id` as form data. |
| `GET` | `/partials/history` | The filtered analyses list. Takes `q` and `sentiment`. |
| `GET` | `/health` | `{"status": "ok"}` if the database is reachable. |

## Design decisions

- **Articles are stored only once analysed.** The database never contains half-finished records. Analyses live in their own table, so re-analysis or other models could be added later by dropping one unique constraint.
- **Synchronous endpoints.** FastAPI runs each request in its thread pool, so a slow OpenAI call does not block other users. At this scale that is simpler than async and behaves the same.
- **Server-rendered HTML with htmx** instead of a JavaScript framework. There is one deployable with no build step, and the pages reuse the same services as the API.
- **Migrations run as a Railway pre-deploy step.** If a migration fails, the deploy stops and the previous version keeps running.

## Limitations and next steps

- **Analysis happens inside the request**, which takes around 4 to 5 seconds. At higher traffic this would move to a background job queue, with the UI polling for the result.
- **The cache is per process.** Running several instances would call for a shared cache such as Redis. Old cache entries are replaced but never removed, which is fine at this scale.
- **Search shows the first 10 results only.** Pagination would be a small addition to the client and the page.
- **There is no authentication or rate limiting on this app's own endpoints**, so anyone with the link can trigger OpenAI calls. A public version would need per-user limits.

## Deployment (Railway)

Deploy settings live in `railway.json`: a pre-deploy step runs `alembic upgrade head`, then uvicorn starts the app, and Railway health-checks `/health`.

Service variables:

| Variable | Value |
| --- | --- |
| `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` (reference to the Railway Postgres service) |
| `GUARDIAN_API_KEY` | Guardian Open Platform key |
| `OPENAI_API_KEY` | OpenAI key |
