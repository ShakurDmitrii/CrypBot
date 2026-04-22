from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Курс"), KeyboardButton(text="Рассчитать")],
            [KeyboardButton(text="Создать заявку"), KeyboardButton(text="История")],
            [KeyboardButton(text="Оферта"), KeyboardButton(text="AML проверка")],
        ],
        resize_keyboard=True,
    )
