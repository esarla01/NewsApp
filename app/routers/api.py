from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response

from app.db import SessionDep
from app.dependencies import GuardianDep, OpenAIDep
from app.models import Analysis, Sentiment
from app.schemas import AnalyseRequest, ArticleResult, to_result
from app.services.analysis import analyse_article, list_analyses
from app.services.search import attach_analyses, search_articles

router = APIRouter(prefix="/api")


@router.get("/articles/search")
def search(
    q: Annotated[str, Query(min_length=1)],
    session: SessionDep,
    guardian: GuardianDep,
    section: str | None = None,
) -> list[ArticleResult]:
    articles = search_articles(guardian, q, section)
    return attach_analyses(session, articles)


@router.post("/analyses")
def create_analysis(
    body: AnalyseRequest,
    response: Response,
    session: SessionDep,
    guardian: GuardianDep,
    openai: OpenAIDep,
) -> ArticleResult:
    analysis, created = analyse_article(session, guardian, openai, body.guardian_id)
    response.status_code = 201 if created else 200
    return to_result(analysis.article, analysis)


@router.get("/analyses")
def get_analyses(
    session: SessionDep, sentiment: Sentiment | None = None, q: str | None = None
) -> list[ArticleResult]:
    return list_analyses(session, sentiment, q)


@router.get("/analyses/{analysis_id}")
def get_analysis(analysis_id: int, session: SessionDep) -> ArticleResult:
    analysis = session.get(Analysis, analysis_id)
    if analysis is None:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return to_result(analysis.article, analysis)
