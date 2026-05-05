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
        keyboard.append([KeyboardButton(text="Команды оператора")])

    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def operator_commands_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Курсы и маржа"), KeyboardButton(text="Маржа")],
            [KeyboardButton(text="Статус заявки"), KeyboardButton(text="AML статус")],
            [KeyboardButton(text="Назад")],
        ],
        resize_keyboard=True,
    )


def back_cancel_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Назад"), KeyboardButton(text="Отмена")],
        ],
        resize_keyboard=True,
    )


def request_confirm_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Подтвердить"), KeyboardButton(text="Изменить")],
            [KeyboardButton(text="Назад"), KeyboardButton(text="Отмена")],
        ],
        resize_keyboard=True,
    )


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
            [KeyboardButton(text="Новая"), KeyboardButton(text="Ожидает оплату")],
            [KeyboardButton(text="Оплата получена"), KeyboardButton(text="В обработке")],
            [KeyboardButton(text="Выполнена"), KeyboardButton(text="Отменена")],
            [KeyboardButton(text="Спор"), KeyboardButton(text="Отмена")],
        ],
        resize_keyboard=True,
    )


def aml_status_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Ожидает"), KeyboardButton(text="Низкий риск")],
            [KeyboardButton(text="Средний риск"), KeyboardButton(text="Высокий риск")],
            [KeyboardButton(text="Отклонено"), KeyboardButton(text="Отмена")],
        ],
        resize_keyboard=True,
    )
