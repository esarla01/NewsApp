"""Fake Guardian and OpenAI clients shared by the analysis tests."""

from datetime import UTC, datetime

from app.clients.guardian import GuardianArticle
from app.clients.openai_client import ArticleAnalysis
from app.models import Sentiment


class FakeGuardianClient:
    def __init__(self, error=None):
        self.error = error

    def get_article(self, guardian_id):
        if self.error:
            raise self.error
        return GuardianArticle(
            guardian_id=guardian_id,
            web_url=f"https://www.theguardian.com/{guardian_id}",
            headline="Example headline",
            section_name="World news",
            published_at=datetime(2026, 10, 1, 9, 0, tzinfo=UTC),
            body_text="Full article text.",
        )

    def search(self, query, section=None, from_date=None, to_date=None, order_by="newest"):
        return [self.get_article("world/2026/oct/01/example")]


class FakeOpenAIClient:
    """Returns a fixed analysis. `during_call` runs mid-call to simulate what happens meanwhile."""

    model = "fake-model"

    def __init__(self, error=None, during_call=None):
        self.error = error
        self.during_call = during_call
        self.calls = 0

    def analyse(self, headline, body):
        self.calls += 1
        if self.during_call:
            self.during_call()
        if self.error:
            raise self.error
        return ArticleAnalysis(
            summary="A summary.", sentiment=Sentiment.NEGATIVE, rationale="Grim."
        )
