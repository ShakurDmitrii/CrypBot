from aiogram import F, Router
from aiogram.filters import Command, CommandObject, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup
from sqlalchemy import select

from src.bot.keyboards.main import aml_status_keyboard, main_menu_keyboard, request_status_keyboard
from src.bot.states.request_flow import OperatorFlow
from src.config import get_settings
from src.db.models import AmlCheck, AmlStatus, RequestStatus, User
from src.db.session import SessionLocal
from src.services.app_settings import get_margin_percent, set_margin_percent
from src.services.exchange_requests import get_request_by_id, update_request_status
from src.services.rates import RateServiceError, available_directions, get_quote

router = Router()
settings = get_settings()
CANCEL_TEXT = "Отмена"

STATUS_ALIASES: dict[str, RequestStatus] = {
    "new": RequestStatus.NEW,
    "waiting_payment": RequestStatus.WAITING_PAYMENT,
    "payment_received": RequestStatus.PAYMENT_RECEIVED,
    "processing": RequestStatus.PROCESSING,
    "done": RequestStatus.DONE,
    "canceled": RequestStatus.CANCELED,
    "cancelled": RequestStatus.CANCELED,
    "disputed": RequestStatus.DISPUTED,
}

AML_ALIASES: dict[str, AmlStatus] = {
    "pending": AmlStatus.PENDING,
    "low": AmlStatus.LOW,
    "medium": AmlStatus.MEDIUM,
    "high": AmlStatus.HIGH,
    "rejected": AmlStatus.REJECTED,
}


def _is_operator(message: Message) -> bool:
    if message.from_user is None:
        return False
    return message.from_user.id in settings.operator_ids


def _operator_menu() -> object:
    return main_menu_keyboard(settings.bot_mini_app_url, is_operator=True)


def _cancel_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=CANCEL_TEXT)]], resize_keyboard=True)


def _format_direction(direction: str) -> str:
    return direction.replace("->", " -> ")


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
    await message.answer("Операция отменена.", reply_markup=_operator_menu())


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


@router.message(F.text == "Опер: Курсы+маржа")
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
            await message.answer("Сервис курсов временно недоступен.", reply_markup=_operator_menu())
            return
        blocks.append(
            (
                f"<b>{_format_direction(direction)}</b>\n"
                f"Базовый курс: <code>{quote.base_rate:.6f}</code>\n"
                f"Маржа: <code>+{quote.margin_percent:.2f}%</code>\n"
                f"Итоговый курс: <code>{quote.final_rate:.6f}</code>"
            )
        )

    await message.answer("<b>Курсы для оператора</b>\n\n" + "\n\n".join(blocks), reply_markup=_operator_menu())


@router.message(F.text == "Опер: Маржа")
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
    await message.answer(f"Маржа обновлена: {margin_percent:.2f}%", reply_markup=_operator_menu())


@router.message(F.text == "Опер: Статус заявки")
async def operator_status_start(message: Message, state: FSMContext) -> None:
    if not _is_operator(message):
        await message.answer("Действие доступно только оператору.")
        return

    await state.set_state(OperatorFlow.waiting_request_id)
    await message.answer("Введите номер заявки (request_id).", reply_markup=_cancel_menu())


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
        await message.answer("Сессия обновления статуса устарела. Повторите заново.", reply_markup=_operator_menu())
        return

    status = STATUS_ALIASES[status_value]
    comment_raw = (message.text or "").strip()
    comment = None if comment_raw in {"", "-"} else comment_raw

    async with SessionLocal() as session:
        request = await get_request_by_id(session, request_id)
        if request is None:
            await state.clear()
            await message.answer(f"Заявка #{request_id} не найдена.", reply_markup=_operator_menu())
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
    await message.answer(f"Статус заявки #{request_id} обновлен: {status.value}", reply_markup=_operator_menu())
    if user:
        await message.bot.send_message(
            chat_id=user.telegram_id,
            text=f"Заявка #{request_id}: новый статус {status.value}\nКомментарий: {comment or '-'}",
        )


@router.message(F.text == "Опер: AML статус")
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
        await message.answer("Сессия AML обновления устарела. Повторите заново.", reply_markup=_operator_menu())
        return

    status = AML_ALIASES[status_value]
    note_raw = (message.text or "").strip()
    note = None if note_raw in {"", "-"} else note_raw

    async with SessionLocal() as session:
        aml = await session.scalar(select(AmlCheck).where(AmlCheck.id == aml_id))
        if aml is None:
            await state.clear()
            await message.answer(f"AML запрос #{aml_id} не найден.", reply_markup=_operator_menu())
            return
        aml.status = status
        aml.result_note = note
        await session.commit()

    await state.clear()
    await message.answer(f"AML запрос #{aml_id} обновлен: {status.value}", reply_markup=_operator_menu())
    await message.bot.send_message(
        chat_id=aml.telegram_user_id,
        text=f"AML запрос #{aml_id}: результат {status.value}\nКомментарий: {note or '-'}",
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
        allowed = ", ".join(STATUS_ALIASES.keys())
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

    await message.answer(f"Статус заявки #{request_id} обновлен: {status.value}")
    if user:
        note = comment or "-"
        await message.bot.send_message(
            chat_id=user.telegram_id,
            text=f"Заявка #{request_id}: новый статус {status.value}\nКомментарий: {note}",
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
        allowed = ", ".join(AML_ALIASES.keys())
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

    await message.answer(f"AML запрос #{aml_id} обновлен: {status.value}")
    await message.bot.send_message(
        chat_id=aml.telegram_user_id,
        text=f"AML запрос #{aml_id}: результат {status.value}\nКомментарий: {note or '-'}",
    )
