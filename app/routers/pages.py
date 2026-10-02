from datetime import date
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.clients.guardian import SECTIONS, GuardianError
from app.clients.openai_client import AnalysisError
from app.db import SessionDep
from app.dependencies import GuardianDep, OpenAIDep
from app.models import Sentiment
from app.schemas import GUARDIAN_ID_PATTERN
from app.services.analysis import analyse_article, list_analyses
from app.services.search import attach_analyses, interpret_question, search_articles

templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")

router = APIRouter(default_response_class=HTMLResponse)


@router.get("/")
def index(request: Request):
    return templates.TemplateResponse(request, "index.html", {"sections": SECTIONS})


@router.get("/history")
def history_page(request: Request, session: SessionDep):
    return templates.TemplateResponse(request, "history.html", {"history": list_analyses(session)})


@router.get("/partials/search")
def search_results(
    request: Request,
    session: SessionDep,
    guardian: GuardianDep,
    openai: OpenAIDep,
    q: str = "",
    section: str = "",
    from_date: str = "",
    to_date: str = "",
    order_by: str = "newest",
    smart: str = "",
):
    # Empty date fields arrive as "", so the dates are converted here rather than by FastAPI.
    start = date.fromisoformat(from_date) if from_date else None
    end = date.fromisoformat(to_date) if to_date else None
    order = "relevance" if order_by == "relevance" else "newest"

    if not q.strip():
        return templates.TemplateResponse(
            request, "partials/results.html", {"error": "Enter a search term."}
        )
    # Smart search replaces the filters with the ones the AI worked out from the question.
    interpreted = None
    if smart:
        interpreted = interpret_question(openai, q, date.today())
        q = interpreted.keywords
        section = interpreted.section
        start = interpreted.from_date
        end = None
        order = interpreted.order_by

    if start and end and start > end:
        return templates.TemplateResponse(
            request, "partials/results.html", {"error": "The From date must be before the To date."}
        )
    try:
        articles = search_articles(guardian, q, section, start, end, order)
    except GuardianError:
        return templates.TemplateResponse(
            request, "partials/results.html", {"error": "Couldn't reach the Guardian. Try again."}
        )

    context = {
        "results": attach_analyses(session, articles),
        "interpreted": interpreted,
        "sections": SECTIONS,
    }
    return templates.TemplateResponse(request, "partials/results.html", context)


@router.post("/partials/analyse")
def analyse(
    request: Request,
    session: SessionDep,
    guardian: GuardianDep,
    openai: OpenAIDep,
    guardian_id: Annotated[str, Form(pattern=GUARDIAN_ID_PATTERN)],
):
    try:
        analysis, _ = analyse_article(session, guardian, openai, guardian_id)
    except (GuardianError, AnalysisError):
        context = {"guardian_id": guardian_id, "error": "Couldn't analyse this article. Try again."}
        return templates.TemplateResponse(request, "partials/analysis.html", context)

    return templates.TemplateResponse(request, "partials/analysis.html", {"analysis": analysis})


@router.get("/partials/history")
def history_results(request: Request, session: SessionDep, q: str = "", sentiment: str = ""):
    # The dropdown sends "" for "All sentiments".
    selected = Sentiment(sentiment) if sentiment in Sentiment else None
    context = {"history": list_analyses(session, selected, q or None)}
    return templates.TemplateResponse(request, "partials/history.html", context)
