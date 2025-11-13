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
    Требует 3x-ui API: POST /panel/api/inbounds/updateClient/:clientId
    Body: id (inbound id), settings (json c изменяемыми полями)
    """
    payload = {
        'id': str(server_config.inbound_id),
        'settings': json.dumps({
            'expiryTime': new_expiry_timestamp,
        })
    }

    async with get_xui_client(server_config) as client:
        if client is None:
            log.error(f"[XUI_API] Client session is None for {server_config.name}, login likely failed.")
            return False

        url = f"{server_config.host.rstrip('/')}/panel/api/inbounds/updateClient/{client_id}"
        try:
            response = await client.post(url, data=payload)
            if response.status_code != 200:
                log.error(f"[XUI_API] updateClient failed! Status: {response.status_code} at {url}")
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
            log.error(f"[XUI_API] Error during updateClient to {server_config.name}: {e}")
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
