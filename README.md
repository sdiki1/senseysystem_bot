# SENSEY SYSTEM Bot (aiogram + PostgreSQL + Docker)

Telegram-бот по ТЗ:
- диагностика из 8 вопросов
- 2 ветки оффера (SENSEY club / личный разбор)
- автоворонки напоминаний по таймерам
- polling/webhook-интеграция Tribute
- админ-панель: статистика + рассылки text/photo/video

## Стек
- Python 3.12
- aiogram 3
- PostgreSQL
- SQLAlchemy async
- Docker / Docker Compose

## Быстрый старт
1. Скопируй `.env.example` -> `.env` и заполни переменные.
2. Запусти:

```bash
docker compose up --build -d
```

3. Проверь логи:

```bash
docker compose logs -f bot
```

## Важные переменные (в `.env`)
- `BOT_TOKEN` — токен Telegram бота
- `DATABASE_URL` — строка подключения к Postgres
- `ADMIN_IDS` — telegram id админов через запятую
- `SENSEY_CHANNEL_ID` — id закрытого канала (если бот создает разовые инвайты)
- `SENSEY_CHANNEL_INVITE_LINK` — готовая ссылка в канал (если не нужен auto-create invite)
- `TRIBUTE_WEBHOOK_SECRET` — секрет проверки `trbt-signature`
- `TRIBUTE_CLUB_PAYMENT_URL` — ссылка Tribute на рекуррентный продукт SENSEY club
- `TRIBUTE_CONSULT_PAYMENT_URL` — ссылка Tribute на разовый продукт личного разбора
- `TRIBUTE_CLUB_PRODUCT_ID`, `TRIBUTE_CONSULT_PRODUCT_ID` — опционально для точного роутинга вебхуков по продуктам
- `TRIBUTE_POLLING_ENABLED` — включить опрос Tribute API вместо webhook (`true`/`false`)
- `TRIBUTE_POLLING_INTERVAL_SEC` — интервал опроса в секундах
- `TRIBUTE_POLLING_DAYS_BACK` — если `> 0`, ограничивает polling последними N днями; `0` = без фильтра по датам
- `TRIBUTE_POLLING_ORDERS_URL` — URL списка заказов для polling
- `TRIBUTE_POLLING_ORDER_URL_TEMPLATE` — URL карточки заказа (должен содержать `{order_id}`)

## Tribute: Polling и Webhook
По умолчанию включен polling (`TRIBUTE_POLLING_ENABLED=true`): бот периодически опрашивает Tribute API и сам обрабатывает изменения статуса оплаты.

Если нужен webhook-режим, установи `TRIBUTE_POLLING_ENABLED=false`. Тогда поднимется HTTP endpoint:
- `POST {WEBHOOK_PATH}`
- по умолчанию: `POST /webhooks/tribute`
- порт: `WEB_PORT` (по умолчанию `8080`)

События подписки (`new_subscription`, `renewed_subscription`, `cancelled_subscription`) обрабатываются автоматически.

`renewed_subscription` используется как автопродление подписки без действий пользователя.

## Админ-панель
Команда:
- `/admin`

Возможности:
- статистика
- список последних пользователей
- список последних оплат
- рассылка в сегменты: все / club / разбор
- форматы: текст / фото / видео

Дополнительно:
- `/stats` — быстрая статистика
