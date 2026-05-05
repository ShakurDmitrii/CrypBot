from datetime import datetime
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, KeyboardButton, Message, ReplyKeyboardMarkup
from sqlalchemy import select

from src.bot.keyboards.main import (
    aml_status_keyboard,
    main_menu_keyboard,
    operator_commands_keyboard,
    request_status_keyboard,
)
from src.bot.states.request_flow import OperatorFlow
from src.config import get_settings
from src.db.models import AmlCheck, AmlStatus, ExchangeRequest, RequestStatus, User
from src.db.session import SessionLocal
from src.services.app_settings import get_margin_percent, set_margin_percent
from src.services.exchange_requests import get_request_by_id, update_request_status
from src.services.rates import RateServiceError, available_directions, get_quote

router = Router()
settings = get_settings()
CANCEL_TEXT = "Отмена"
BACK_TEXT = "Назад"
OPEN_OPERATOR_MENU_TEXT = "Команды оператора"

STATUS_ALIASES: dict[str, RequestStatus] = {
    "new": RequestStatus.NEW,
    "новая": RequestStatus.NEW,
    "waiting_payment": RequestStatus.WAITING_PAYMENT,
    "ожидает оплату": RequestStatus.WAITING_PAYMENT,
    "payment_received": RequestStatus.PAYMENT_RECEIVED,
    "оплата получена": RequestStatus.PAYMENT_RECEIVED,
    "processing": RequestStatus.PROCESSING,
    "в обработке": RequestStatus.PROCESSING,
    "done": RequestStatus.DONE,
    "выполнена": RequestStatus.DONE,
    "canceled": RequestStatus.CANCELED,
    "cancelled": RequestStatus.CANCELED,
    "отменена": RequestStatus.CANCELED,
    "disputed": RequestStatus.DISPUTED,
    "спор": RequestStatus.DISPUTED,
}

AML_ALIASES: dict[str, AmlStatus] = {
    "pending": AmlStatus.PENDING,
    "ожидает": AmlStatus.PENDING,
    "low": AmlStatus.LOW,
    "низкий риск": AmlStatus.LOW,
    "medium": AmlStatus.MEDIUM,
    "средний риск": AmlStatus.MEDIUM,
    "high": AmlStatus.HIGH,
    "высокий риск": AmlStatus.HIGH,
    "rejected": AmlStatus.REJECTED,
    "отклонено": AmlStatus.REJECTED,
}


def _is_operator(message: Message) -> bool:
    if message.from_user is None:
        return False
    return message.from_user.id in settings.operator_ids


def _mini_app_url_for_message(message: Message | None) -> str:
    base_url = settings.bot_mini_app_url.strip()
    if not base_url:
        return base_url
    telegram_id = message.from_user.id if message and message.from_user else None
    if telegram_id is None:
        return base_url
    parsed = urlparse(base_url)
    query_pairs = parse_qsl(parsed.query, keep_blank_values=True)
    query_pairs = [(key, value) for key, value in query_pairs if key != "telegram_id"]
    query_pairs.append(("telegram_id", str(telegram_id)))
    return urlunparse(parsed._replace(query=urlencode(query_pairs)))


def _operator_menu(message: Message | None = None) -> object:
    return main_menu_keyboard(_mini_app_url_for_message(message), is_operator=True)


def _operator_commands_menu() -> object:
    return operator_commands_keyboard()


def _cancel_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=CANCEL_TEXT)]], resize_keyboard=True)


def _format_direction(direction: str) -> str:
    return direction.replace("->", " -> ")


REQUEST_STATUS_TITLES: dict[RequestStatus, str] = {
    RequestStatus.NEW: "Новая",
    RequestStatus.WAITING_PAYMENT: "Ожидает оплату",
    RequestStatus.PAYMENT_RECEIVED: "Оплата получена",
    RequestStatus.PROCESSING: "В обработке",
    RequestStatus.DONE: "Выполнена",
    RequestStatus.CANCELED: "Отменена",
    RequestStatus.DISPUTED: "Спор",
}

AML_STATUS_TITLES: dict[AmlStatus, str] = {
    AmlStatus.PENDING: "Ожидает",
    AmlStatus.LOW: "Низкий риск",
    AmlStatus.MEDIUM: "Средний риск",
    AmlStatus.HIGH: "Высокий риск",
    AmlStatus.REJECTED: "Отклонено",
}


def _format_created_at(value: datetime | None) -> str:
    if value is None:
        return "-"
    return value.strftime("%d.%m.%Y %H:%M")


