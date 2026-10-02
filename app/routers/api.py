from datetime import date
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response

from app.clients.guardian import OrderBy
from app.db import SessionDep
from app.dependencies import GuardianDep, OpenAIDep
from app.models import Analysis, Sentiment
from app.schemas import AnalyseRequest, ArticleResult, SmartSearchResult, to_result
from app.services.analysis import analyse_article, list_analyses
from app.services.search import attach_analyses, interpret_question, search_articles

router = APIRouter(prefix="/api")


@router.get("/articles/search")
def search(
    q: Annotated[str, Query(min_length=1)],
    session: SessionDep,
    guardian: GuardianDep,
    section: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    order_by: OrderBy = "newest",
) -> list[ArticleResult]:
    """Search the Guardian. Each result includes its stored analysis, or null."""
    if from_date and to_date and from_date > to_date:
        raise HTTPException(status_code=422, detail="from_date must be on or before to_date")
    articles = search_articles(guardian, q, section, from_date, to_date, order_by)
    return attach_analyses(session, articles)


@router.get("/articles/smart-search")
def smart_search(
    q: Annotated[str, Query(min_length=1)],
    session: SessionDep,
    guardian: GuardianDep,
    openai: OpenAIDep,
) -> SmartSearchResult:
    """Search with a plain-English question. Returns the interpreted filters with the results."""
    interpreted = interpret_question(openai, q, date.today())
    articles = search_articles(
        guardian,
        interpreted.keywords,
        interpreted.section,
        from_date=interpreted.from_date,
        order_by=interpreted.order_by,
    )
    return SmartSearchResult(interpreted=interpreted, results=attach_analyses(session, articles))


@router.post("/analyses")
def create_analysis(
    body: AnalyseRequest,
    response: Response,
    session: SessionDep,
    guardian: GuardianDep,
    openai: OpenAIDep,
) -> ArticleResult:
    """Analyse an article. Returns 201 if newly analysed, 200 if it already existed."""
    analysis, created = analyse_article(session, guardian, openai, body.guardian_id)
    response.status_code = 201 if created else 200
    return to_result(analysis.article, analysis)


@router.get("/analyses")
def get_analyses(
    session: SessionDep, sentiment: Sentiment | None = None, q: str | None = None
) -> list[ArticleResult]:
    """List stored analyses, newest first, filtered by sentiment and keyword."""
    return list_analyses(session, sentiment, q)


@router.get("/analyses/{analysis_id}")
def get_analysis(analysis_id: int, session: SessionDep) -> ArticleResult:
    """Fetch one stored analysis with its article."""
    analysis = session.get(Analysis, analysis_id)
    if analysis is None:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return to_result(analysis.article, analysis)
