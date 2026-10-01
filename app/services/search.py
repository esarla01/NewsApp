from time import monotonic

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.clients.guardian import GuardianArticle, GuardianClient
from app.models import Analysis, Article
from app.schemas import AnalysisOut, ArticleResult

CACHE_TTL_SECONDS = 600

# (query, section) -> (time stored, results). In memory is enough at this scale.
_cache: dict[tuple[str, str | None], tuple[float, list[GuardianArticle]]] = {}


# Search the Guardian API for articles matching the query and section, using a cache to avoid repeated searches.
def search_articles(
    client: GuardianClient, query: str, section: str | None = None
) -> list[GuardianArticle]:

    # Only whitespace is normalised: the Guardian treats upper-case AND/OR/NOT as operators.
    query = " ".join(query.split())
    section = section.strip().lower() if section and section.strip() else None
    key = (query, section)

    #  Check the cache first. If the cached results are not expired (within the TTL),
    #  return the cached results. Otherwise, perform a new search and update the cache.
    cached = _cache.get(key)
    if cached and monotonic() - cached[0] < CACHE_TTL_SECONDS:
        return cached[1]

    results = client.search(query, section)
    _cache[key] = (monotonic(), results)
    return results


# Pair each article with its stored analysis, or None, using a single query.
def attach_analyses(session: Session, articles: list[GuardianArticle]) -> list[ArticleResult]:

    guardian_ids = [article.guardian_id for article in articles]

    # One query for the whole page: (guardian_id, Analysis) for every analysed article.
    rows = session.execute(
        select(Article.guardian_id, Analysis)
        .join(Analysis.article)
        .where(Article.guardian_id.in_(guardian_ids))
    )
    analysis_by_guardian_id = {guardian_id: analysis for guardian_id, analysis in rows}

    results = []
    for article in articles:
        analysis = analysis_by_guardian_id.get(article.guardian_id)
        results.append(
            ArticleResult(
                article=article,
                analysis=AnalysisOut.model_validate(analysis) if analysis else None,
            )
        )
    return results
