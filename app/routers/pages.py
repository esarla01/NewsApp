from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.clients.guardian import GuardianError
from app.clients.openai_client import AnalysisError
from app.db import SessionDep
from app.dependencies import GuardianDep, OpenAIDep
from app.models import Sentiment
from app.schemas import GUARDIAN_ID_PATTERN
from app.services.analysis import analyse_article, list_analyses
from app.services.search import attach_analyses, search_articles

templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")

router = APIRouter(default_response_class=HTMLResponse)

# Guardian section ids and the names shown in the dropdown.
SECTIONS = [
    ("world", "World"),
    ("uk-news", "UK"),
    ("politics", "Politics"),
    ("business", "Business"),
    ("technology", "Technology"),
    ("environment", "Environment"),
    ("science", "Science"),
    ("sport", "Sport"),
    ("culture", "Culture"),
]


@router.get("/")
def index(request: Request, session: SessionDep):
    context = {"sections": SECTIONS, "history": list_analyses(session)}
    return templates.TemplateResponse(request, "index.html", context)


@router.get("/partials/search")
def search_results(
    request: Request, session: SessionDep, guardian: GuardianDep, q: str = "", section: str = ""
):
    if not q.strip():
        return templates.TemplateResponse(
            request, "partials/results.html", {"error": "Enter a search term."}
        )
    try:
        articles = search_articles(guardian, q, section)
    except GuardianError:
        return templates.TemplateResponse(
            request, "partials/results.html", {"error": "Couldn't reach the Guardian. Try again."}
        )

    results = attach_analyses(session, articles)
    return templates.TemplateResponse(request, "partials/results.html", {"results": results})


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

    response = templates.TemplateResponse(request, "partials/analysis.html", {"analysis": analysis})
    # Tells the history list on the page to reload itself.
    response.headers["HX-Trigger"] = "analysed"
    return response


@router.get("/partials/history")
def history(request: Request, session: SessionDep, q: str = "", sentiment: str = ""):
    # The dropdown sends "" for "All sentiments".
    selected = Sentiment(sentiment) if sentiment in Sentiment else None
    context = {"history": list_analyses(session, selected, q or None)}
    return templates.TemplateResponse(request, "partials/history.html", context)