def _request_status_title(status: RequestStatus) -> str:
    return REQUEST_STATUS_TITLES.get(status, status.value)


def _aml_status_title(status: AmlStatus) -> str:
    return AML_STATUS_TITLES.get(status, status.value)


async def _send_requests_history(message: Message) -> None:
    async with SessionLocal() as session:
        rows = await session.execute(
            select(ExchangeRequest, User)
            .join(User, ExchangeRequest.user_id == User.id, isouter=True)
            .order_by(ExchangeRequest.created_at.desc())
        )
        items = rows.all()

    if not items:
        await message.answer("Пока нет ни одной заявки.")
        return

    lines: list[str] = []
    for request, user in items:
        user_ref = "-"
        if user is not None:
            user_ref = f"@{user.username}" if user.username else f"id:{user.telegram_id}"
        lines.append(
            (
                f"#{request.id} | {_format_created_at(request.created_at)}\n"
                f"{_format_direction(request.direction)} | {request.amount_send:.2f} -> {request.amount_receive:.2f}\n"
                f"Статус: {_request_status_title(request.status)} | Пользователь: {user_ref}"
            )
        )

    chunk = "📋 <b>История заявок</b>\n\n"
    for line in lines:
        block = f"{line}\n\n"
        if len(chunk) + len(block) > 3500:
            await message.answer(chunk)
            chunk = block
        else:
            chunk += block
    if chunk.strip():
        await message.answer(chunk)


@router.callback_query(F.data.startswith("opreq:"))
async def operator_quick_request_status(callback: CallbackQuery) -> None:
    if callback.from_user is None or callback.from_user.id not in settings.operator_ids:
        await callback.answer("Доступно только оператору.", show_alert=True)
        return

    data = callback.data or ""
    parts = data.split(":")
    if len(parts) != 3:
        await callback.answer("Некорректные данные кнопки.", show_alert=True)
        return

    _, request_id_raw, status_raw = parts
    if not request_id_raw.isdigit():
        await callback.answer("Некорректный номер заявки.", show_alert=True)
        return
    status = STATUS_ALIASES.get(status_raw.strip().lower())
    if status is None:
        await callback.answer("Неизвестный статус.", show_alert=True)
        return

    request_id = int(request_id_raw)
    async with SessionLocal() as session:
        request = await get_request_by_id(session, request_id)
        if request is None:
            await callback.answer("Заявка не найдена.", show_alert=True)
            return
        if request.status == status:
            await callback.answer("У заявки уже этот статус.")
            return

        await update_request_status(
            session=session,
            request=request,
            new_status=status,
            changed_by=f"operator:{callback.from_user.id}",
            comment="Изменено кнопкой оператора",
        )
        user = await session.scalar(select(User).where(User.id == request.user_id))
        await session.commit()

    status_label = _request_status_title(status)
    await callback.answer(f"Статус обновлен: {status_label}")
    if callback.message and getattr(callback.message, "chat", None):
        await callback.bot.send_message(
            chat_id=callback.message.chat.id,
            text=f"Заявка #{request_id}: статус изменен на «{status_label}».",
        )
    if user:
        await callback.bot.send_message(
            chat_id=user.telegram_id,
            text=f"Заявка #{request_id}: новый статус {status_label}\nКомментарий: Изменено оператором",
        )


@router.message(
    StateFilter(
        OperatorFlow.waiting_margin_value,
        OperatorFlow.waiting_request_id,
        OperatorFlow.waiting_request_status,
        OperatorFlow.waiting_request_comment,
        OperatorFlow.waiting_aml_id,
        OperatorFlow.waiting_aml_status,
        OperatorFlow.waiting_aml_comment,
    ),
    F.text == CANCEL_TEXT,
)
async def operator_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Операция отменена.", reply_markup=_operator_commands_menu())


@router.message(F.text == OPEN_OPERATOR_MENU_TEXT)
async def operator_open_menu(message: Message, state: FSMContext) -> None:
    if not _is_operator(message):
        await message.answer("Действие доступно только оператору.")
        return

    await state.clear()
    await message.answer("Выберите действие оператора:", reply_markup=_operator_commands_menu())


@router.message(F.text == BACK_TEXT)
async def operator_back_to_main(message: Message, state: FSMContext) -> None:
    if not _is_operator(message):
        return
    await state.clear()
    await message.answer("Главное меню.", reply_markup=_operator_menu(message))


