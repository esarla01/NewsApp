from typing import Annotated

from fastapi import Depends

from app.clients.guardian import GuardianClient
from app.config import settings

# One shared client, so all requests reuse the same connection pool.
guardian_client = GuardianClient(settings.guardian_api_key)


def get_guardian_client() -> GuardianClient:
    return guardian_client


GuardianDep = Annotated[GuardianClient, Depends(get_guardian_client)]
