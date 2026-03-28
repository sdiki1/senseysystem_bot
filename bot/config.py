from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bot_token: str = Field(alias="BOT_TOKEN")

    database_url: str = Field(default="", alias="DATABASE_URL")
    postgres_db: str = Field(default="sensey", alias="POSTGRES_DB")
    postgres_user: str = Field(default="sensey", alias="POSTGRES_USER")
    postgres_password: str = Field(default="sensey", alias="POSTGRES_PASSWORD")
    postgres_host: str = Field(default="db", alias="POSTGRES_HOST")
    postgres_port: int = Field(default=5432, alias="POSTGRES_PORT")

    admin_ids_raw: str = Field(default="", alias="ADMIN_IDS")
    sensey_channel_id: int | None = Field(default=None, alias="SENSEY_CHANNEL_ID")
    sensey_channel_invite_link: str | None = Field(default=None, alias="SENSEY_CHANNEL_INVITE_LINK")

    tribute_api_key: str | None = Field(default=None, alias="TRIBUTE_API_KEY")
    tribute_webhook_secret: str | None = Field(default=None, alias="TRIBUTE_WEBHOOK_SECRET")
    tribute_verify_signature: bool = Field(default=True, alias="TRIBUTE_VERIFY_SIGNATURE")
    tribute_club_payment_url: str = Field(default="", alias="TRIBUTE_CLUB_PAYMENT_URL")
    tribute_consult_payment_url: str = Field(default="", alias="TRIBUTE_CONSULT_PAYMENT_URL")
    tribute_club_product_id: str | None = Field(default=None, alias="TRIBUTE_CLUB_PRODUCT_ID")
    tribute_consult_product_id: str | None = Field(default=None, alias="TRIBUTE_CONSULT_PRODUCT_ID")
    tribute_polling_enabled: bool = Field(default=True, alias="TRIBUTE_POLLING_ENABLED")
    tribute_polling_interval_sec: int = Field(default=20, alias="TRIBUTE_POLLING_INTERVAL_SEC")
    tribute_polling_days_back: int = Field(default=0, alias="TRIBUTE_POLLING_DAYS_BACK")
    tribute_polling_orders_url: str = Field(default="https://tribute.tg/api/v1/shop/orders", alias="TRIBUTE_POLLING_ORDERS_URL")
    tribute_polling_order_url_template: str = Field(
        default="https://tribute.tg/api/v1/shop/orders/{order_id}",
        alias="TRIBUTE_POLLING_ORDER_URL_TEMPLATE",
    )

    web_host: str = Field(default="0.0.0.0", alias="WEB_HOST")
    web_port: int = Field(default=8080, alias="WEB_PORT")
    webhook_path: str = Field(default="/webhooks/tribute", alias="WEBHOOK_PATH")

    app_timezone: str = Field(default="Europe/Moscow", alias="APP_TIMEZONE")

    club_price_rub: int = 3000
    consult_price_rub: int = 10000

    @property
    def admin_ids(self) -> List[int]:
        if not self.admin_ids_raw.strip():
            return []
        return [int(value.strip()) for value in self.admin_ids_raw.split(",") if value.strip()]

    @property
    def resolved_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
