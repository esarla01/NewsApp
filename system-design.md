#  Aries \- Engineering Case Study

## Requirements

### Functional:

1. Search recent news by keyword  
2. Select an article and request an AI summary \+ sentiment (positive / neutral / negative)  
3. Persist the results  
4. Display all stored results and their analysis.

### Non-functional: 

1. User experience: UI should have a loading state for OpenAI calls.  
2. Security: API keys must be hidden in the environment variables and not in the repo.  
3. Idempotency: Analysing the same article twice shouldn't create duplicates or waste API calls.  
4. Low traffic: Only a few reviewers will engage with the application.   
5. External rate limits: Guardian Open Platform free developer tier allows at least 500 requests/day. 

## Core entities

1. Articles:  
- id  
- guardian\_id (unique)  
- web\_url  
- headline  
- standfirst  
- body\_text  
- section\_name  
- byline  
- thumbnail\_url  
- published\_at  
- created\_at


2. Analyses:  
- id  
- article\_id (FK, unique)  
- summary  
- sentiment (enum)  
- rationale  
- model  
- created\_at

Justification:

1. Articles and analyses are kept in separate tables because an article's content does not change, while its analysis could. Re-analysis or analyses from other models could be added later by removing the unique constraint, without changing the articles table. Articles are only stored once they have been analysed, so every stored article has an analysis.  
2. There should be one analysis per article and therefore “article id” in the analysis table is unique.

### API Design

| Method | Endpoint | Purpose |
| :---- | :---- | :---- |
| GET | /api/articles/search?q=\&section= | Search the Guardian. Each result includes its stored analysis, or null if it has not been analysed yet. |
| POST | /api/analyses | Analyse an article by guardian\_id. Returns the existing analysis (200) if there is one, otherwise calls OpenAI and stores the article and analysis together (201). |
| GET | /api/analyses?sentiment=\&q= | List stored analyses with their articles, filterable by sentiment and keyword. |
| GET | /api/analyses/{id} | One analysis with its article (optional detail view). |

### User flow

1. **Landing page:** Search bar with an optional section filter, plus a list of recently analysed articles loaded from the database.  
2. **Search:** The client calls GET /api/articles/search. The server fetches results from the Guardian and attaches any existing analyses with a single database query.  
3. **Results:** Each card shows headline, standfirst, section, date and thumbnail. Unanalysed articles show an Analyse button; analysed ones show the sentiment badge and summary directly.  
4. **Analyse:** The client calls POST /api/analyses with the guardian\_id. The button shows a loading state and stays disabled until the response arrives, then the result replaces it on the card.  
5. **History:** GET /api/analyses lists all stored analyses, filterable by sentiment and keyword.

### Analysis request sequence

1. Check the database for an existing analysis and return it if found (200).  
2. Fetch the article from the Guardian, or from the search cache.  
3. Call OpenAI and validate the response. No database transaction is open during this call.  
4. Open a short transaction, insert the article and the analysis together, and return 201\.  
5. If two requests for the same article overlap, the unique constraint on guardian\_id rejects the second insert and the existing analysis is returned.  
   

**Justification** for storing on analysis:

1. The database stays consistent. Every stored article has an analysis. It doesn't deal with half-finished records.  
2. Failures don’t leave anything behind. If OpenAI times out, it just returns an error and the user only has to click Analyse again to re-initiate it.  
3. The database is succinct. Only successfully analysed articles are inserted. Articles that already have an analysis are returned from the database and not sent to OpenAI again.

## Design Details

1. The OpenAI call should return a JSON that strictly matches a fixed schema. Validate it with Pydantic.  
2. Cache raw Guardian results in memory for 10 minutes, keyed by normalised query and section, to avoid repeated calls for the same search. Analyses are attached from the database on every request, so cached results never show an outdated status. In-memory caching is sufficient at this scale.  
3. Guardian searches default to order-by=newest and type=article, so results are recent and liveblogs are excluded.  
4. Article body text is truncated before it is sent to OpenAI, to keep latency and cost predictable.  
5. Errors: Guardian or OpenAI failures return 502, a Guardian rate limit returns 429 and an unknown guardian\_id returns 404\. Nothing is saved when an analysis fails, so the user can retry.  
6. The OpenAI call completes within the POST request while the UI shows a loading state. Endpoints use async clients so one slow call does not block other users. A background job queue would be the next step at higher scale.

## Stretch goals

1. **AI query understanding:** One OpenAI call converts a natural-language question into structured Guardian search parameters (keywords, section, date range, ordering). The output is validated against known values, falls back to a plain keyword search if it fails, and the interpreted query is shown to the user. The search service accepts structured parameters from the start, so this plugs in without other changes.  
2. **Agentic search:** The model is given tools to search the Guardian and read articles, refines its query over several steps, and selects the most relevant articles or writes a short briefing. Kept as future work because it adds latency and cost, is less reliable on gpt-4.1-nano, and is harder to modify by hand.

## Changes during implementation

1. **Synchronous instead of async.** Endpoints are plain functions that FastAPI runs in its thread pool, with sync database and API clients. At this traffic it behaves the same as async and is simpler to read and debug.  
2. **One path for the article text.** Searches request only the fields the cards need, and the full text is fetched from the Guardian only when an article is analysed. This replaces “from the Guardian, or from the search cache”, which would have made every search fetch full article bodies.  
3. **The read transaction is ended before the API calls.** The existing-analysis check opens a database transaction, so it is explicitly closed before the Guardian and OpenAI calls. That keeps the rule that no transaction is open during the OpenAI call.  
4. **The stretch goal needs the search service extended.** It currently accepts a keyword and a section. Query understanding would add date range and ordering to it, which is still the only place that would need to change.