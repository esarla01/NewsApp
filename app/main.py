from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.clients.guardian import GuardianError, GuardianNotFoundError, GuardianRateLimitError
from app.db import SessionDep
from app.routers import api

app = FastAPI(title="Aries News")
app.include_router(api.router)


@app.exception_handler(GuardianError)
def guardian_error(request: Request, exc: GuardianError) -> JSONResponse:
    if isinstance(exc, GuardianRateLimitError):
        status = 429
    elif isinstance(exc, GuardianNotFoundError):
        status = 404
    else:
        status = 502
    return JSONResponse(status_code=status, content={"detail": str(exc)})


@app.get("/health")
def health(session: SessionDep) -> dict[str, str]:
    session.execute(text("SELECT 1"))
    return {"status": "ok"}
