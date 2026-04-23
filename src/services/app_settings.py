from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import AppSetting

MARGIN_PERCENT_KEY = "bot_margin_percent"


async def get_margin_percent(session: AsyncSession, default_margin_percent: float) -> float:
    row = await session.scalar(select(AppSetting).where(AppSetting.key == MARGIN_PERCENT_KEY))
    if row is None:
        return default_margin_percent
    try:
        value = float(row.value)
    except ValueError:
        return default_margin_percent
    if value < 0:
        return default_margin_percent
    return value


async def set_margin_percent(session: AsyncSession, margin_percent: float) -> float:
    if margin_percent < 0:
        raise ValueError("margin_percent must be >= 0")

    row = await session.scalar(select(AppSetting).where(AppSetting.key == MARGIN_PERCENT_KEY))
    value = f"{margin_percent:.6f}".rstrip("0").rstrip(".")
    if row is None:
        session.add(AppSetting(key=MARGIN_PERCENT_KEY, value=value))
    else:
        row.value = value
    await session.flush()
    return margin_percent
