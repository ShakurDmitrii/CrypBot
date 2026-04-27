from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from src.config import get_settings
from src.db.models import ExchangeRequest, RequestStatusHistory, User
from src.db.session import SessionLocal
from src.services.app_settings import get_margin_percent
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


def _is_operator(telegram_id: int) -> bool:
    return telegram_id in settings.operator_ids


def _require_operator(telegram_id: int) -> None:
    if not _is_operator(telegram_id):
        raise HTTPException(status_code=403, detail="Operator access required")


@app.get("/")
async def miniapp_index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/admin")
async def miniapp_admin() -> FileResponse:
    return FileResponse(STATIC_DIR / "admin.html")


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/me/{telegram_id}")
async def me(telegram_id: int) -> dict[str, int | bool]:
    return {"telegram_id": telegram_id, "is_operator": _is_operator(telegram_id)}


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
    async with SessionLocal() as session:
        margin_percent = await get_margin_percent(session, settings.bot_margin_percent)
    try:
        quote = await get_quote(payload.direction, margin_percent, settings)
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
    async with SessionLocal() as session:
        margin_percent = await get_margin_percent(session, settings.bot_margin_percent)
    try:
        quote = await get_quote(payload.direction, margin_percent, settings)
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
        "amount_send": float(request.amount_send),
        "amount_receive": float(request.amount_receive),
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
                "amount_send": float(row.amount_send),
                "amount_receive": float(row.amount_receive),
                "status": row.status.value,
                "created_at": row.created_at.isoformat() if row.created_at else "",
            }
            for row in rows
        ]
    }


@app.get("/api/admin/users/{telegram_id}")
async def admin_users(telegram_id: int, limit: int = 100) -> dict[str, list[dict[str, int | str | None]]]:
    _require_operator(telegram_id)
    safe_limit = max(1, min(limit, 300))
    async with SessionLocal() as session:
        rows = await session.execute(
            select(
                User.id,
                User.telegram_id,
                User.username,
                User.full_name,
                User.created_at,
                func.count(ExchangeRequest.id).label("requests_count"),
            )
            .outerjoin(ExchangeRequest, ExchangeRequest.user_id == User.id)
            .group_by(User.id)
            .order_by(User.created_at.desc())
            .limit(safe_limit)
        )
        items = rows.all()

    return {
        "items": [
            {
                "id": row.id,
                "telegram_id": row.telegram_id,
                "username": row.username,
                "full_name": row.full_name,
                "requests_count": int(row.requests_count or 0),
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in items
        ]
    }


@app.get("/api/admin/requests/{telegram_id}")
async def admin_requests(
    telegram_id: int, limit: int = 100
) -> dict[str, list[dict[str, int | float | str | None]]]:
    _require_operator(telegram_id)
    safe_limit = max(1, min(limit, 300))
    async with SessionLocal() as session:
        rows = await session.execute(
            select(ExchangeRequest, User)
            .join(User, ExchangeRequest.user_id == User.id, isouter=True)
            .order_by(ExchangeRequest.created_at.desc())
            .limit(safe_limit)
        )
        items = rows.all()

    return {
        "items": [
            {
                "id": request.id,
                "telegram_id": user.telegram_id if user else None,
                "username": user.username if user else None,
                "full_name": user.full_name if user else None,
                "direction": request.direction,
                "amount_send": float(request.amount_send),
                "amount_receive": float(request.amount_receive),
                "final_rate": float(request.final_rate),
                "status": request.status.value,
                "status_comment": request.status_comment,
                "created_at": request.created_at.isoformat() if request.created_at else None,
                "updated_at": request.updated_at.isoformat() if request.updated_at else None,
            }
            for request, user in items
        ]
    }


@app.get("/api/admin/request-history/{telegram_id}")
async def admin_request_history(
    telegram_id: int, limit: int = 200
) -> dict[str, list[dict[str, int | str | None]]]:
    _require_operator(telegram_id)
    safe_limit = max(1, min(limit, 500))
    async with SessionLocal() as session:
        rows = await session.execute(
            select(RequestStatusHistory, ExchangeRequest, User)
            .join(ExchangeRequest, RequestStatusHistory.request_id == ExchangeRequest.id)
            .join(User, ExchangeRequest.user_id == User.id, isouter=True)
            .order_by(RequestStatusHistory.created_at.desc())
            .limit(safe_limit)
        )
        items = rows.all()

    return {
        "items": [
            {
                "history_id": history.id,
                "request_id": history.request_id,
                "status": history.status.value,
                "comment": history.comment,
                "changed_by": history.changed_by,
                "created_at": history.created_at.isoformat() if history.created_at else None,
                "direction": request.direction,
                "telegram_id": user.telegram_id if user else None,
                "username": user.username if user else None,
            }
            for history, request, user in items
        ]
    }


if __name__ == "__main__":
    uvicorn.run("src.miniapp.app:app", host="0.0.0.0", port=8080, reload=True)
