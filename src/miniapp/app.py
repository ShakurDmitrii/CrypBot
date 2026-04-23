from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from src.config import get_settings
from src.db.init_db import create_tables
from src.db.session import SessionLocal, engine
from src.services.exchange_requests import (
    create_exchange_request,
    get_or_create_user,
    list_user_requests,
)
from src.services.rates import RateServiceError, available_directions, calc_receive, get_quote

settings = get_settings()
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title="CrypBot Mini App API", version="0.1.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class CalcRequest(BaseModel):
    direction: str
    amount_send: float = Field(gt=0)


class CreateRequestPayload(BaseModel):
    telegram_id: int
    direction: str
    amount_send: float = Field(gt=0)
    user_requisites: str = Field(min_length=1, max_length=512)
    username: str | None = Field(default=None, max_length=64)
    full_name: str | None = Field(default=None, max_length=128)


def _validate_direction(direction: str) -> None:
    if direction not in available_directions():
        raise HTTPException(status_code=400, detail="Unsupported direction")


@app.on_event("startup")
async def on_startup() -> None:
    await create_tables(engine)


@app.get("/")
async def miniapp_index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/offer")
async def offer() -> dict[str, str]:
    return {"url": settings.bot_offer_url}


@app.get("/api/directions")
async def directions() -> dict[str, list[dict[str, str]]]:
    return {
        "items": [
            {"id": direction, "label": direction.replace("->", " -> ")}
            for direction in available_directions()
        ]
    }


@app.post("/api/calc")
async def calc(payload: CalcRequest) -> dict[str, float | str]:
    _validate_direction(payload.direction)
    try:
        quote = await get_quote(payload.direction, settings.bot_margin_percent, settings)
    except RateServiceError as exc:
        raise HTTPException(status_code=503, detail="Rate provider is temporarily unavailable") from exc
    amount_receive = calc_receive(payload.amount_send, quote.final_rate)
    return {
        "direction": payload.direction,
        "amount_send": payload.amount_send,
        "amount_receive": amount_receive,
        "base_rate": quote.base_rate,
        "final_rate": quote.final_rate,
        "margin_percent": quote.margin_percent,
    }


@app.post("/api/requests")
async def create_request(payload: CreateRequestPayload) -> dict[str, int | str | float]:
    _validate_direction(payload.direction)
    try:
        quote = await get_quote(payload.direction, settings.bot_margin_percent, settings)
    except RateServiceError as exc:
        raise HTTPException(status_code=503, detail="Rate provider is temporarily unavailable") from exc
    amount_receive = calc_receive(payload.amount_send, quote.final_rate)

    async with SessionLocal() as session:
        user = await get_or_create_user(
            session=session,
            telegram_id=payload.telegram_id,
            username=payload.username,
            full_name=payload.full_name,
        )
        request = await create_exchange_request(
            session=session,
            user_id=user.id,
            direction=payload.direction,
            amount_send=payload.amount_send,
            amount_receive=amount_receive,
            base_rate=quote.base_rate,
            margin_percent=quote.margin_percent,
            final_rate=quote.final_rate,
            user_requisites=payload.user_requisites,
            source="miniapp",
        )
        await session.commit()

    return {
        "id": request.id,
        "direction": request.direction,
        "amount_send": request.amount_send,
        "amount_receive": request.amount_receive,
        "status": request.status.value,
    }


@app.get("/api/requests/{telegram_id}")
async def user_requests(telegram_id: int) -> dict[str, list[dict[str, int | str | float]]]:
    async with SessionLocal() as session:
        user = await get_or_create_user(
            session=session,
            telegram_id=telegram_id,
            username=None,
            full_name=None,
        )
        rows = await list_user_requests(session, user.id, limit=20)
        await session.commit()

    return {
        "items": [
            {
                "id": row.id,
                "direction": row.direction,
                "amount_send": row.amount_send,
                "amount_receive": row.amount_receive,
                "status": row.status.value,
                "created_at": row.created_at.isoformat() if row.created_at else "",
            }
            for row in rows
        ]
    }


if __name__ == "__main__":
    uvicorn.run("src.miniapp.app:app", host="0.0.0.0", port=8080, reload=True)
