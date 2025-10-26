import datetime
import uuid
import logging
from typing import Optional, Dict

from aiogram import Bot
from urllib.parse import quote

from config import settings, XuiServer
from database import db_commands as db
import vpn_api

log = logging.getLogger(__name__)


global_last_server_indices: Dict[str, int] = {}


async def get_least_loaded_server(country: str) -> Optional[XuiServer]:
    """
    Выбирает сервер из УКАЗАННОЙ СТРАНЫ методом "Карусель".
    Возвращает None, если серверов в этой стране нет.
    """
    global global_last_server_indices
    all_servers = settings.XUI_SERVERS

    # 1. Фильтруем серверы по выбранной стране
    servers_in_country = [s for s in all_servers if s.country == country]

    if not servers_in_country:
        log.error(f"!!! ОШИБКА в get_least_loaded_server: Не найдено серверов для страны '{country}'!")
        return None

    # 2. Инициализируем/получаем индекс для этой страны
    if country not in global_last_server_indices:
        global_last_server_indices[country] = -1
    last_index = global_last_server_indices[country]

    # 3. Применяем "Карусель" к отфильтрованному списку
    next_index = (last_index + 1) % len(servers_in_country)
    global_last_server_indices[country] = next_index # Обновляем индекс для ЭТОЙ СТРАНЫ

    selected_server = servers_in_country[next_index]

    if isinstance(selected_server, XuiServer):
        log.info(f"Распределитель: для страны '{country}' выбран сервер {selected_server.name}")
        return selected_server
    else:
        log.error(f"!!! НЕИЗВЕСТНЫЙ ТИП: get_least_loaded_server вернул {type(selected_server)}")
        return None


def generate_vless_key(user_uuid: str, product_name: str, user_id: int, server_config: XuiServer) -> str:
    """
    Генерирует ссылку VLess в формате VLESS + XHTTP + Reality,
    основываясь на ключе, сгенерированном панелью.
    """
    tag = f"VPNBot_{product_name.replace(' ', '_')}_{user_id}_{server_config.country}"

    vless_server = server_config.vless_server
    vless_port = server_config.vless_port
    security_type = server_config.security_type # "reality"
    reality_pbk = server_config.reality_pbk
    reality_short_id = server_config.reality_short_id
    reality_sni = server_config.reality_server_names[0] if server_config.reality_server_names else ""
    reality_fp = server_config.reality_fingerprint
    xhttp_path_raw = "/"
    xhttp_path = quote(xhttp_path_raw)

    # Собираем VLESS + XHTTP + Reality
    vless_string = (
        f"vless://{user_uuid}"
        f"@{vless_server}:{vless_port}"
        f"?type=xhttp"
        f"&encryption=none"
        f"&path={xhttp_path}"
        # f"&host="
        # f"&mode=auto"
        f"&security={security_type}"
        f"&pbk={reality_pbk}"
        f"&fp={reality_fp}"
        f"&sni={reality_sni}"
        f"&sid={reality_short_id}"
        # f"&spx={xhttp_path}"
        # f"&pqv=..."
        f"#{tag}"
    )

    return vless_string


async def issue_key_to_user(bot: Bot, user_id: int, product_id: int, order_id: int, country: str) -> tuple[bool, str | None]: # Добавили country
    """
    Полный цикл выдачи ключа: Выбор сервера ИЗ СТРАНЫ -> API -> Генерация -> БД
    """
    try:
        # 1. ВЫБИРАЕМ СЕРВЕР ИЗ УКАЗАННОЙ СТРАНЫ
        server_config = await get_least_loaded_server(country=country) # Передаем страну
        if not server_config:
            raise ValueError(f"No servers found for country: {country}")

        product = await db.get_product_by_id(product_id)
        if not product:
            raise ValueError(f"Product {product_id} not found")

        new_uuid = str(uuid.uuid4())
        expires_at = datetime.datetime.now() + datetime.timedelta(days=product.duration_days)

        # 2. ПЕРЕДАЕМ КОНФИГ ВЫБРАННОГО СЕРВЕРА в vpn_api
        api_success = await vpn_api.add_vless_user(
            server_config=server_config,
            user_id=user_id,
            days=product.duration_days,
            new_uuid=new_uuid
        )

        if not api_success:
            raise Exception("Failed to add user via X-UI API")

        # 3. ГЕНЕРИРУЕМ КЛЮЧ (VLESS+Reality) для этого сервера
        vless_string = generate_vless_key(
            user_uuid=new_uuid,
            product_name=product.name,
            user_id=user_id,
            server_config=server_config
        )

        # 4. Сохраняем ключ в БД
        await db.add_vless_key(
            user_id=user_id,
            order_id=order_id,
            vless_key=vless_string,
            expires_at=expires_at
        )

        log.info(f"Successfully issued key {new_uuid} for order {order_id} on server {server_config.name}")
        return True, vless_string

    except Exception as e:
        log.error(f"Failed to issue key for order {order_id} (user {user_id}): {e}")
        try:
            for admin_id in settings.get_admin_ids:
                await bot.send_message(
                    admin_id,
                    f"⚠️ **СБОЙ ВЫДАЧИ КЛЮЧА** ⚠️\n\n"
                    f"Не удалось выдать ключ для заказа #{order_id} (Пользователь: {user_id}, Страна: {country}).\n" # Добавили страну в лог
                    f"Ошибка: {e}\n\n"
                    "**Требуется ручное вмешательство!**",
                    parse_mode="Markdown"
                )
        except Exception as admin_notify_e:
            log.error(f"Failed to notify admin about failure: {admin_notify_e}")

        return False, None
