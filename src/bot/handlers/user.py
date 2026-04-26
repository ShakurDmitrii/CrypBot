import re
import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, ReplyKeyboardMarkup

from src.bot.keyboards.main import (
    back_cancel_keyboard,
    direction_keyboard,
    main_menu_keyboard,
    request_confirm_keyboard,
)
from src.bot.states.request_flow import AmlFlow, CalcFlow, CreateRequestFlow
from src.config import get_settings
from src.db.session import SessionLocal
from src.services.app_settings import get_margin_percent
from src.services.exchange_requests import (
    create_aml_check,
    create_exchange_request,
    get_or_create_user,
    list_user_requests,
)
from src.services.rates import RateServiceError, available_directions, calc_receive, get_quote

router = Router()
settings = get_settings()
CANCEL_TEXT = "Отмена"
BACK_TEXT = "Назад"
CONFIRM_TEXT = "Подтвердить"
EDIT_TEXT = "Изменить"
logger = logging.getLogger(__name__)


def _is_operator_user(message: Message) -> bool:
    if message.from_user is None:
        return False
    return message.from_user.id in settings.operator_ids


def _menu(message: Message):
    return main_menu_keyboard(settings.bot_mini_app_url, is_operator=_is_operator_user(message))


def _back_cancel_menu() -> ReplyKeyboardMarkup:
    return back_cancel_keyboard()


def _directions_text() -> str:
    return "Выберите направление кнопкой ниже."


def _parse_amount(raw: str) -> float | None:
    cleaned = raw.replace(",", ".").strip()
    try:
        value = float(cleaned)
    except ValueError:
        return None
    if value <= 0:
        return None
    return value


def _parse_phone(raw: str) -> str | None:
    candidate = raw.strip()
    if not candidate:
        return None
    if not re.fullmatch(r"[0-9+\-()\s]{7,25}", candidate):
        return None
    digits = re.sub(r"\D", "", candidate)
    if len(digits) < 10:
        return None
    return candidate


def _operator_username_for_user() -> str:
    username = settings.bot_operator_username.strip()
    if not username:
        return ""
    if not username.startswith("@"):
        username = f"@{username}"
    return username


def _format_direction(direction: str) -> str:
    return direction.replace("->", " -> ")


def _operator_request_actions_keyboard(request_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⏳ В обработке",
                    callback_data=f"opreq:{request_id}:processing",
                ),
                InlineKeyboardButton(
                    text="✅ Выполнена",
                    callback_data=f"opreq:{request_id}:done",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отменена",
                    callback_data=f"opreq:{request_id}:canceled",
                ),
            ],
        ]
    )


async def _build_request_preview_text(
    direction: str,
    amount_send: float,
    request_full_name: str,
    request_phone: str,
    requisites: str,
) -> str | None:
    try:
        async with SessionLocal() as session:
            margin_percent = await get_margin_percent(session, settings.bot_margin_percent)
        quote = await get_quote(direction, margin_percent, settings)
    except RateServiceError:
        return None
    amount_receive = calc_receive(amount_send, quote.final_rate)
    return (
        "<b>Проверьте заявку</b>\n\n"
        f"Направление: <b>{_format_direction(direction)}</b>\n"
        f"Отправка: <code>{amount_send}</code>\n"
        f"Итоговый курс: <code>{quote.final_rate:.6f}</code>\n"
        f"К получению: <code>{amount_receive}</code>\n\n"
        f"ФИО: {request_full_name}\n"
        f"Телефон: {request_phone}\n"
        f"Реквизиты: {requisites}"
    )


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "Операционный бот обменника запущен.\nВыберите действие в меню.",
        reply_markup=_menu(message),
    )


