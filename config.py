import datetime
import json
import logging
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import SecretStr, model_validator, BaseModel, Field
from typing import List, Dict, Any, Optional

log = logging.getLogger(__name__)


class XuiServer(BaseModel):
    """Модель для описания одного X-UI сервера с Reality"""
    name: str
    host: str  # URL панели
    inbound_id: int  # ID инбаунда в панели
    country: str  # Страна сервера

    username: str
    password: SecretStr

    # --- Параметры для VLESS ключа ---
    vless_server: str  # IP или домен сервера для подключения
    vless_port: int  # Порт Reality инбаунда
    security_type: str = "reality"  # Тип безопасности
    reality_pbk: str  # Публичный ключ Reality
    reality_short_id: str  # Короткий ID Reality
    reality_server_names: List[str]  # Список доменов для SNI
    reality_fingerprint: str  # Отпечаток браузера


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8')

    # --- Настройки Бота ---
    BOT_TOKEN: SecretStr
    BOT_USERNAME: str

    # --- Настройки ЮKassa ---
    YOOKASSA_SHOP_ID: SecretStr
    YOOKASSA_SECRET_KEY: SecretStr

    # --- Настройки CryptoBot ---
    CRYPTO_BOT_TOKEN: SecretStr
    CRYPTO_BOT_WEBHOOK_PATH: str = "/webhook/cryptobot"

    # --- Настройки Вебхуков ---
    WEBHOOK_HOST: Optional[str] = None
    WEBHOOK_PATH: str = "/webhook/yookassa"

    # --- Админы (через запятую) ---
    ADMIN_IDS: str

    RUN_MODE: str = 'webhook'

    # --- Список серверов X-UI ---
    XUI_SERVERS: List[XuiServer] = []

    POSTGRESQL_USER: str
    POSTGRESQL_PASSWORD: SecretStr
    POSTGRESQL_HOST: str
    POSTGRESQL_PORT: int = 5432  # Порт по умолчанию
    POSTGRESQL_DBNAME: str


    @property
    def get_admin_ids(self) -> list[int]:
        return [int(admin_id) for admin_id in self.ADMIN_IDS.split(',')]


settings = Settings()
log.info(f"Crypto Bot Token loaded: {'Token loaded' if settings.CRYPTO_BOT_TOKEN else '!!! Token NOT loaded !!!'}")

if not settings.XUI_SERVERS:
    log.critical("!!! КРИТИЧЕСКАЯ ОШИБКА: Конфигурация серверов XUI_SERVERS не загружена. Проверьте .env файл!")
elif not isinstance(settings.XUI_SERVERS[0], XuiServer):
    log.critical(
        f"!!! КРИТИЧЕСКАЯ ОШИБКА: Элементы в XUI_SERVERS имеют тип {type(settings.XUI_SERVERS[0])}, а не XuiServer!")
else:
    log.info(f"Конфигурация успешно загружена. Первый сервер: {settings.XUI_SERVERS[0].name}")
