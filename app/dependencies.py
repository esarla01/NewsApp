from typing import Annotated

from fastapi import Depends

from app.clients.guardian import GuardianClient
from app.clients.openai_client import OpenAIClient
from app.config import settings

# One shared client each, so all requests reuse the same connection pools.
guardian_client = GuardianClient(settings.guardian_api_key)
openai_client = OpenAIClient(settings.openai_api_key, settings.openai_model)


def get_guardian_client() -> GuardianClient:
    return guardian_client


def get_openai_client() -> OpenAIClient:
    return openai_client


GuardianDep = Annotated[GuardianClient, Depends(get_guardian_client)]
OpenAIDep = Annotated[OpenAIClient, Depends(get_openai_client)]
