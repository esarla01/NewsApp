from typing import Literal

from openai import OpenAI, OpenAIError
from pydantic import BaseModel, ValidationError

from app.clients.guardian import SECTIONS, OrderBy
from app.models import Sentiment

# Keeps latency and cost predictable (roughly 3,000 tokens).
MAX_BODY_CHARS = 12_000

INSTRUCTIONS = """You analyse news articles. Given a headline and the article text, return:
- summary: a neutral two to three sentence summary of the article.
- sentiment: the overall tone of the article, either positive, neutral or negative.
- rationale: one sentence explaining why you chose that sentiment."""

INTERPRET_INSTRUCTIONS = """You turn a reader's question into a Guardian news search. Return:
- keywords: a short search phrase of one to five words, not a list. Leave out words about
  time, mood or section, and generic words such as news, latest, articles or happened.
- section: one of {sections}. Only set it when the question clearly names that area,
  otherwise null.
- time_period: "today", "this_week" (also "since Monday", "recent", "lately") or
  "this_month" if the question mentions a recent time period, otherwise "any".
- order_by: "newest", unless the question explicitly asks for the best, top or most
  relevant matches, then "relevance"."""


class AnalysisError(Exception):
    """OpenAI failed, timed out or did not return a valid analysis."""


class ArticleAnalysis(BaseModel):
    """The exact JSON shape OpenAI must return."""

    summary: str
    sentiment: Sentiment
    rationale: str


class SearchQuestion(BaseModel):
    """The exact JSON shape OpenAI must return when interpreting a search question."""

    keywords: str
    section: str | None
    time_period: Literal["any", "today", "this_week", "this_month"]
    order_by: OrderBy


class OpenAIClient:
    """Wraps the OpenAI Responses API. Every reply is parsed into a Pydantic schema."""

    def __init__(self, api_key: str, model: str) -> None:
        self.model = model
        self._client = OpenAI(api_key=api_key, timeout=30.0, max_retries=1)

    def analyse(self, headline: str, body: str) -> ArticleAnalysis:
        """Summarise an article and classify its sentiment."""
        try:
            response = self._client.responses.parse(
                model=self.model,
                instructions=INSTRUCTIONS,
                input=f"Headline: {headline}\n\n{body[:MAX_BODY_CHARS]}",
                text_format=ArticleAnalysis,
            )
        except (OpenAIError, ValidationError) as exc:
            raise AnalysisError("OpenAI request failed") from exc

        if response.output_parsed is None:
            raise AnalysisError("OpenAI did not return an analysis")
        return response.output_parsed

    def interpret_question(self, question: str) -> SearchQuestion:
        """Convert a plain-English question into structured search filters."""
        try:
            response = self._client.responses.parse(
                model=self.model,
                instructions=INTERPRET_INSTRUCTIONS.format(sections=", ".join(SECTIONS)),
                input=question,
                text_format=SearchQuestion,
            )
        except (OpenAIError, ValidationError) as exc:
            raise AnalysisError("OpenAI request failed") from exc

        if response.output_parsed is None:
            raise AnalysisError("OpenAI did not return a search query")
        return response.output_parsed
