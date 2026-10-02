from datetime import date, timedelta
from time import monotonic

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.clients.guardian import SECTIONS, GuardianArticle, GuardianClient, OrderBy
from app.clients.openai_client import AnalysisError, OpenAIClient
from app.models import Analysis, Article
from app.schemas import ArticleResult, InterpretedSearch, to_result

CACHE_TTL_SECONDS = 600

# How far back each time period the AI can choose reaches.
TIME_PERIOD_DAYS = {"today": 0, "this_week": 7, "this_month": 30}

# (query, section, from_date, to_date, order_by) -> (time stored, results).
# In memory is enough at this scale.
_cache: dict[tuple, tuple[float, list[GuardianArticle]]] = {}


# Search the Guardian API for articles matching the query and section, using a cache to
# avoid repeated searches.
def search_articles(
    client: GuardianClient,
    query: str,
    section: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    order_by: OrderBy = "newest",
) -> list[GuardianArticle]:

    # Only whitespace is normalised: the Guardian treats upper-case AND/OR/NOT as operators.
    query = " ".join(query.split())
    section = section.strip().lower() if section and section.strip() else None
    key = (query, section, from_date, to_date, order_by)

    #  Check the cache first. If the cached results are not expired (within the TTL),
    #  return the cached results. Otherwise, perform a new search and update the cache.
    cached = _cache.get(key)
    if cached and monotonic() - cached[0] < CACHE_TTL_SECONDS:
        return cached[1]

    results = client.search(query, section, from_date, to_date, order_by)
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
        results.append(to_result(article, analysis))
    return results


def interpret_question(openai: OpenAIClient, question: str, today: date) -> InterpretedSearch:
    """Turn a plain-English question into search filters.

    Anything the AI returns that we can't use is dropped, and if OpenAI fails the
    question is searched as plain keywords.
    """
    try:
        answer = openai.interpret_question(question)
    except AnalysisError:
        return InterpretedSearch(keywords=question, section=None, from_date=None, order_by="newest")

    days = TIME_PERIOD_DAYS.get(answer.time_period)
    return InterpretedSearch(
        keywords=answer.keywords.strip() or question,
        section=answer.section if answer.section in SECTIONS else None,
        from_date=today - timedelta(days=days) if days is not None else None,
        order_by=answer.order_by,
    )
