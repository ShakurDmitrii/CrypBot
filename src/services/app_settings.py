from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import AppSetting

MARGIN_PERCENT_KEY = "bot_margin_percent"
MIN_DEAL_USDT_KEY = "min_deal_usdt"
MIN_DEAL_USDT_DEFAULT = 100
MIN_DEAL_USDT_ALLOWED = (100, 200, 250, 300, 350, 500)
ROUND_STEP_RUB_KEY = "round_step_rub"
ROUND_STEP_RUB_DEFAULT = 500
ROUND_STEP_RUB_ALLOWED = (100, 200, 250, 300, 350, 500, 1000)


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


async def get_min_deal_usdt(
    session: AsyncSession,
    default_value: int = MIN_DEAL_USDT_DEFAULT,
) -> int:
    row = await session.scalar(select(AppSetting).where(AppSetting.key == MIN_DEAL_USDT_KEY))
    if row is None:
        return default_value
    try:
        value = int(row.value)
    except ValueError:
        return default_value
    if value not in MIN_DEAL_USDT_ALLOWED:
        return default_value
    return value


async def set_min_deal_usdt(session: AsyncSession, min_deal_usdt: int) -> int:
    if min_deal_usdt not in MIN_DEAL_USDT_ALLOWED:
        allowed = ", ".join(str(item) for item in MIN_DEAL_USDT_ALLOWED)
        raise ValueError(f"min_deal_usdt must be one of: {allowed}")

    row = await session.scalar(select(AppSetting).where(AppSetting.key == MIN_DEAL_USDT_KEY))
    value = str(min_deal_usdt)
    if row is None:
        session.add(AppSetting(key=MIN_DEAL_USDT_KEY, value=value))
    else:
        row.value = value
    await session.flush()
    return min_deal_usdt


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
    if value not in ROUND_STEP_RUB_ALLOWED:
        return default_value
    return value


async def set_round_step_rub(session: AsyncSession, round_step_rub: int) -> int:
    if round_step_rub not in ROUND_STEP_RUB_ALLOWED:
        allowed = ", ".join(str(item) for item in ROUND_STEP_RUB_ALLOWED)
        raise ValueError(f"round_step_rub must be one of: {allowed}")

    row = await session.scalar(select(AppSetting).where(AppSetting.key == ROUND_STEP_RUB_KEY))
    value = str(round_step_rub)
    if row is None:
        session.add(AppSetting(key=ROUND_STEP_RUB_KEY, value=value))
    else:
        row.value = value
    await session.flush()
    return round_step_rub
