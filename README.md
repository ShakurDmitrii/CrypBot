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
   - Опционально: `BOT_OPERATOR_USERNAME` для показа пользователю в подтверждении заявки
   - Для кнопки мини-аппа добавить `BOT_MINI_APP_URL` (например, `https://your-domain.com`)
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

## Mini App

Запуск API и фронта мини-аппа:
```bash
uvicorn src.miniapp.app:app --host 0.0.0.0 --port 8080 --reload
```

Локально открыть:
```text
http://127.0.0.1:8080
```

Для открытия из Telegram-кнопки укажите публичный HTTPS URL в `.env`:
```env
BOT_MINI_APP_URL=https://your-domain.com
```

## Локальный запуск Mini App через ngrok

Если вы тестируете локально, Telegram-кнопке нужен публичный `https` URL.

1. Запустить mini app локально:
```bash
uvicorn src.miniapp.app:app --host 127.0.0.1 --port 8083
```

2. Запустить туннель:
```bash
ngrok http 8083
```

3. Скопировать HTTPS Forwarding URL (например `https://xxxx.ngrok-free.app`) и указать его в `.env`:
```env
BOT_MINI_APP_URL=https://xxxx.ngrok-free.app
```

4. Перезапустить Telegram-бота:
```bash
python -m src.main
```

Важно:
- polling может работать только в одном экземпляре бота на один токен;
- при каждом новом URL от ngrok нужно обновить `BOT_MINI_APP_URL` и перезапустить бота;
- окно `ngrok` и процесс `uvicorn` должны оставаться запущенными, пока вы тестируете mini app.

## Операторские команды

- `/status <request_id> <status> [comment]`
  - статусы: `new`, `waiting_payment`, `payment_received`, `processing`, `done`, `canceled`, `disputed`
- `/aml_status <aml_id> <status> [comment]`
  - статусы: `pending`, `low`, `medium`, `high`, `rejected`
- `/margin [percent]`
  - без аргументов показывает текущую маржу
  - с аргументом устанавливает новую маржу в процентах (например, `/margin 2.5`)

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
