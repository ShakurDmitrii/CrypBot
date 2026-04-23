from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from sqlalchemy import select

from src.config import get_settings
from src.db.models import AmlCheck, AmlStatus, RequestStatus, User
from src.db.session import SessionLocal
from src.services.app_settings import get_margin_percent, set_margin_percent
from src.services.exchange_requests import get_request_by_id, update_request_status

router = Router()
settings = get_settings()

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
            f"Изменить: /margin <percent>\n"
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


@router.message(Command("status"))
async def set_request_status(message: Message, command: CommandObject) -> None:
    if not _is_operator(message):
        await message.answer("Команда доступна только оператору.")
        return

    if not command.args:
        await message.answer("Формат: /status <request_id> <status> [comment]")
        return

    parts = command.args.split(maxsplit=2)
    if len(parts) < 2:
        await message.answer("Формат: /status <request_id> <status> [comment]")
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
        await message.answer("Формат: /aml_status <aml_id> <status> [comment]")
        return

    parts = command.args.split(maxsplit=2)
    if len(parts) < 2:
        await message.answer("Формат: /aml_status <aml_id> <status> [comment]")
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
