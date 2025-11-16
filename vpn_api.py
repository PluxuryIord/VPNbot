# vpn_api.py
import httpx
import logging
import json
import datetime
import uuid
from contextlib import asynccontextmanager
from urllib.parse import urlparse

from config import settings, XuiServer

log = logging.getLogger(__name__)

API_HEADERS = {
    'Accept': 'application/json',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36',
    'X-Requested-With': 'XMLHttpRequest',
}



@asynccontextmanager
async def get_xui_client(server_config: XuiServer):
    """
    Асинхронный менеджер контекста на HTTpx.
    Использует username/password из server_config.
    """
    headers = API_HEADERS.copy()
    headers['Referer'] = f"{server_config.host.rstrip('/')}/panel/inbounds"

    try:
        # Используем httpx[http2] если установлен, для лучшей имитации
        async with httpx.AsyncClient(headers=headers, http2=True, verify=False) as client:

            login_url = f"{server_config.host.rstrip('/')}/login"
            # ⭐️ Получаем пароль из SecretStr ⭐️
            credentials = {
                'username': server_config.username,
                'password': server_config.password.get_secret_value()
            }

            response = await client.post(login_url, data=credentials)

            if response.status_code != 200:
                log.error(f"[XUI_API] Login failed! Status: {response.status_code} at {login_url}")
                raise Exception("X-UI Login failed")

            login_data = response.json()
            if not login_data.get('success'):
                log.error(f"[XUI_API] Login credentials incorrect. API returned: {login_data}")
                raise Exception("X-UI Login returned false")

            log.info(f"[XUI_API] Login successful to {server_config.name} (httpx).")
            yield client

    except ImportError: # Если http2 не установлен, пробуем без него
         async with httpx.AsyncClient(headers=headers, verify=False) as client:
            login_url = f"{server_config.host.rstrip('/')}/login"
            credentials = {
                'username': server_config.username,
                'password': server_config.password.get_secret_value()
            }
            response = await client.post(login_url, data=credentials)
            if response.status_code != 200: log.error(f"[XUI_API] Login failed! Status: {response.status_code} at {login_url}"); raise Exception("X-UI Login failed")
            login_data = response.json();
            if not login_data.get('success'): log.error(f"[XUI_API] Login credentials incorrect. API returned: {login_data}"); raise Exception("X-UI Login returned false")
            log.info(f"[XUI_API] Login successful to {server_config.name} (httpx - no http2).")
            yield client
    except Exception as e:
        log.error(f"[XUI_API] Error in X-UI context manager for {server_config.name}: {e}")
        yield None



async def add_vless_user(server_config: XuiServer, user_id: int, days: int, new_uuid: str) -> bool:  # Added type hint
    """
    Добавляет нового пользователя (клиента) на VLess сервер.
    Использует dot notation для доступа к server_config.
    """
    now = datetime.datetime.now()
    expires_at = now + datetime.timedelta(days=days)
    expiry_timestamp = int(expires_at.timestamp() * 1000)
    email = f"u{user_id}_{new_uuid[:8]}"

    client_settings = {
        "clients": [
            {
                "id": new_uuid, "email": email, "totalGB": 0, "expiryTime": expiry_timestamp,
                "enable": True, "tgId": "", "limitIp": 0, "flow": "",
                "subId": str(uuid.uuid4()).replace('-', '')[:16]
            }
        ]
    }

    payload = {
        'id': str(server_config.inbound_id),
        'settings': json.dumps(client_settings)
    }

    async with get_xui_client(server_config) as client:
        if client is None:
            log.error(f"[XUI_API] Client session is None for {server_config.name}, login likely failed.")
            return False

        add_url = f"{server_config.host.rstrip('/')}/panel/api/inbounds/addClient"

        try:
            response = await client.post(add_url, data=payload)

            if response.status_code != 200:
                log.error(f"[XUI_API] addClient request failed! Status: {response.status_code} at {add_url}")
                log.error(f"[XUI_API] Response: {response.text}")
                return False

            resp_data = response.json()

            if resp_data.get('success'):
                log.info(f"[XUI_API] Successfully added user {email} to {server_config.name}")
                return True
            else:
                log.error(f"[XUI_API] addClient API returned false: {resp_data}")
                return False

        except Exception as e:
            log.error(f"[XUI_API] Error during addClient request to {server_config.name}: {e}")
            return False