@router.message(Command("margin"))
async def set_bot_margin(message: Message, command: CommandObject) -> None:
    if not _is_operator(message):
        await message.answer("Команда доступна только оператору.")
        return

    if not command.args:
        async with SessionLocal() as session:
            margin_percent = await get_margin_percent(session, settings.bot_margin_percent)
        await message.answer(
            f"Текущая маржа: {margin_percent:.2f}%\n"
            f"Изменить: /margin &lt;percent&gt;\n"
            f"Пример: /margin 2.5"
        )
        return

    raw_value = command.args.strip().replace(",", ".")
    try:
        margin_percent = float(raw_value)
    except ValueError:
        await message.answer("Некорректное значение. Пример: /margin 2.5")
        return

    if margin_percent < 0:
        await message.answer("Маржа не может быть отрицательной.")
        return

    async with SessionLocal() as session:
        await set_margin_percent(session, margin_percent)
        await session.commit()

    await message.answer(f"Маржа обновлена: {margin_percent:.2f}%")


@router.message(F.text.in_({"Опер: Курсы+маржа", "Курсы и маржа"}))
async def operator_show_rates(message: Message) -> None:
    if not _is_operator(message):
        await message.answer("Действие доступно только оператору.")
        return

    async with SessionLocal() as session:
        margin_percent = await get_margin_percent(session, settings.bot_margin_percent)

    blocks: list[str] = []
    for direction in available_directions():
        try:
            quote = await get_quote(direction, margin_percent, settings)
        except RateServiceError:
            await message.answer("Сервис курсов временно недоступен.", reply_markup=_operator_commands_menu())
            return
        blocks.append(
            (
                f"<b>{_format_direction(direction)}</b>\n"
                f"Базовый курс: <code>{quote.base_rate:.6f}</code>\n"
                f"Маржа: <code>+{quote.margin_percent:.2f}%</code>\n"
                f"Итоговый курс: <code>{quote.final_rate:.6f}</code>"
            )
        )

    await message.answer(
        "<b>Курсы для оператора</b>\n\n" + "\n\n".join(blocks),
        reply_markup=_operator_commands_menu(),
    )


@router.message(F.text.in_({"Опер: Маржа", "Маржа"}))
async def operator_margin_start(message: Message, state: FSMContext) -> None:
    if not _is_operator(message):
        await message.answer("Действие доступно только оператору.")
        return

    async with SessionLocal() as session:
        margin_percent = await get_margin_percent(session, settings.bot_margin_percent)
    await state.set_state(OperatorFlow.waiting_margin_value)
    await message.answer(
        f"Текущая маржа: {margin_percent:.2f}%\nВведите новое значение (например, 2.5).",
        reply_markup=_cancel_menu(),
    )


@router.message(OperatorFlow.waiting_margin_value)
async def operator_margin_apply(message: Message, state: FSMContext) -> None:
    if not _is_operator(message):
        await state.clear()
        await message.answer("Действие доступно только оператору.")
        return

    raw_value = (message.text or "").strip().replace(",", ".")
    try:
        margin_percent = float(raw_value)
    except ValueError:
        await message.answer("Некорректное значение. Введите число, например 1.5.", reply_markup=_cancel_menu())
        return
    if margin_percent < 0:
        await message.answer("Маржа не может быть отрицательной.", reply_markup=_cancel_menu())
        return

    async with SessionLocal() as session:
        await set_margin_percent(session, margin_percent)
        await session.commit()
    await state.clear()
    await message.answer(f"Маржа обновлена: {margin_percent:.2f}%", reply_markup=_operator_commands_menu())


@router.message(F.text.in_({"Опер: Статус заявки", "Статус заявки"}))
async def operator_status_start(message: Message, state: FSMContext) -> None:
    if not _is_operator(message):
        await message.answer("Действие доступно только оператору.")
        return

    await _send_requests_history(message)
    await state.set_state(OperatorFlow.waiting_request_id)
    await message.answer("Введите номер заявки (ID из списка выше).", reply_markup=_cancel_menu())


@router.message(F.text == "История")
async def operator_history(message: Message) -> None:
    if not _is_operator(message):
        await message.answer("Действие доступно только оператору.")
        return

    await _send_requests_history(message)


@router.message(OperatorFlow.waiting_request_id)
async def operator_status_set_request_id(message: Message, state: FSMContext) -> None:
    if not _is_operator(message):
        await state.clear()
        await message.answer("Действие доступно только оператору.")
        return

    raw = (message.text or "").strip()
    if not raw.isdigit():
        await message.answer("request_id должен быть числом.", reply_markup=_cancel_menu())
        return
    await state.update_data(request_id=int(raw))
    await state.set_state(OperatorFlow.waiting_request_status)
    await message.answer("Выберите новый статус заявки:", reply_markup=request_status_keyboard())


