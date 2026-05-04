import re
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import and_, case, delete, func, select, update

from src.config import get_settings
from src.db.models import AmlCheck, ExchangeRequest, RequestStatus, RequestStatusHistory, SupportMessage, User
from src.db.session import SessionLocal
from src.services.app_settings import get_margin_percent
from src.services.exchange_requests import (
    create_exchange_request,
    get_request_by_id,
    get_or_create_user,
    list_user_requests,
    update_request_status,
)
from src.services.rates import RateServiceError, available_directions, calc_receive, get_quote

settings = get_settings()
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title="CrypBot Mini App API", version="0.1.0")
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class CalcRequest(BaseModel):
    direction: str
    amount_send: float = Field(gt=0)


class CreateRequestPayload(BaseModel):
    telegram_id: int
    direction: str
    amount_send: float = Field(gt=0)
    user_requisites: str = Field(min_length=1, max_length=1024)
    username: str | None = Field(default=None, max_length=64)
    full_name: str | None = Field(default=None, max_length=128)


class AdminUpdateRequestStatusPayload(BaseModel):
    status: str
    comment: str | None = Field(default=None, max_length=512)


class UserSupportMessagePayload(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    username: str | None = Field(default=None, max_length=64)
    full_name: str | None = Field(default=None, max_length=128)


class AdminSupportMessagePayload(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


CHAT_ROLE_USER = "user"
CHAT_ROLE_OPERATOR = "operator"


def _validate_direction(direction: str) -> None:
    if direction not in available_directions():
        raise HTTPException(status_code=400, detail="Unsupported direction")


def _is_operator(telegram_id: int) -> bool:
    return telegram_id in settings.operator_ids


def _require_operator(telegram_id: int) -> None:
    if not _is_operator(telegram_id):
        raise HTTPException(status_code=403, detail="Operator access required")


def _operator_username_for_user() -> str:
    username = settings.bot_operator_username.strip()
    if not username:
        return ""
    if not username.startswith("@"):
        username = f"@{username}"
    return username


def _parse_request_status(raw: str) -> RequestStatus:
    try:
        return RequestStatus(raw)
    except ValueError as exc:
        allowed = ", ".join(status.value for status in RequestStatus)
        raise HTTPException(status_code=400, detail=f"Unsupported status. Allowed: {allowed}") from exc


def _extract_phone_from_requisites(user_requisites: str | None) -> str | None:
    if not user_requisites:
        return None
    match = re.search(r"(?im)^\s*(?:телефон|phone)\s*:\s*(.+?)\s*$", user_requisites)
    if not match:
        return None
    phone = match.group(1).strip()
    return phone or None


def _normalize_chat_text(raw: str) -> str:
    text = raw.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Message must not be empty")
    return text


def _serialize_chat_message(message: SupportMessage) -> dict[str, int | str | None]:
    return {
        "id": message.id,
        "sender_role": message.sender_role,
        "message": message.message,
        "operator_telegram_id": message.operator_telegram_id,
        "created_at": message.created_at.isoformat() if message.created_at else None,
    }


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
        "operator_username": _operator_username_for_user(),
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
        user_ids = [row.id for row in items]
        latest_requisites_by_user_id: dict[int, str | None] = {}
        if user_ids:
            requisites_rows = await session.execute(
                select(ExchangeRequest.user_id, ExchangeRequest.user_requisites)
                .where(ExchangeRequest.user_id.in_(user_ids))
                .order_by(ExchangeRequest.user_id.asc(), ExchangeRequest.created_at.desc())
            )
            for user_id, user_requisites in requisites_rows.all():
                if user_id not in latest_requisites_by_user_id:
                    latest_requisites_by_user_id[user_id] = user_requisites

    return {
        "items": [
            {
                "id": row.id,
                "telegram_id": row.telegram_id,
                "username": row.username,
                "full_name": row.full_name,
                "phone": _extract_phone_from_requisites(latest_requisites_by_user_id.get(row.id)),
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
                "user_requisites": request.user_requisites,
                "created_at": request.created_at.isoformat() if request.created_at else None,
                "updated_at": request.updated_at.isoformat() if request.updated_at else None,
            }
            for request, user in items
        ]
    }


@app.get("/api/admin/chat/users/{telegram_id}")
async def admin_chat_users(telegram_id: int, limit: int = 100) -> dict[str, list[dict[str, int | str | None]]]:
    _require_operator(telegram_id)
    safe_limit = max(1, min(limit, 300))
    async with SessionLocal() as session:
        grouped_rows = await session.execute(
            select(
                User.id.label("user_id"),
                User.telegram_id,
                User.username,
                User.full_name,
                func.max(SupportMessage.id).label("last_message_id"),
                func.max(SupportMessage.created_at).label("last_message_at"),
                func.sum(
                    case(
                        (
                            and_(
                                SupportMessage.sender_role == CHAT_ROLE_USER,
                                SupportMessage.is_read_by_operator.is_(False),
                            ),
                            1,
                        ),
                        else_=0,
                    )
                ).label("unread_count"),
            )
            .join(SupportMessage, SupportMessage.user_id == User.id)
            .group_by(User.id)
            .order_by(func.max(SupportMessage.created_at).desc())
            .limit(safe_limit)
        )
        grouped_items = grouped_rows.all()
        last_message_ids = [int(item.last_message_id) for item in grouped_items if item.last_message_id is not None]
        last_messages_by_id: dict[int, SupportMessage] = {}
        if last_message_ids:
            messages_rows = await session.execute(
                select(SupportMessage).where(SupportMessage.id.in_(last_message_ids))
            )
            for message in messages_rows.scalars().all():
                last_messages_by_id[message.id] = message

    items: list[dict[str, int | str | None]] = []
    for item in grouped_items:
        last_message = last_messages_by_id.get(int(item.last_message_id)) if item.last_message_id else None
        items.append(
            {
                "telegram_id": item.telegram_id,
                "username": item.username,
                "full_name": item.full_name,
                "last_message": last_message.message if last_message else None,
                "last_message_at": item.last_message_at.isoformat() if item.last_message_at else None,
                "unread_count": int(item.unread_count or 0),
            }
        )
    return {"items": items}


@app.get("/api/admin/chat/{telegram_id}/{target_user_telegram_id}")
async def admin_chat_messages(
    telegram_id: int, target_user_telegram_id: int, limit: int = 200
) -> dict[str, int | str | None | list[dict[str, int | str | None]]]:
    _require_operator(telegram_id)
    safe_limit = max(1, min(limit, 500))
    async with SessionLocal() as session:
        user_row = await session.execute(select(User).where(User.telegram_id == target_user_telegram_id))
        user = user_row.scalar_one_or_none()
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")
        await session.execute(
            update(SupportMessage)
            .where(
                SupportMessage.user_id == user.id,
                SupportMessage.sender_role == CHAT_ROLE_USER,
                SupportMessage.is_read_by_operator.is_(False),
            )
            .values(is_read_by_operator=True)
        )
        rows = await session.execute(
            select(SupportMessage)
            .where(SupportMessage.user_id == user.id)
            .order_by(SupportMessage.created_at.asc())
            .limit(safe_limit)
        )
        messages = rows.scalars().all()
        await session.commit()

    return {
        "user_telegram_id": user.telegram_id,
        "username": user.username,
        "full_name": user.full_name,
        "items": [_serialize_chat_message(message) for message in messages],
    }


@app.post("/api/admin/chat/{telegram_id}/{target_user_telegram_id}")
async def admin_send_chat_message(
    telegram_id: int, target_user_telegram_id: int, payload: AdminSupportMessagePayload
) -> dict[str, int | str | None]:
    _require_operator(telegram_id)
    text = _normalize_chat_text(payload.message)
    async with SessionLocal() as session:
        user_row = await session.execute(select(User).where(User.telegram_id == target_user_telegram_id))
        user = user_row.scalar_one_or_none()
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")
        message = SupportMessage(
            user_id=user.id,
            sender_role=CHAT_ROLE_OPERATOR,
            message=text,
            operator_telegram_id=telegram_id,
            is_read_by_user=False,
            is_read_by_operator=True,
        )
        session.add(message)
        await session.commit()
        await session.refresh(message)
    return _serialize_chat_message(message)


@app.get("/api/chat/{telegram_id}")
async def user_chat_messages(telegram_id: int, limit: int = 100) -> dict[str, list[dict[str, int | str | None]]]:
    safe_limit = max(1, min(limit, 300))
    async with SessionLocal() as session:
        user = await get_or_create_user(
            session=session,
            telegram_id=telegram_id,
            username=None,
            full_name=None,
        )
        await session.execute(
            update(SupportMessage)
            .where(
                SupportMessage.user_id == user.id,
                SupportMessage.sender_role == CHAT_ROLE_OPERATOR,
                SupportMessage.is_read_by_user.is_(False),
            )
            .values(is_read_by_user=True)
        )
        rows = await session.execute(
            select(SupportMessage)
            .where(SupportMessage.user_id == user.id)
            .order_by(SupportMessage.created_at.asc())
            .limit(safe_limit)
        )
        messages = rows.scalars().all()
        await session.commit()

    return {"items": [_serialize_chat_message(message) for message in messages]}


@app.post("/api/chat/{telegram_id}")
async def user_send_chat_message(
    telegram_id: int, payload: UserSupportMessagePayload
) -> dict[str, int | str | None]:
    text = _normalize_chat_text(payload.message)
    async with SessionLocal() as session:
        user = await get_or_create_user(
            session=session,
            telegram_id=telegram_id,
            username=payload.username,
            full_name=payload.full_name,
        )
        message = SupportMessage(
            user_id=user.id,
            sender_role=CHAT_ROLE_USER,
            message=text,
            operator_telegram_id=None,
            is_read_by_user=True,
            is_read_by_operator=False,
        )
        session.add(message)
        await session.commit()
        await session.refresh(message)
    return _serialize_chat_message(message)


@app.patch("/api/admin/requests/{telegram_id}/{request_id}/status")
async def admin_update_request_status(
    telegram_id: int, request_id: int, payload: AdminUpdateRequestStatusPayload
) -> dict[str, int | str | None]:
    _require_operator(telegram_id)
    new_status = _parse_request_status(payload.status)
    comment = (payload.comment or "").strip() or None
    async with SessionLocal() as session:
        request = await get_request_by_id(session, request_id)
        if request is None:
            raise HTTPException(status_code=404, detail="Request not found")
        await update_request_status(
            session=session,
            request=request,
            new_status=new_status,
            changed_by=f"miniapp-operator:{telegram_id}",
            comment=comment,
        )
        await session.commit()
        return {
            "id": request.id,
            "status": request.status.value,
            "status_comment": request.status_comment,
        }


@app.delete("/api/admin/requests/{telegram_id}/{request_id}")
async def admin_delete_request(telegram_id: int, request_id: int) -> dict[str, int | bool]:
    _require_operator(telegram_id)
    async with SessionLocal() as session:
        request = await get_request_by_id(session, request_id)
        if request is None:
            raise HTTPException(status_code=404, detail="Request not found")
        await session.execute(delete(RequestStatusHistory).where(RequestStatusHistory.request_id == request_id))
        await session.execute(delete(AmlCheck).where(AmlCheck.request_id == request_id))
        await session.delete(request)
        await session.commit()
    return {"ok": True, "deleted_request_id": request_id}


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
