from decimal import Decimal

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import (
    AmlCheck,
    AmlStatus,
    ExchangeRequest,
    RequestStatus,
    RequestStatusHistory,
    User,
)


async def get_or_create_user(
    session: AsyncSession,
    telegram_id: int,
    username: str | None,
    full_name: str | None,
) -> User:
    stmt: Select[tuple[User]] = select(User).where(User.telegram_id == telegram_id)
    user = await session.scalar(stmt)
    if user:
        if username is not None:
            user.username = username
        if full_name is not None:
            user.full_name = full_name
        await session.flush()
        return user

    user = User(telegram_id=telegram_id, username=username, full_name=full_name)
    session.add(user)
    await session.flush()
    return user


async def create_exchange_request(
    session: AsyncSession,
    user_id: int,
    direction: str,
    amount_send: float,
    amount_receive: float,
    base_rate: float,
    margin_percent: float,
    final_rate: float,
    user_requisites: str,
    source: str = "telegram",
) -> ExchangeRequest:
    amount_send_dec = Decimal(str(amount_send))
    amount_receive_dec = Decimal(str(amount_receive))
    base_rate_dec = Decimal(str(base_rate))
    margin_percent_dec = Decimal(str(margin_percent))
    final_rate_dec = Decimal(str(final_rate))

    request = ExchangeRequest(
        source=source,
        user_id=user_id,
        direction=direction,
        amount_send=amount_send_dec,
        amount_receive=amount_receive_dec,
        base_rate=base_rate_dec,
        margin_percent=margin_percent_dec,
        final_rate=final_rate_dec,
        user_requisites=user_requisites,
        status=RequestStatus.NEW,
    )
    session.add(request)
    await session.flush()

    status_history = RequestStatusHistory(
        request_id=request.id,
        status=RequestStatus.NEW,
        comment="Created via Telegram bot",
        changed_by="bot",
    )
    session.add(status_history)
    await session.flush()
    return request


async def list_user_requests(session: AsyncSession, user_id: int, limit: int = 10) -> list[ExchangeRequest]:
    stmt: Select[tuple[ExchangeRequest]] = (
        select(ExchangeRequest)
        .where(ExchangeRequest.user_id == user_id)
        .order_by(ExchangeRequest.created_at.desc())
        .limit(limit)
    )
    rows = await session.scalars(stmt)
    return list(rows)


async def get_request_by_id(session: AsyncSession, request_id: int) -> ExchangeRequest | None:
    stmt: Select[tuple[ExchangeRequest]] = select(ExchangeRequest).where(ExchangeRequest.id == request_id)
    return await session.scalar(stmt)


async def update_request_status(
    session: AsyncSession,
    request: ExchangeRequest,
    new_status: RequestStatus,
    changed_by: str,
    comment: str | None = None,
) -> ExchangeRequest:
    request.status = new_status
    request.status_comment = comment
    history = RequestStatusHistory(
        request_id=request.id,
        status=new_status,
        comment=comment,
        changed_by=changed_by,
    )
    session.add(history)
    await session.flush()
    return request


async def create_aml_check(
    session: AsyncSession,
    telegram_user_id: int,
    check_type: str,
    value: str,
    request_id: int | None = None,
) -> AmlCheck:
    aml = AmlCheck(
        request_id=request_id,
        telegram_user_id=telegram_user_id,
        check_type=check_type,
        value=value,
        status=AmlStatus.PENDING,
    )
    session.add(aml)
    await session.flush()
    return aml
