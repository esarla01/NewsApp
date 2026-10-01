from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models import Sentiment


class ArticleOut(BaseModel):
    """The article fields the API returns (the full body text is left out)."""

    # Lets model_validate() read fields from a GuardianArticle or a SQLAlchemy Article.
    model_config = ConfigDict(from_attributes=True)

    guardian_id: str
    web_url: str
    headline: str
    standfirst: str | None
    section_name: str
    byline: str | None
    thumbnail_url: str | None
    published_at: datetime


class AnalysisOut(BaseModel):
    """The analysis fields the API returns."""

    # Lets model_validate() read fields from a SQLAlchemy Analysis.
    model_config = ConfigDict(from_attributes=True)

    id: int
    summary: str
    sentiment: Sentiment
    rationale: str
    model: str
    created_at: datetime


class ArticleResult(BaseModel):
    """An article and its stored analysis (None if not analysed yet)."""

    article: ArticleOut
    analysis: AnalysisOut | None


class AnalyseRequest(BaseModel):
    # Guardian ids look like "world/2026/oct/01/some-slug". Rejecting anything else
    # stops odd input from being sent to the Guardian as a URL path.
    guardian_id: str = Field(pattern=r"^[a-z0-9_-]+(/[a-z0-9_-]+)+$", max_length=300)


def to_result(article, analysis) -> ArticleResult:
    """Build an ArticleResult from an article and an optional analysis."""
    return ArticleResult(
        article=ArticleOut.model_validate(article),
        analysis=AnalysisOut.model_validate(analysis) if analysis else None,
    )