@router.message(OperatorFlow.waiting_request_status)
async def operator_status_set_status(message: Message, state: FSMContext) -> None:
    if not _is_operator(message):
        await state.clear()
        await message.answer("Действие доступно только оператору.")
        return

    status_raw = (message.text or "").strip().lower()
    status = STATUS_ALIASES.get(status_raw)
    if status is None:
        await message.answer("Выберите статус кнопкой.", reply_markup=request_status_keyboard())
        return

    await state.update_data(request_status=status.value)
    await state.set_state(OperatorFlow.waiting_request_comment)
    await message.answer("Комментарий к статусу (или '-' без комментария):", reply_markup=_cancel_menu())


@router.message(OperatorFlow.waiting_request_comment)
async def operator_status_apply(message: Message, state: FSMContext) -> None:
    if not _is_operator(message):
        await state.clear()
        await message.answer("Действие доступно только оператору.")
        return

    data = await state.get_data()
    request_id = data.get("request_id")
    status_value = data.get("request_status")
    if request_id is None or not status_value:
        await state.clear()
        await message.answer(
            "Сессия обновления статуса устарела. Повторите заново.",
            reply_markup=_operator_commands_menu(),
        )
        return

    status = STATUS_ALIASES[status_value]
    comment_raw = (message.text or "").strip()
    comment = None if comment_raw in {"", "-"} else comment_raw

    async with SessionLocal() as session:
        request = await get_request_by_id(session, request_id)
        if request is None:
            await state.clear()
            await message.answer(f"Заявка #{request_id} не найдена.", reply_markup=_operator_commands_menu())
            return

        await update_request_status(
            session=session,
            request=request,
            new_status=status,
            changed_by=f"operator:{message.from_user.id}",
            comment=comment,
        )
        user = await session.scalar(select(User).where(User.id == request.user_id))
        await session.commit()

    await state.clear()
    status_label = _request_status_title(status)
    await message.answer(
        f"Статус заявки #{request_id} обновлен: {status_label}",
        reply_markup=_operator_commands_menu(),
    )
    if user:
        await message.bot.send_message(
            chat_id=user.telegram_id,
            text=f"Заявка #{request_id}: новый статус {status_label}\nКомментарий: {comment or '-'}",
        )


@router.message(F.text.in_({"Опер: AML статус", "AML статус"}))
async def operator_aml_start(message: Message, state: FSMContext) -> None:
    if not _is_operator(message):
        await message.answer("Действие доступно только оператору.")
        return

    await state.set_state(OperatorFlow.waiting_aml_id)
    await message.answer("Введите номер AML запроса (aml_id).", reply_markup=_cancel_menu())


@router.message(OperatorFlow.waiting_aml_id)
async def operator_aml_set_id(message: Message, state: FSMContext) -> None:
    if not _is_operator(message):
        await state.clear()
        await message.answer("Действие доступно только оператору.")
        return

    raw = (message.text or "").strip()
    if not raw.isdigit():
        await message.answer("aml_id должен быть числом.", reply_markup=_cancel_menu())
        return
    await state.update_data(aml_id=int(raw))
    await state.set_state(OperatorFlow.waiting_aml_status)
    await message.answer("Выберите AML статус:", reply_markup=aml_status_keyboard())


@router.message(OperatorFlow.waiting_aml_status)
async def operator_aml_set_status(message: Message, state: FSMContext) -> None:
    if not _is_operator(message):
        await state.clear()
        await message.answer("Действие доступно только оператору.")
        return

    status_raw = (message.text or "").strip().lower()
    status = AML_ALIASES.get(status_raw)
    if status is None:
        await message.answer("Выберите AML статус кнопкой.", reply_markup=aml_status_keyboard())
        return

    await state.update_data(aml_status=status.value)
    await state.set_state(OperatorFlow.waiting_aml_comment)
    await message.answer("Комментарий к AML (или '-' без комментария):", reply_markup=_cancel_menu())


