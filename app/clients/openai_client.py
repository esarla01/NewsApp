from openai import OpenAI, OpenAIError
from pydantic import BaseModel, ValidationError

from app.models import Sentiment

# Keeps latency and cost predictable (roughly 3,000 tokens).
MAX_BODY_CHARS = 12_000

INSTRUCTIONS = """You analyse news articles. Given a headline and the article text, return:
- summary: a neutral two to three sentence summary of the article.
- sentiment: the overall tone of the article, either positive, neutral or negative.
- rationale: one sentence explaining why you chose that sentiment."""


class AnalysisError(Exception):
    """OpenAI failed, timed out or did not return a valid analysis."""


class ArticleAnalysis(BaseModel):
    """The exact JSON shape OpenAI must return."""

    summary: str
    sentiment: Sentiment
    rationale: str


class OpenAIClient:
    def __init__(self, api_key: str, model: str) -> None:
        self.model = model
        self._client = OpenAI(api_key=api_key, timeout=30.0, max_retries=1)

    def analyse(self, headline: str, body: str) -> ArticleAnalysis:
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
