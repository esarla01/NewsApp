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


def search_articles(
    client: GuardianClient,
    query: str,
    section: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    order_by: OrderBy = "newest",
) -> list[GuardianArticle]:
    """Search the Guardian, serving repeat searches from a 10-minute cache."""
    # Only whitespace is normalised: the Guardian treats upper-case AND/OR/NOT as operators.
    query = " ".join(query.split())
    section = section.strip().lower() if section and section.strip() else None
    key = (query, section, from_date, to_date, order_by)

    cached = _cache.get(key)
    if cached and monotonic() - cached[0] < CACHE_TTL_SECONDS:
        return cached[1]

    results = client.search(query, section, from_date, to_date, order_by)
    _cache[key] = (monotonic(), results)
    return results


def attach_analyses(session: Session, articles: list[GuardianArticle]) -> list[ArticleResult]:
    """Pair each article with its stored analysis, or None.

    Runs on every request, even for cached searches, so analysis status is never stale.
    """
    guardian_ids = [article.guardian_id for article in articles]

    # A single IN query for the whole page avoids one query per article.
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
    """Turn a plain-English question into validated search filters.

    Unusable values from the model are dropped, and if OpenAI fails the question is
    searched as plain keywords, so smart search degrades to a normal search.
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
