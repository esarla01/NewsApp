from time import monotonic

from app.clients.guardian import GuardianArticle, GuardianClient

CACHE_TTL_SECONDS = 600

# (query, section) -> (time stored, results). In memory is enough at this scale.
_cache: dict[tuple[str, str | None], tuple[float, list[GuardianArticle]]] = {}


def search_articles(
    client: GuardianClient, query: str, section: str | None = None
) -> list[GuardianArticle]:
    # Only whitespace is normalised: the Guardian treats upper-case AND/OR/NOT as operators.
    query = " ".join(query.split())
    section = section.strip().lower() if section and section.strip() else None
    key = (query, section)

    # Check the cache first
    # If the cached results are not expired (within the TTL - 600 seconds), return the cached results. 
    # Otherwise, perform a new search and update the cache.
    cached = _cache.get(key)
    if cached and monotonic() - cached[0] < CACHE_TTL_SECONDS:
        return cached[1]

    results = client.search(query, section)
    _cache[key] = (monotonic(), results)
    return results