@router.message(OperatorFlow.waiting_aml_comment)
async def operator_aml_apply(message: Message, state: FSMContext) -> None:
    if not _is_operator(message):
        await state.clear()
        await message.answer("Действие доступно только оператору.")
        return

    data = await state.get_data()
    aml_id = data.get("aml_id")
    status_value = data.get("aml_status")
    if aml_id is None or not status_value:
        await state.clear()
        await message.answer(
            "Сессия AML обновления устарела. Повторите заново.",
            reply_markup=_operator_commands_menu(),
        )
        return

    status = AML_ALIASES[status_value]
    note_raw = (message.text or "").strip()
    note = None if note_raw in {"", "-"} else note_raw

    async with SessionLocal() as session:
        aml = await session.scalar(select(AmlCheck).where(AmlCheck.id == aml_id))
        if aml is None:
            await state.clear()
            await message.answer(f"AML запрос #{aml_id} не найден.", reply_markup=_operator_commands_menu())
            return
        aml.status = status
        aml.result_note = note
        await session.commit()

    await state.clear()
    status_label = _aml_status_title(status)
    await message.answer(f"AML запрос #{aml_id} обновлен: {status_label}", reply_markup=_operator_commands_menu())
    await message.bot.send_message(
        chat_id=aml.telegram_user_id,
        text=f"AML запрос #{aml_id}: результат {status_label}\nКомментарий: {note or '-'}",
    )


@router.message(Command("status"))
async def set_request_status(message: Message, command: CommandObject) -> None:
    if not _is_operator(message):
        await message.answer("Команда доступна только оператору.")
        return

    if not command.args:
        await message.answer("Формат: /status &lt;request_id&gt; &lt;status&gt; [comment]")
        return

    parts = command.args.split(maxsplit=2)
    if len(parts) < 2:
        await message.answer("Формат: /status &lt;request_id&gt; &lt;status&gt; [comment]")
        return

    request_id_raw, status_raw = parts[0], parts[1].lower()
    comment = parts[2] if len(parts) == 3 else None
    if not request_id_raw.isdigit():
        await message.answer("request_id должен быть числом.")
        return

    status = STATUS_ALIASES.get(status_raw)
    if status is None:
        allowed = ", ".join(status.value for status in RequestStatus)
        await message.answer(f"Неизвестный статус. Допустимые: {allowed}")
        return

    request_id = int(request_id_raw)
    async with SessionLocal() as session:
        request = await get_request_by_id(session, request_id)
        if request is None:
            await message.answer(f"Заявка #{request_id} не найдена.")
            return

        await update_request_status(
            session=session,
            request=request,
            new_status=status,
            changed_by=f"operator:{message.from_user.id}",
            comment=comment,
        )
        user = await session.scalar(select(User).where(User.id == request.user_id))
        await session.commit()

    status_label = _request_status_title(status)
    await message.answer(f"Статус заявки #{request_id} обновлен: {status_label}")
    if user:
        note = comment or "-"
        await message.bot.send_message(
            chat_id=user.telegram_id,
            text=f"Заявка #{request_id}: новый статус {status_label}\nКомментарий: {note}",
        )


@router.message(Command("aml_status"))
async def set_aml_status(message: Message, command: CommandObject) -> None:
    if not _is_operator(message):
        await message.answer("Команда доступна только оператору.")
        return

    if not command.args:
        await message.answer("Формат: /aml_status &lt;aml_id&gt; &lt;status&gt; [comment]")
        return

    parts = command.args.split(maxsplit=2)
    if len(parts) < 2:
        await message.answer("Формат: /aml_status &lt;aml_id&gt; &lt;status&gt; [comment]")
        return

    aml_id_raw, status_raw = parts[0], parts[1].lower()
    note = parts[2] if len(parts) == 3 else None
    if not aml_id_raw.isdigit():
        await message.answer("aml_id должен быть числом.")
        return

    status = AML_ALIASES.get(status_raw)
    if status is None:
        allowed = ", ".join(status.value for status in AmlStatus)
        await message.answer(f"Неизвестный AML-статус. Допустимые: {allowed}")
        return

    aml_id = int(aml_id_raw)
    async with SessionLocal() as session:
        aml = await session.scalar(select(AmlCheck).where(AmlCheck.id == aml_id))
        if aml is None:
            await message.answer(f"AML запрос #{aml_id} не найден.")
            return
        aml.status = status
        aml.result_note = note
        await session.commit()

    status_label = _aml_status_title(status)
    await message.answer(f"AML запрос #{aml_id} обновлен: {status_label}")
    await message.bot.send_message(
        chat_id=aml.telegram_user_id,
        text=f"AML запрос #{aml_id}: результат {status_label}\nКомментарий: {note or '-'}",
    )