@router.message(StateFilter("*"), F.text == CANCEL_TEXT)
async def cancel_flow(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Действие отменено.", reply_markup=_menu(message))


@router.message(StateFilter(CalcFlow.waiting_direction), F.text == BACK_TEXT)
async def calc_back_from_direction(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Возврат в главное меню.", reply_markup=_menu(message))


@router.message(StateFilter(CalcFlow.waiting_amount), F.text == BACK_TEXT)
async def calc_back_from_amount(message: Message, state: FSMContext) -> None:
    await state.set_state(CalcFlow.waiting_direction)
    await message.answer(
        "Шаг 1/2. Выберите направление кнопкой ниже.",
        reply_markup=direction_keyboard(available_directions()),
    )


@router.message(StateFilter(CreateRequestFlow.waiting_direction), F.text == BACK_TEXT)
async def request_back_from_direction(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Возврат в главное меню.", reply_markup=_menu(message))


@router.message(StateFilter(CreateRequestFlow.waiting_amount), F.text == BACK_TEXT)
async def request_back_from_amount(message: Message, state: FSMContext) -> None:
    await state.set_state(CreateRequestFlow.waiting_direction)
    await message.answer(
        "Шаг 1/5. Выберите направление кнопкой ниже.",
        reply_markup=direction_keyboard(available_directions()),
    )


@router.message(StateFilter(CreateRequestFlow.waiting_full_name), F.text == BACK_TEXT)
async def request_back_from_full_name(message: Message, state: FSMContext) -> None:
    await state.set_state(CreateRequestFlow.waiting_amount)
    await message.answer("Шаг 2/5. Введите сумму отправки.", reply_markup=_back_cancel_menu())


@router.message(StateFilter(CreateRequestFlow.waiting_phone), F.text == BACK_TEXT)
async def request_back_from_phone(message: Message, state: FSMContext) -> None:
    await state.set_state(CreateRequestFlow.waiting_full_name)
    await message.answer("Шаг 3/5. Введите ФИО получателя.", reply_markup=_back_cancel_menu())


@router.message(StateFilter(CreateRequestFlow.waiting_requisites), F.text == BACK_TEXT)
async def request_back_from_requisites(message: Message, state: FSMContext) -> None:
    await state.set_state(CreateRequestFlow.waiting_phone)
    await message.answer("Шаг 4/5. Введите номер телефона для связи.", reply_markup=_back_cancel_menu())


@router.message(StateFilter(CreateRequestFlow.waiting_confirm), F.text == BACK_TEXT)
async def request_back_from_confirm(message: Message, state: FSMContext) -> None:
    await state.set_state(CreateRequestFlow.waiting_requisites)
    await message.answer("Шаг 5/5. Отправьте реквизиты для получения средств.", reply_markup=_back_cancel_menu())


@router.message(Command("myid"))
async def cmd_myid(message: Message) -> None:
    if message.from_user is None:
        await message.answer("Не удалось определить user id.")
        return
    await message.answer(f"Ваш user id: {message.from_user.id}")


@router.message(Command("chatid"))
async def cmd_chatid(message: Message) -> None:
    await message.answer(f"ID этого чата: {message.chat.id}")


@router.message(F.text == "Курс")
async def show_rate(message: Message) -> None:
    async with SessionLocal() as session:
        margin_percent = await get_margin_percent(session, settings.bot_margin_percent)

    show_margin = _is_operator_user(message)
    blocks: list[str] = []
    for direction in available_directions():
        try:
            quote = await get_quote(direction, margin_percent, settings)
        except RateServiceError:
            await message.answer(
                "Сервис курсов временно недоступен. Попробуйте еще раз через пару секунд.",
                reply_markup=_menu(message),
            )
            return
        base_line = f"Базовый курс: <code>{quote.base_rate:.6f}</code>\n" if show_margin else ""
        margin_line = f"Маржа: <code>+{quote.margin_percent:.2f}%</code>\n" if show_margin else ""
        blocks.append(
            (
                f"<b>{_format_direction(direction)}</b>\n"
                f"{base_line}"
                f"{margin_line}"
                f"Итоговый курс: <code>{quote.final_rate:.6f}</code>"
            )
        )

    text = "<b>Актуальные курсы</b>\n\n" + "\n\n".join(blocks)
    await message.answer(text, reply_markup=_menu(message))


@router.message(F.text == "Рассчитать")
async def start_calc(message: Message, state: FSMContext) -> None:
    await state.set_state(CalcFlow.waiting_direction)
    await message.answer(
        "Шаг 1/2. " + _directions_text(),
        reply_markup=direction_keyboard(available_directions()),
    )


@router.message(CalcFlow.waiting_direction)
async def calc_set_direction(message: Message, state: FSMContext) -> None:
    direction = (message.text or "").strip()
    if direction not in available_directions():
        await message.answer(
            "Неизвестное направление. Выберите вариант кнопкой.",
            reply_markup=direction_keyboard(available_directions()),
        )
        return
    await state.update_data(direction=direction)
    await state.set_state(CalcFlow.waiting_amount)
    await message.answer("Шаг 2/2. Введите сумму отправки.", reply_markup=_back_cancel_menu())


@router.message(CalcFlow.waiting_amount)
async def calc_set_amount(message: Message, state: FSMContext) -> None:
    amount = _parse_amount(message.text or "")
    if amount is None:
        await message.answer("Введите корректную сумму числом, например 1500 или 1500.50")
        return

    data = await state.get_data()
    direction = data["direction"]
    try:
        async with SessionLocal() as session:
            margin_percent = await get_margin_percent(session, settings.bot_margin_percent)
        quote = await get_quote(direction, margin_percent, settings)
    except RateServiceError:
        await message.answer("Сервис курсов временно недоступен. Попробуйте позже.", reply_markup=_menu(message))
        return
    amount_receive = calc_receive(amount, quote.final_rate)
    await state.clear()
    await message.answer(
        (
            f"Расчет:\n"
            f"Направление: {direction}\n"
            f"Сумма отправки: {amount}\n"
            f"Итоговый курс: {quote.final_rate:.6f}\n"
            f"К получению: {amount_receive}"
        ),
        reply_markup=_menu(message),
    )


@router.message(F.text == "Создать заявку")
async def create_request_start(message: Message, state: FSMContext) -> None:
    await state.set_state(CreateRequestFlow.waiting_direction)
    await message.answer(
        "Создание заявки.\nШаг 1/5. " + _directions_text(),
        reply_markup=direction_keyboard(available_directions()),
    )


@router.message(CreateRequestFlow.waiting_direction)
async def request_set_direction(message: Message, state: FSMContext) -> None:
    direction = (message.text or "").strip()
    if direction not in available_directions():
        await message.answer(
            "Неизвестное направление. Выберите вариант кнопкой.",
            reply_markup=direction_keyboard(available_directions()),
        )
        return
    await state.update_data(direction=direction)
    await state.set_state(CreateRequestFlow.waiting_amount)
    await message.answer("Шаг 2/5. Введите сумму отправки.", reply_markup=_back_cancel_menu())


@router.message(CreateRequestFlow.waiting_amount)
async def request_set_amount(message: Message, state: FSMContext) -> None:
    amount = _parse_amount(message.text or "")
    if amount is None:
        await message.answer("Введите корректную сумму числом.")
        return
    await state.update_data(amount=amount)
    await state.set_state(CreateRequestFlow.waiting_full_name)
    await message.answer("Шаг 3/5. Введите ФИО получателя.", reply_markup=_back_cancel_menu())


@router.message(CreateRequestFlow.waiting_full_name)
async def request_set_full_name(message: Message, state: FSMContext) -> None:
    full_name = (message.text or "").strip()
    if len(full_name) < 5:
        await message.answer("Введите полное ФИО, минимум 5 символов.")
        return
    await state.update_data(request_full_name=full_name)
    await state.set_state(CreateRequestFlow.waiting_phone)
    await message.answer("Шаг 4/5. Введите номер телефона для связи.", reply_markup=_back_cancel_menu())


@router.message(CreateRequestFlow.waiting_phone)
async def request_set_phone(message: Message, state: FSMContext) -> None:
    phone = _parse_phone(message.text or "")
    if phone is None:
        await message.answer("Введите корректный номер телефона, например +79991234567.")
        return
    await state.update_data(request_phone=phone)
    await state.set_state(CreateRequestFlow.waiting_requisites)
    await message.answer("Шаг 5/5. Отправьте реквизиты для получения средств.", reply_markup=_back_cancel_menu())


@router.message(CreateRequestFlow.waiting_requisites)
async def request_set_requisites(message: Message, state: FSMContext) -> None:
    requisites = (message.text or "").strip()
    if not requisites:
        await message.answer("Реквизиты не могут быть пустыми.")
        return

    data = await state.get_data()
    direction = data.get("direction")
    amount_raw = data.get("amount")
    request_full_name = data.get("request_full_name")
    request_phone = data.get("request_phone")

    if not direction or amount_raw is None or not request_full_name or not request_phone:
        await state.clear()
        await message.answer(
            "Сессия заявки устарела. Пожалуйста, начните заново через кнопку «Создать заявку».",
            reply_markup=_menu(message),
        )
        return

    amount_send = float(amount_raw)
    await state.update_data(request_requisites=requisites)
    preview = await _build_request_preview_text(
        direction=direction,
        amount_send=amount_send,
        request_full_name=request_full_name,
        request_phone=request_phone,
        requisites=requisites,
    )
    if preview is None:
        await message.answer("Сервис курсов временно недоступен. Попробуйте позже.", reply_markup=_menu(message))
        return

    await state.set_state(CreateRequestFlow.waiting_confirm)
    await message.answer(
        "Шаг подтверждения.\n" + preview + "\n\nПодтвердить создание заявки?",
        reply_markup=request_confirm_keyboard(),
    )


@router.message(CreateRequestFlow.waiting_confirm)
async def request_confirm(message: Message, state: FSMContext) -> None:
    choice = (message.text or "").strip()
    if choice == EDIT_TEXT:
        await state.set_state(CreateRequestFlow.waiting_direction)
        await message.answer(
            "Ок, изменяем заявку.\nШаг 1/5. Выберите направление кнопкой ниже.",
            reply_markup=direction_keyboard(available_directions()),
        )
        return

    if choice != CONFIRM_TEXT:
        await message.answer("Выберите действие кнопкой ниже.", reply_markup=request_confirm_keyboard())
        return

    if message.from_user is None:
        await state.clear()
        await message.answer("Не удалось определить пользователя. Начните заявку заново.", reply_markup=_menu(message))
        return

    data = await state.get_data()
    direction = data.get("direction")
    amount_raw = data.get("amount")
    request_full_name = data.get("request_full_name")
    request_phone = data.get("request_phone")
    requisites = data.get("request_requisites")
    if not direction or amount_raw is None or not request_full_name or not request_phone or not requisites:
        await state.clear()
        await message.answer(
            "Сессия заявки устарела. Пожалуйста, начните заново через кнопку «Создать заявку».",
            reply_markup=_menu(message),
        )
        return

    amount_send = float(amount_raw)
    try:
        async with SessionLocal() as session:
            margin_percent = await get_margin_percent(session, settings.bot_margin_percent)
        quote = await get_quote(direction, margin_percent, settings)
    except RateServiceError:
        await message.answer("Сервис курсов временно недоступен. Попробуйте позже.", reply_markup=_menu(message))
        return
    amount_receive = calc_receive(amount_send, quote.final_rate)

    requisites_for_storage = (
        f"ФИО: {request_full_name}\n"
        f"Телефон: {request_phone}\n"
        f"Реквизиты: {requisites}"
    )

    async with SessionLocal() as session:
        user = await get_or_create_user(
            session=session,
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            full_name=request_full_name,
        )
        request = await create_exchange_request(
            session=session,
            user_id=user.id,
            direction=direction,
            amount_send=amount_send,
            amount_receive=amount_receive,
            base_rate=quote.base_rate,
            margin_percent=quote.margin_percent,
            final_rate=quote.final_rate,
            user_requisites=requisites_for_storage,
        )
        await session.commit()

    try:
        await message.bot.send_message(
            chat_id=settings.bot_operator_chat_id,
            text=(
                f"Новая заявка #{request.id}\n"
                f"Статус: Новая\n"
                f"user_id={message.from_user.id}\n"
                f"username={('@' + message.from_user.username) if message.from_user.username else '-'}\n"
                f"Направление: {direction}\n"
                f"Отправка: {amount_send}\n"
                f"Получение: {amount_receive}\n"
                f"Курс: {quote.final_rate:.6f}\n"
                f"ФИО: {request_full_name}\n"
                f"Телефон: {request_phone}\n"
                f"Реквизиты: {requisites}"
            ),
            reply_markup=_operator_request_actions_keyboard(request.id),
        )
    except (TelegramBadRequest, TelegramForbiddenError) as exc:
        logger.error("Failed to deliver request #%s to operator chat: %s", request.id, exc)

    await state.clear()
    operator_username = _operator_username_for_user()
    operator_line = f"\nОператор: {operator_username}" if operator_username else ""
    await message.answer(
        f"Заявка #{request.id} принята.{operator_line}\nМы уведомим вас при смене статуса.",
        reply_markup=_menu(message),
    )


@router.message(F.text == "История")
async def show_history(message: Message) -> None:
    async with SessionLocal() as session:
        user = await get_or_create_user(
            session=session,
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            full_name=message.from_user.full_name,
        )
        rows = await list_user_requests(session, user.id, limit=10)
        await session.commit()

    if not rows:
        await message.answer("История пуста. У вас пока нет заявок.", reply_markup=_menu(message))
        return

    lines = ["Последние заявки:"]
    for row in rows:
        lines.append(
            f"#{row.id} {row.direction} | send={row.amount_send} receive={row.amount_receive} | {row.status.value}"
        )
    await message.answer("\n".join(lines), reply_markup=_menu(message))


@router.message(F.text == "Оферта")
async def show_offer(message: Message) -> None:
    await message.answer(f"Публичная оферта: {settings.bot_offer_url}", reply_markup=_menu(message))


@router.message(F.text == "AML проверка")
async def aml_start(message: Message, state: FSMContext) -> None:
    await state.set_state(AmlFlow.waiting_check_type)
    await message.answer("Введите тип проверки: address или tx")


@router.message(AmlFlow.waiting_check_type)
async def aml_set_type(message: Message, state: FSMContext) -> None:
    check_type = (message.text or "").strip().lower()
    if check_type not in {"address", "tx"}:
        await message.answer("Допустимые типы: address или tx")
        return
    await state.update_data(check_type=check_type)
    await state.set_state(AmlFlow.waiting_value)
    await message.answer("Введите адрес кошелька или hash транзакции.")


@router.message(AmlFlow.waiting_value)
async def aml_set_value(message: Message, state: FSMContext) -> None:
    value = (message.text or "").strip()
    if not value:
        await message.answer("Значение не может быть пустым.")
        return

    data = await state.get_data()
    check_type = data["check_type"]
    async with SessionLocal() as session:
        aml = await create_aml_check(
            session=session,
            telegram_user_id=message.from_user.id,
            check_type=check_type,
            value=value,
        )
        await session.commit()

    try:
        await message.bot.send_message(
            chat_id=settings.bot_operator_chat_id,
            text=(
                f"AML запрос #{aml.id}\n"
                f"user_id={message.from_user.id}\n"
                f"type={check_type}\n"
                f"value={value}\n"
                f"Для обновления: /aml_status {aml.id} low|medium|high|rejected [comment]"
            ),
        )
    except (TelegramBadRequest, TelegramForbiddenError) as exc:
        logger.error("Failed to deliver AML request #%s to operator chat: %s", aml.id, exc)
    await state.clear()
    await message.answer(
        f"AML-запрос #{aml.id} принят. Результат сообщим отдельно.",
        reply_markup=_menu(message),
    )
