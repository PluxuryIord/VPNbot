# config.py
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import SecretStr


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8')

    BOT_TOKEN: SecretStr
    BOT_USERNAME: str

    # ЮKassa
    YOOKASSA_SHOP_ID: SecretStr
    YOOKASSA_SECRET_KEY: SecretStr

    # URL, на который ЮKassa будет слать вебхуки
    # Должен быть HTTPS! Используй ngrok для тестов.
    WEBHOOK_HOST: str
    WEBHOOK_PATH: str = "/webhook/yookassa"

    # Админы (через запятую)
    ADMIN_IDS: str

    # Настройки VLess (замени на свои)
    VLESS_SERVER: str = "your.server.com"
    VLESS_PORT: int = 443
    VLESS_SNI: str = "your.sni.com"

    @property
    def get_admin_ids(self) -> list[int]:
        return [int(admin_id) for admin_id in self.ADMIN_IDS.split(',')]


settings = Settings()