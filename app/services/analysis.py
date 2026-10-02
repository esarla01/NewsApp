from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.clients.guardian import GuardianClient
from app.clients.openai_client import OpenAIClient
from app.models import Analysis, Article, Sentiment
from app.schemas import ArticleResult, to_result


def find_analysis(session: Session, guardian_id: str) -> Analysis | None:
    return session.scalar(
        select(Analysis).join(Analysis.article).where(Article.guardian_id == guardian_id)
    )


def analyse_article(
    session: Session, guardian: GuardianClient, openai: OpenAIClient, guardian_id: str
) -> tuple[Analysis, bool]:
    """Return the article's analysis and whether it was newly created.

    Idempotent: an existing analysis is returned without calling OpenAI. Nothing is
    saved unless both the Guardian and OpenAI calls succeed.
    """
    existing = find_analysis(session, guardian_id)
    if existing:
        return existing, False

    # End the read transaction so no connection is held during the slow API calls.
    session.rollback()

    article = guardian.get_article(guardian_id)
    result = openai.analyse(article.headline, article.body_text or article.standfirst or "")

    analysis = Analysis(
        article=Article(
            guardian_id=article.guardian_id,
            web_url=article.web_url,
            headline=article.headline,
            standfirst=article.standfirst,
            body_text=article.body_text,
            section_name=article.section_name,
            byline=article.byline,
            thumbnail_url=article.thumbnail_url,
            published_at=article.published_at,
        ),
        summary=result.summary,
        sentiment=result.sentiment,
        rationale=result.rationale,
        model=openai.model,
    )
    session.add(analysis)
    try:
        session.commit()
    except IntegrityError:
        # A concurrent request saved this article first, so return its analysis instead.
        session.rollback()
        existing = find_analysis(session, guardian_id)
        if existing is None:
            raise
        return existing, False

    return analysis, True


def list_analyses(
    session: Session, sentiment: Sentiment | None = None, q: str | None = None
) -> list[ArticleResult]:
    """Stored analyses, newest first, optionally filtered by sentiment and keyword."""
    statement = (
        select(Article, Analysis)
        .join(Analysis.article)
        .order_by(Analysis.created_at.desc())
        .limit(50)
    )
    if sentiment:
        statement = statement.where(Analysis.sentiment == sentiment)
    if q:
        keyword = f"%{q}%"
        statement = statement.where(
            or_(Article.headline.ilike(keyword), Analysis.summary.ilike(keyword))
        )

    return [to_result(article, analysis) for article, analysis in session.execute(statement)]
