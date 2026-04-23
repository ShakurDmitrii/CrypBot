from aiogram.types import KeyboardButton, ReplyKeyboardMarkup, WebAppInfo


def main_menu_keyboard(mini_app_url: str = "") -> ReplyKeyboardMarkup:
    keyboard: list[list[KeyboardButton]] = [
        [KeyboardButton(text="Курс"), KeyboardButton(text="Рассчитать")],
        [KeyboardButton(text="Создать заявку"), KeyboardButton(text="История")],
        [KeyboardButton(text="Оферта"), KeyboardButton(text="AML проверка")],
    ]

    if mini_app_url.strip():
        keyboard.append(
            [KeyboardButton(text="Мини-апп", web_app=WebAppInfo(url=mini_app_url.strip()))]
        )

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
