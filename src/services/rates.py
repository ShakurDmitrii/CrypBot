from dataclasses import dataclass


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


def available_directions() -> list[str]:
    return list(BASE_RATES.keys())


def get_quote(direction: str, margin_percent: float) -> RateQuote:
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
