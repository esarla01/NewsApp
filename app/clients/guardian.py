from datetime import date, datetime
from typing import Literal

import httpx
from pydantic import BaseModel

BASE_URL = "https://content.guardianapis.com"
CARD_FIELDS = "standfirst,byline,thumbnail"

OrderBy = Literal["newest", "relevance"]

# Guardian section ids and their display names, used by the dropdown and by smart search.
SECTIONS = {
    "world": "World",
    "uk-news": "UK",
    "politics": "Politics",
    "business": "Business",
    "technology": "Technology",
    "environment": "Environment",
    "science": "Science",
    "sport": "Sport",
    "culture": "Culture",
}


class GuardianError(Exception):
    """The Guardian API failed or could not be reached."""


class GuardianRateLimitError(GuardianError):
    """The Guardian API rate limit was reached."""


class GuardianNotFoundError(GuardianError):
    """The requested article does not exist."""


class GuardianArticle(BaseModel):
    guardian_id: str
    web_url: str
    headline: str
    standfirst: str | None = None
    section_name: str
    byline: str | None = None
    thumbnail_url: str | None = None
    published_at: datetime
    body_text: str | None = None  # only filled in by get_article()


class GuardianClient:
    def __init__(self, api_key: str, transport: httpx.BaseTransport | None = None):
        self.api_key = api_key
        self.http = httpx.Client(base_url=BASE_URL, timeout=10, transport=transport)

    def search(
        self,
        query: str,
        section: str | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
        order_by: OrderBy = "newest",
    ) -> list[GuardianArticle]:
        params = {
            "q": query,
            "type": "article",
            "order-by": order_by,
            "show-fields": CARD_FIELDS,
            "page-size": 10,
        }
        if section:
            params["section"] = section
        if from_date:
            params["from-date"] = from_date.isoformat()
        if to_date:
            params["to-date"] = to_date.isoformat()

        data = self._get("/search", params)
        return [parse_article(item) for item in data["results"]]

    def get_article(self, guardian_id: str) -> GuardianArticle:
        """Fetch one article, including its full body text."""
        data = self._get(f"/{guardian_id}", {"show-fields": CARD_FIELDS + ",bodyText"})
        return parse_article(data["content"])

    def _get(self, path: str, params: dict) -> dict:
        params["api-key"] = self.api_key
        try:
            response = self.http.get(path, params=params)
        except httpx.HTTPError as exc:
            raise GuardianError("Could not reach the Guardian API") from exc

        if response.status_code == 429:
            raise GuardianRateLimitError("Guardian API rate limit reached")
        if response.status_code == 404:
            raise GuardianNotFoundError("Article not found")
        if response.is_error:
            raise GuardianError(f"Guardian API returned {response.status_code}")

        return response.json()["response"]


def parse_article(item: dict) -> GuardianArticle:
    """Turn one Guardian result into a flat GuardianArticle."""
    fields = item.get("fields", {})
    return GuardianArticle(
        guardian_id=item["id"],
        web_url=item["webUrl"],
        headline=item["webTitle"],
        standfirst=fields.get("standfirst"),
        section_name=item["sectionName"],
        byline=fields.get("byline"),
        thumbnail_url=fields.get("thumbnail"),
        published_at=item["webPublicationDate"],
        body_text=fields.get("bodyText"),
    )
