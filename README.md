# SKY Telegram Bot MVP (Python)

MVP-бот для криптообменника на стеке:
- `Python 3.11+`
- `aiogram 3`
- `SQLAlchemy 2`
- `Alembic`
- `SQLite` (с переходом на PostgreSQL через `DATABASE_URL`)

## Что умеет MVP

- Показать курс
- Рассчитать сумму обмена
- Принять заявку и сохранить в БД
- Передать заявку оператору в Telegram-чат
- Уведомлять пользователя о смене статуса
- Показать историю заявок
- Показать ссылку на публичную оферту
- Принять ручной AML-запрос и передать оператору

## Быстрый запуск

1. Создать `.env`:
   - Скопировать `.env.example` в `.env`
   - Заполнить `BOT_TOKEN`, `BOT_OPERATOR_CHAT_ID`, `BOT_OPERATOR_IDS`, `BOT_OFFER_URL`
   - Если `api.telegram.org` недоступен в вашей сети, укажите прокси в `BOT_PROXY`
2. Установить зависимости:
```bash
pip install -r requirements.txt
```
3. Выполнить миграцию:
```bash
alembic upgrade head
```
4. Запустить бота:
```bash
python -m src.main
```

## Операторские команды

- `/status <request_id> <status> [comment]`
  - статусы: `new`, `waiting_payment`, `payment_received`, `processing`, `done`, `canceled`, `disputed`
- `/aml_status <aml_id> <status> [comment]`
  - статусы: `pending`, `low`, `medium`, `high`, `rejected`

## Переключение на PostgreSQL

Изменить `DATABASE_URL`:
```env
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/sky_bot
```

Для Alembic в `alembic/env.py` уже есть преобразование URL в sync-драйвер для миграций.

## Прокси (если Telegram API недоступен)

```env
BOT_PROXY=socks5://user:pass@host:port
```

или

```env
BOT_PROXY=http://user:pass@host:port
```
