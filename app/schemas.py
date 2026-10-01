from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.clients.guardian import GuardianArticle
from app.models import Sentiment


class AnalysisOut(BaseModel):
    """The analysis fields the API returns."""

    # Lets AnalysisOut.model_validate() read fields from a SQLAlchemy Analysis object.
    model_config = ConfigDict(from_attributes=True)

    id: int
    summary: str
    sentiment: Sentiment
    rationale: str
    model: str
    created_at: datetime


class ArticleResult(BaseModel):
    """A Guardian search result and its stored analysis (None if not analysed yet)."""

    article: GuardianArticle
    analysis: AnalysisOut | None
