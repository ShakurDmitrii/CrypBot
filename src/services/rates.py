import asyncio
from dataclasses import dataclass
from time import monotonic
from typing import Any

import aiohttp

from src.config import Settings


@dataclass(frozen=True)
class RateQuote:
    direction: str
    base_rate: float
    final_rate: float
    margin_percent: float


BASE_RATES: dict[str, float] = {
    "RUB->USDT": 0.0110,
    "USDT->RUB": 90.0,
}

_CACHE: dict[str, tuple[float, float]] = {}


class RateServiceError(RuntimeError):
    pass


def available_directions() -> list[str]:
    return list(BASE_RATES.keys())


def _read_cache(key: str, ttl_sec: int) -> float | None:
    cached = _CACHE.get(key)
    if not cached:
        return None
    value, ts = cached
    if monotonic() - ts > ttl_sec:
        return None
    return value


def _write_cache(key: str, value: float) -> None:
    _CACHE[key] = (value, monotonic())


async def _fetch_latest_trade_price(
    session: aiohttp.ClientSession,
    base_url: str,
    symbol: str,
) -> float:
    url = f"{base_url}/market/latest-trade"
    async with session.get(url, params={"symbol": symbol}) as response:
        response.raise_for_status()
        payload: dict[str, Any] = await response.json()
    data = payload.get("data")
    if not data:
        raise RateServiceError("latest-trade returned empty data")
    first = data[0]
    try:
        return float(first["price"])
    except (KeyError, TypeError, ValueError) as exc:
        raise RateServiceError("latest-trade payload has invalid price") from exc


async def _fetch_symbol_thumb_price(
    session: aiohttp.ClientSession,
    base_url: str,
    symbol: str,
) -> float:
    url = f"{base_url}/market/symbol-thumb"
    async with session.get(url) as response:
        response.raise_for_status()
        payload: list[dict[str, Any]] = await response.json()

    symbol_upper = symbol.upper()
    for item in payload:
        if str(item.get("symbol", "")).upper() != symbol_upper:
            continue
        for key in ("close", "last", "price"):
            if key in item:
                try:
                    return float(item[key])
                except (TypeError, ValueError) as exc:
                    raise RateServiceError("symbol-thumb payload has invalid price") from exc
    raise RateServiceError(f"symbol-thumb does not contain symbol {symbol}")


async def _fetch_usdt_rub_rate(settings: Settings) -> float:
    timeout = aiohttp.ClientTimeout(total=settings.rate_api_timeout_sec)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        try:
            return await _fetch_latest_trade_price(
                session=session,
                base_url=settings.rate_api_base_url.rstrip("/"),
                symbol=settings.rate_usdt_rub_symbol,
            )
        except (aiohttp.ClientError, asyncio.TimeoutError, RateServiceError):
            return await _fetch_symbol_thumb_price(
                session=session,
                base_url=settings.rate_api_base_url.rstrip("/"),
                symbol=settings.rate_usdt_rub_symbol,
            )


async def get_quote(direction: str, margin_percent: float, settings: Settings) -> RateQuote:
    if direction not in BASE_RATES:
        raise KeyError(direction)

    cached_rate = _read_cache("USDT->RUB", settings.rate_cache_ttl_sec)
    if cached_rate is None:
        try:
            usdt_rub = await _fetch_usdt_rub_rate(settings)
        except (aiohttp.ClientError, asyncio.TimeoutError, RateServiceError) as exc:
            raise RateServiceError("failed to fetch rate from Rapira API") from exc
        if usdt_rub <= 0:
            raise RateServiceError("Rapira API returned non-positive rate")
        _write_cache("USDT->RUB", usdt_rub)
    else:
        usdt_rub = cached_rate

    if direction == "USDT->RUB":
        base_rate = usdt_rub
    elif direction == "RUB->USDT":
        base_rate = 1 / usdt_rub
    else:
        base_rate = BASE_RATES[direction]

    final_rate = base_rate * (1 + margin_percent / 100)
    return RateQuote(
        direction=direction,
        base_rate=base_rate,
        final_rate=final_rate,
        margin_percent=margin_percent,
    )


def calc_receive(amount_send: float, final_rate: float) -> float:
    return round(amount_send * final_rate, 6)