async def update_vless_user_expiry(server_config: XuiServer, client_id: str, new_expiry_timestamp: int) -> bool:
    """
    Обновляет срок действия (expiryTime) существующего клиента VLESS на панели.
    Требует 3x-ui API: POST /panel/api/inbounds/updateClient/{client_uuid}

    Сначала получает информацию о клиенте (включая email), затем обновляет срок.
    """
    async with get_xui_client(server_config) as client:
        if client is None:
            log.error(f"[XUI_API] Client session is None for {server_config.name}, login likely failed.")
            return False

        # Сначала получаем информацию о клиенте
        list_url = f"{server_config.host.rstrip('/')}/panel/api/inbounds/list"
        try:
            response = await client.get(list_url)
            if response.status_code != 200:
                log.error(f"[XUI_API] inbounds/list failed! Status: {response.status_code}")
                return False

            resp_data = response.json()
            if not resp_data.get('success'):
                log.error(f"[XUI_API] inbounds/list API returned false: {resp_data}")
                return False

            # Ищем нужный inbound
            inbounds = resp_data.get('obj', [])
            target_inbound = None

            for inbound in inbounds:
                if inbound.get('id') == server_config.inbound_id:
                    target_inbound = inbound
                    break

            if not target_inbound:
                log.error(f"[XUI_API] Inbound {server_config.inbound_id} not found on {server_config.name}")
                return False

            # Парсим настройки клиентов
            settings_str = target_inbound.get('settings', '{}')
            settings = json.loads(settings_str)
            clients = settings.get('clients', [])

            # Ищем клиента по UUID
            client_data = None
            for c in clients:
                if c.get('id') == client_id:
                    client_data = c
                    break

            if not client_data:
                log.error(f"[XUI_API] Client {client_id} not found in inbound {server_config.inbound_id}")
                return False

            # Обновляем expiryTime в данных клиента
            client_data['expiryTime'] = new_expiry_timestamp

            # Формируем payload для обновления
            payload = {
                'id': str(server_config.inbound_id),
                'settings': json.dumps({
                    'clients': [client_data]
                })
            }

            # Отправляем запрос на обновление
            update_url = f"{server_config.host.rstrip('/')}/panel/api/inbounds/updateClient/{client_id}"
            response = await client.post(update_url, data=payload)

            if response.status_code != 200:
                log.error(f"[XUI_API] updateClient failed! Status: {response.status_code} at {update_url}")
                log.error(f"[XUI_API] Response: {response.text}")
                return False

            resp_data = response.json()
            if resp_data.get('success'):
                log.info(f"[XUI_API] Updated expiry for client {client_id} on {server_config.name}")
                return True
            else:
                log.error(f"[XUI_API] updateClient API returned false: {resp_data}")
                return False

        except Exception as e:
            log.error(f"[XUI_API] Error during updateClient to {server_config.name}: {e}", exc_info=True)
            return False


async def delete_vless_user(server_config: XuiServer, client_id: str) -> bool:
    """
    Удаляет клиента по его clientId (UUID) из inbound.
    3x-ui API: POST /panel/api/inbounds/:id/delClient/:clientId
    """
    async with get_xui_client(server_config) as client:
        if client is None:
            log.error(f"[XUI_API] Client session is None for {server_config.name}, login likely failed.")
            return False

        url = f"{server_config.host.rstrip('/')}/panel/api/inbounds/{server_config.inbound_id}/delClient/{client_id}"
        try:
            response = await client.post(url)
            if response.status_code != 200:
                log.error(f"[XUI_API] delClient failed! Status: {response.status_code} at {url}")
                log.error(f"[XUI_API] Response: {response.text}")
                return False
            resp_data = response.json()
            if resp_data.get('success'):
                log.info(f"[XUI_API] Deleted client {client_id} from {server_config.name}")
                return True
            else:
                log.error(f"[XUI_API] delClient API returned false: {resp_data}")
                return False
        except Exception as e:
            log.error(f"[XUI_API] Error during delClient on {server_config.name}: {e}")
            return False


