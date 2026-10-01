from datetime import UTC, datetime

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.models import Analysis, Article, Sentiment


def make_article(guardian_id: str = "world/2026/oct/01/example") -> Article:
    return Article(
        guardian_id=guardian_id,
        web_url=f"https://www.theguardian.com/{guardian_id}",
        headline="Example headline",
        section_name="World news",
        published_at=datetime(2026, 10, 1, 9, 0, tzinfo=UTC),
    )


def make_analysis(article: Article, sentiment: Sentiment = Sentiment.NEUTRAL) -> Analysis:
    return Analysis(
        article=article,
        summary="A short summary.",
        sentiment=sentiment,
        rationale="Balanced reporting.",
        model="gpt-4.1-nano",
    )


def test_article_and_analysis_are_saved_together(session):
    article = make_article()
    session.add(make_analysis(article, Sentiment.POSITIVE))
    session.commit()

    saved = session.scalars(select(Article)).one()
    assert saved.analysis.sentiment is Sentiment.POSITIVE
    assert saved.created_at is not None


def test_sentiment_is_stored_as_lowercase_value(session):
    session.add(make_analysis(make_article(), Sentiment.NEGATIVE))
    session.commit()

    stored = session.scalar(text("SELECT sentiment FROM analyses"))
    assert stored == "negative"


def test_duplicate_guardian_id_is_rejected(session):
    session.add(make_article())
    session.commit()

    session.add(make_article())
    with pytest.raises(IntegrityError, match="uq_articles_guardian_id"):
        session.commit()


def test_article_cannot_have_two_analyses(session):
    article = make_article()
    session.add(make_analysis(article))
    session.commit()

    # Set article_id directly: assigning the relationship would just replace the first analysis.
    duplicate = Analysis(
        article_id=article.id,
        summary="Another summary.",
        sentiment=Sentiment.NEUTRAL,
        rationale="Another rationale.",
        model="gpt-4.1-nano",
    )
    session.add(duplicate)
    with pytest.raises(IntegrityError, match="uq_analyses_article_id"):
        session.commit()


def test_database_rejects_unknown_sentiment(session):
    article = make_article()
    session.add(article)
    session.commit()

    # Raw SQL bypasses the Python enum, so this checks the database constraint itself.
    with pytest.raises(IntegrityError, match="ck_analyses_sentiment"):
        session.execute(
            text(
                "INSERT INTO analyses (article_id, summary, sentiment, rationale, model) "
                "VALUES (:id, 's', 'angry', 'r', 'm')"
            ),
            {"id": article.id},
        )


def test_deleting_article_deletes_its_analysis(session):
    session.add(make_analysis(make_article()))
    session.commit()

    session.delete(session.scalars(select(Article)).one())
    session.commit()

    assert session.scalars(select(Analysis)).all() == []
