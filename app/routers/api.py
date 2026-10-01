from typing import Annotated

from fastapi import APIRouter, Query

from app.db import SessionDep
from app.dependencies import GuardianDep
from app.schemas import ArticleResult
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
