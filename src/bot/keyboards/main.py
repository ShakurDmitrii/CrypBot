from urllib.parse import urlparse

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup, WebAppInfo


def _is_valid_telegram_webapp_url(raw_url: str) -> bool:
    value = raw_url.strip()
    if not value:
        return False
    parsed = urlparse(value)
    return parsed.scheme == "https" and bool(parsed.netloc)


def main_menu_keyboard(mini_app_url: str = "", is_operator: bool = False) -> ReplyKeyboardMarkup:
    keyboard: list[list[KeyboardButton]] = [
        [KeyboardButton(text="Курс"), KeyboardButton(text="Рассчитать")],
        [KeyboardButton(text="Создать заявку"), KeyboardButton(text="История")],
        [KeyboardButton(text="Оферта"), KeyboardButton(text="AML проверка")],
    ]

    if _is_valid_telegram_webapp_url(mini_app_url):
        keyboard.append(
            [KeyboardButton(text="Мини-апп", web_app=WebAppInfo(url=mini_app_url.strip()))]
        )

    if is_operator:
        keyboard.append([KeyboardButton(text="Опер: Курсы+маржа"), KeyboardButton(text="Опер: Маржа")])
        keyboard.append([KeyboardButton(text="Опер: Статус заявки"), KeyboardButton(text="Опер: AML статус")])

    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def direction_keyboard(directions: list[str]) -> ReplyKeyboardMarkup:
    rows: list[list[KeyboardButton]] = []
    pair_row: list[KeyboardButton] = []

    for direction in directions:
        pair_row.append(KeyboardButton(text=direction))
        if len(pair_row) == 2:
            rows.append(pair_row)
            pair_row = []

    if pair_row:
        rows.append(pair_row)

    rows.append([KeyboardButton(text="Отмена")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def request_status_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="new"), KeyboardButton(text="waiting_payment")],
            [KeyboardButton(text="payment_received"), KeyboardButton(text="processing")],
            [KeyboardButton(text="done"), KeyboardButton(text="canceled")],
            [KeyboardButton(text="disputed"), KeyboardButton(text="Отмена")],
        ],
        resize_keyboard=True,
    )


def aml_status_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="pending"), KeyboardButton(text="low")],
            [KeyboardButton(text="medium"), KeyboardButton(text="high")],
            [KeyboardButton(text="rejected"), KeyboardButton(text="Отмена")],
        ],
        resize_keyboard=True,
    )
