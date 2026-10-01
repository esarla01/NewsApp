import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Sentiment(enum.StrEnum):
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"


class Article(Base):
    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(primary_key=True)
    guardian_id: Mapped[str] = mapped_column(unique=True)
    web_url: Mapped[str] = mapped_column(Text)  # the URL of the article on the Guardian website
    headline: Mapped[str] = mapped_column(Text)
    standfirst: Mapped[str | None] = mapped_column(Text)  # short subtitle or summary of the article
    body_text: Mapped[str | None] = mapped_column(Text)
    section_name: Mapped[str]
    byline: Mapped[str | None] = mapped_column(Text)  # the author of the article
    thumbnail_url: Mapped[str | None] = mapped_column(Text)  # image URL for the article thumbnail
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    analysis: Mapped["Analysis | None"] = relationship(
        back_populates="article", cascade="all, delete-orphan", passive_deletes=True
    )


class Analysis(Base):
    __tablename__ = "analyses"

    id: Mapped[int] = mapped_column(primary_key=True)
    article_id: Mapped[int] = mapped_column(
        ForeignKey("articles.id", ondelete="CASCADE"), unique=True
    )
    summary: Mapped[str] = mapped_column(Text)

    # Claude suggestion: Stored as VARCHAR + CHECK rather than a native Postgres enum, which
    # is awkward to alter. This allows us to add new values without having to run a migration.
    sentiment: Mapped[Sentiment] = mapped_column(
        Enum(
            Sentiment,
            name="sentiment",
            native_enum=False,
            create_constraint=True,
            values_callable=lambda e: [member.value for member in e],
        )
    )
    rationale: Mapped[str] = mapped_column(Text)
    model: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    article: Mapped[Article] = relationship(back_populates="analysis")
