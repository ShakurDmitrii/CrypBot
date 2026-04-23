from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    bot_token: str = Field(alias="BOT_TOKEN")
    bot_operator_chat_id: int = Field(alias="BOT_OPERATOR_CHAT_ID")
    bot_operator_ids: str = Field(default="", alias="BOT_OPERATOR_IDS")
    bot_offer_url: str = Field(alias="BOT_OFFER_URL")
    bot_margin_percent: float = Field(default=1.5, alias="BOT_MARGIN_PERCENT")
    bot_mini_app_url: str = Field(default="", alias="BOT_MINI_APP_URL")
    bot_proxy: str = Field(default="", alias="BOT_PROXY")
    database_url: str = Field(alias="DATABASE_URL")

    @field_validator("bot_operator_ids")
    @classmethod
    def validate_operator_ids(cls, value: str) -> str:
        if not value:
            return ""
        try:
            [int(item.strip()) for item in value.split(",") if item.strip()]
        except ValueError as exc:
            raise ValueError("BOT_OPERATOR_IDS must be comma-separated integers") from exc
        return value

    @field_validator("bot_margin_percent")
    @classmethod
    def validate_margin(cls, value: float) -> float:
        if value < 0:
            raise ValueError("BOT_MARGIN_PERCENT must be >= 0")
        return value

    @property
    def operator_ids(self) -> list[int]:
        if not self.bot_operator_ids.strip():
            return []
        return [int(item.strip()) for item in self.bot_operator_ids.split(",") if item.strip()]


@lru_cache(1)
def get_settings() -> Settings:
    return Settings()