async def get_client_traffic(server_config: XuiServer, client_uuid: str) -> dict | None:
    """
    Получает статистику трафика для конкретного клиента.
    Использует endpoint GET /panel/api/inbounds/list

    Возвращает словарь с данными:
    {
        'up': int,      # Исходящий трафик в байтах
        'down': int,    # Входящий трафик в байтах
        'total': int,   # Общий трафик в байтах
        'email': str,   # Email клиента
        'enable': bool  # Активен ли клиент
    }

    Возвращает None если клиент не найден или произошла ошибка.
    """
    async with get_xui_client(server_config) as client:
        if client is None:
            log.error(f"[XUI_API] Client session is None for {server_config.name}, login likely failed.")
            return None

        url = f"{server_config.host.rstrip('/')}/panel/api/inbounds/list"
        try:
            response = await client.get(url)
            if response.status_code != 200:
                log.error(f"[XUI_API] inbounds/list failed! Status: {response.status_code} at {url}")
                log.error(f"[XUI_API] Response: {response.text}")
                return None

            resp_data = response.json()
            if not resp_data.get('success'):
                log.error(f"[XUI_API] inbounds/list API returned false: {resp_data}")
                return None

            # Ищем нужный inbound
            inbounds = resp_data.get('obj', [])
            target_inbound = None

            for inbound in inbounds:
                if inbound.get('id') == server_config.inbound_id:
                    target_inbound = inbound
                    break

            if not target_inbound:
                log.warning(f"[XUI_API] Inbound {server_config.inbound_id} not found on {server_config.name}")
                return None

            # Парсим настройки клиентов
            settings_str = target_inbound.get('settings', '{}')
            try:
                settings = json.loads(settings_str)
            except json.JSONDecodeError:
                log.error(f"[XUI_API] Failed to parse settings JSON for inbound {server_config.inbound_id}")
                return None

            clients = settings.get('clients', [])

            # Ищем клиента по UUID
            for client_data in clients:
                if client_data.get('id') == client_uuid:
                    # Получаем статистику клиента
                    client_stats = target_inbound.get('clientStats', [])

                    # Ищем статистику для этого email
                    email = client_data.get('email', '')
                    traffic_data = {
                        'up': 0,
                        'down': 0,
                        'total': 0,
                        'email': email,
                        'enable': client_data.get('enable', False)
                    }

                    for stat in client_stats:
                        if stat.get('email') == email:
                            traffic_data['up'] = stat.get('up', 0)
                            traffic_data['down'] = stat.get('down', 0)
                            traffic_data['total'] = traffic_data['up'] + traffic_data['down']
                            break

                    log.info(f"[XUI_API] Got traffic stats for client {client_uuid} on {server_config.name}: {traffic_data['total']} bytes")
                    return traffic_data

            log.warning(f"[XUI_API] Client {client_uuid} not found in inbound {server_config.inbound_id}")
            return None

        except Exception as e:
            log.error(f"[XUI_API] Error getting client traffic from {server_config.name}: {e}")
            return None



def format_traffic(bytes_count: int) -> str:
    """
    Форматирует количество байт в читаемый вид (КБ, МБ, ГБ).
    """
    if bytes_count < 1024:
        return f"{bytes_count} Б"
    elif bytes_count < 1024 * 1024:
        return f"{bytes_count / 1024:.2f} КБ"
    elif bytes_count < 1024 * 1024 * 1024:
        return f"{bytes_count / (1024 * 1024):.2f} МБ"
    else:
        return f"{bytes_count / (1024 * 1024 * 1024):.2f} ГБ"


async def get_traffic_by_vless_key(vless_key: str) -> dict | None:
    """
    Получает статистику трафика по VLESS ключу.
    Извлекает UUID и сервер из ключа, находит соответствующий server_config
    и получает статистику трафика.

    Возвращает словарь с данными или None если не удалось получить.
    """
    try:
        # Извлекаем UUID и сервер из vless://<uuid>@<server>:<port>
        client_uuid = vless_key.split('vless://')[1].split('@')[0]
        server_host = vless_key.split('@')[1].split(':')[0]

        # Находим соответствующий server_config
        server_config = None
        for s in settings.XUI_SERVERS:
            if s.vless_server == server_host:
                server_config = s
                break

        if not server_config:
            log.warning(f"[XUI_API] Server config not found for host {server_host}")
            return None

        # Получаем статистику трафика
        traffic_data = await get_client_traffic(server_config, client_uuid)
        return traffic_data

    except Exception as e:
        log.error(f"[XUI_API] Error parsing vless key or getting traffic: {e}")
        return None
