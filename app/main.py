from fastapi import FastAPI
from sqlalchemy import text

from app.db import SessionDep

app = FastAPI(title="Aries News")


@app.get("/health")
def health(session: SessionDep) -> dict[str, str]:
    session.execute(text("SELECT 1"))
    return {"status": "ok"}
