from datetime import datetime
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

BASE_URL = "https://content.guardianapis.com"
PAGE_SIZE = 10
CARD_FIELDS = "standfirst,byline,thumbnail"


class GuardianError(Exception):
    """The Guardian API failed, timed out or returned something unexpected."""


class GuardianRateLimitError(GuardianError):
    """The Guardian API rejected the request because of rate limiting."""


class GuardianNotFoundError(GuardianError):
    """The requested Guardian content does not exist."""


class GuardianArticle(BaseModel):
    guardian_id: str
    web_url: str
    headline: str
    standfirst: str | None = None
    section_name: str
    byline: str | None = None
    thumbnail_url: str | None = None
    published_at: datetime


class GuardianClient:
    def __init__(self, api_key: str, transport: httpx.BaseTransport | None = None) -> None:
        self._api_key = api_key
        self._http = httpx.Client(base_url=BASE_URL, timeout=10.0, transport=transport)

    def search(self, query: str, section: str | None = None) -> list[GuardianArticle]:
        params = {
            "q": query,
            "type": "article",
            "order-by": "newest",
            "show-fields": CARD_FIELDS,
            "page-size": PAGE_SIZE,
        }
        if section:
            params["section"] = section

        data = self._get("/search", params)
        try:
            return [_parse_article(item) for item in data["results"]]
        except (KeyError, TypeError, ValidationError) as exc:
            raise GuardianError("Unexpected search response from the Guardian API") from exc

    def close(self) -> None:
        self._http.close()

    def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        try:
            response = self._http.get(path, params={**params, "api-key": self._api_key})
        except httpx.HTTPError as exc:
            raise GuardianError("Could not reach the Guardian API") from exc

        if response.status_code == 429:
            raise GuardianRateLimitError("Guardian API rate limit reached")
        if response.status_code == 404:
            raise GuardianNotFoundError("Guardian content not found")
        if response.is_error:
            raise GuardianError(f"Guardian API returned {response.status_code}")

        try:
            return response.json()["response"]
        except (ValueError, KeyError) as exc:
            raise GuardianError("Unexpected response from the Guardian API") from exc


def _parse_article(item: dict[str, Any]) -> GuardianArticle:
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
    )
