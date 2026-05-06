from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import AppSetting

MARGIN_PERCENT_KEY = "bot_margin_percent"
MIN_DEAL_RUB_KEY = "min_deal_rub"
MIN_DEAL_RUB_DEFAULT = 8000
MIN_DEAL_RUB_MIN = 1
ROUND_STEP_RUB_KEY = "round_step_rub"
ROUND_STEP_RUB_DEFAULT = 500
ROUND_STEP_RUB_MIN = 1


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


async def get_min_deal_rub(
    session: AsyncSession,
    default_value: int = MIN_DEAL_RUB_DEFAULT,
) -> int:
    row = await session.scalar(select(AppSetting).where(AppSetting.key == MIN_DEAL_RUB_KEY))
    if row is None:
        return default_value
    try:
        value = int(row.value)
    except ValueError:
        return default_value
    if value < MIN_DEAL_RUB_MIN:
        return default_value
    return value


async def set_min_deal_rub(session: AsyncSession, min_deal_rub: int) -> int:
    if min_deal_rub < MIN_DEAL_RUB_MIN:
        raise ValueError(f"min_deal_rub must be >= {MIN_DEAL_RUB_MIN}")

    row = await session.scalar(select(AppSetting).where(AppSetting.key == MIN_DEAL_RUB_KEY))
    value = str(min_deal_rub)
    if row is None:
        session.add(AppSetting(key=MIN_DEAL_RUB_KEY, value=value))
    else:
        row.value = value
    await session.flush()
    return min_deal_rub


async def get_round_step_rub(
    session: AsyncSession,
    default_value: int = ROUND_STEP_RUB_DEFAULT,
) -> int:
    row = await session.scalar(select(AppSetting).where(AppSetting.key == ROUND_STEP_RUB_KEY))
    if row is None:
        return default_value
    try:
        value = int(row.value)
    except ValueError:
        return default_value
    if value < ROUND_STEP_RUB_MIN:
        return default_value
    return value


async def set_round_step_rub(session: AsyncSession, round_step_rub: int) -> int:
    if round_step_rub < ROUND_STEP_RUB_MIN:
        raise ValueError(f"round_step_rub must be >= {ROUND_STEP_RUB_MIN}")

    row = await session.scalar(select(AppSetting).where(AppSetting.key == ROUND_STEP_RUB_KEY))
    value = str(round_step_rub)
    if row is None:
        session.add(AppSetting(key=ROUND_STEP_RUB_KEY, value=value))
    else:
        row.value = value
    await session.flush()
    return round_step_rub
