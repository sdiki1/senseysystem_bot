from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta
from typing import Any

from aiohttp import ClientSession, ClientTimeout

from bot.config import Settings
from bot.web.server import TributeWebhookServer

logger = logging.getLogger(__name__)


class TributePollingService:
    def __init__(self, processor: TributeWebhookServer, settings: Settings) -> None:
        self.processor = processor
        self.settings = settings
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()

    async def start(self) -> bool:
        if not self.settings.tribute_api_key:
            logger.warning("Tribute polling is enabled but TRIBUTE_API_KEY is empty")
            return False
        if self._task is not None and not self._task.done():
            return True

        self._stop_event.clear()
        self._task = asyncio.create_task(self._run(), name="tribute-polling")
        logger.info(
            "Tribute polling started interval=%ss orders_url=%s",
            self.settings.tribute_polling_interval_sec,
            self.settings.tribute_polling_orders_url,
        )
        return True

    async def stop(self) -> None:
        if self._task is None:
            return

        self._stop_event.set()
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    async def _run(self) -> None:
        timeout = ClientTimeout(total=20)
        headers = {"Api-Key": str(self.settings.tribute_api_key), "Accept": "application/json"}
        async with ClientSession(timeout=timeout, headers=headers) as client:
            while not self._stop_event.is_set():
                try:
                    await self._poll_once(client)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception("Tribute polling iteration failed")

                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(),
                        timeout=max(5, self.settings.tribute_polling_interval_sec),
                    )
                except asyncio.TimeoutError:
                    continue

    async def _poll_once(self, client: ClientSession) -> None:
        orders = await self._fetch_orders(client)
        if not orders:
            return

        # API returns newest first. Process oldest first for deterministic state updates.
        for order in reversed(orders):
            raw_event = await self._order_to_event(client, order)
            if raw_event is None:
                continue
            await self.processor.process_tribute_event(raw_event, source="polling")

    async def _fetch_orders(self, client: ClientSession) -> list[dict[str, Any]]:
        params: dict[str, str] | None = None
        days_back = max(0, self.settings.tribute_polling_days_back)
        if days_back > 0:
            date_to = date.today()
            date_from = date_to - timedelta(days=days_back)
            params = {"dateFrom": date_from.isoformat(), "dateTo": date_to.isoformat()}

        async with client.get(self.settings.tribute_polling_orders_url, params=params) as response:
            if response.status >= 400:
                text = await response.text()
                logger.error("Tribute polling failed status=%s body=%s", response.status, text[:500])
                return []
            payload = await response.json(content_type=None)

        if isinstance(payload, list):
            return [row for row in payload if isinstance(row, dict)]

        if isinstance(payload, dict):
            rows = payload.get("rows")
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)]

            grouped = payload.get("orders")
            if isinstance(grouped, dict) and isinstance(grouped.get("all"), list):
                all_orders = grouped.get("all") or []
                return [row for row in all_orders if isinstance(row, dict)]

        logger.warning("Tribute polling got unsupported response format: %s", type(payload).__name__)
        return []

    async def _order_to_event(self, client: ClientSession, order: dict[str, Any]) -> dict[str, Any] | None:
        payload = dict(order)
        order_id = str(payload.get("uuid") or payload.get("id") or "").strip()
        if order_id and not self._has_telegram_id(payload):
            details = await self._fetch_order_details(client, order_id)
            if details:
                payload.update(details)

        if not self._has_telegram_id(payload):
            return None

        event_type = self._resolve_event_type(payload)
        if not event_type:
            return None

        return {
            "event": event_type,
            "payload": payload,
        }

    async def _fetch_order_details(self, client: ClientSession, order_id: str) -> dict[str, Any] | None:
        url = self.settings.tribute_polling_order_url_template.format(order_id=order_id)
        async with client.get(url) as response:
            if response.status >= 400:
                return None
            payload = await response.json(content_type=None)
        if isinstance(payload, dict):
            return payload
        return None

    @staticmethod
    def _resolve_event_type(payload: dict[str, Any]) -> str | None:
        status = str(payload.get("status") or "").strip().lower()
        member_status = str(payload.get("memberStatus") or payload.get("member_status") or "").strip().lower()

        if member_status in {"cancelled", "canceled"}:
            return "cancelled_subscription"
        if status == "paid":
            return "payment_succeeded"
        if status in {"failed", "cancelled", "canceled", "refunded"}:
            return "payment_failed"
        return None

    @staticmethod
    def _has_telegram_id(payload: dict[str, Any]) -> bool:
        return bool(
            payload.get("telegram_id")
            or payload.get("telegramId")
            or payload.get("telegramID")
            or payload.get("user_id")
            or payload.get("customer_id")
            or payload.get("customerId")
        )
