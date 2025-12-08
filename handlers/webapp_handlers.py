"""
Обработчики для Telegram Web App.
Предоставляет REST API для веб-приложения.
"""
import logging
import hashlib
import hmac
from urllib.parse import parse_qsl
from aiohttp import web
from datetime import datetime

from config import settings
from database import db_commands as db

log = logging.getLogger(__name__)


def validate_telegram_webapp_data(init_data: str, bot_token: str) -> dict | None:
    """
    Валидирует данные от Telegram Web App.
    
    Args:
        init_data: строка initData от Telegram Web App
        bot_token: токен бота
        
    Returns:
        dict с данными пользователя или None если валидация не прошла
    """
    try:
        # Парсим данные
        parsed_data = dict(parse_qsl(init_data))
        
        # Извлекаем hash
        received_hash = parsed_data.pop('hash', None)
        if not received_hash:
            log.warning("No hash in initData")
            return None
        
        # Создаем строку для проверки
        data_check_string = '\n'.join(
            f"{k}={v}" for k, v in sorted(parsed_data.items())
        )
        
        # Вычисляем secret key
        secret_key = hmac.new(
            key=b"WebAppData",
            msg=bot_token.encode(),
            digestmod=hashlib.sha256
        ).digest()
        
        # Вычисляем hash
        calculated_hash = hmac.new(
            key=secret_key,
            msg=data_check_string.encode(),
            digestmod=hashlib.sha256
        ).hexdigest()
        
        # Сравниваем
        if calculated_hash != received_hash:
            log.warning("Hash mismatch in initData")
            return None
        
        # Проверяем auth_date (не старше 1 часа)
        auth_date = int(parsed_data.get('auth_date', 0))
        current_timestamp = int(datetime.now().timestamp())
        if current_timestamp - auth_date > 3600:
            log.warning("initData is too old")
            return None
        
        return parsed_data
        
    except Exception as e:
        log.error(f"Error validating initData: {e}", exc_info=True)
        return None


async def webapp_get_user_info(request: web.Request):
    """
    GET /api/webapp/user
    
    Возвращает информацию о пользователе и его ключах.
    Требует заголовок Authorization с initData от Telegram.
    """
    try:
        # Получаем initData из заголовка
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('tma '):
            return web.json_response(
                {'error': 'Invalid authorization header'},
                status=401
            )
        
        init_data = auth_header[4:]  # Убираем префикс 'tma '
        
        # Валидируем данные
        bot_token = settings.BOT_TOKEN.get_secret_value()
        validated_data = validate_telegram_webapp_data(init_data, bot_token)
        
        if not validated_data:
            return web.json_response(
                {'error': 'Invalid initData'},
                status=401
            )
        
        # Извлекаем user из validated_data
        import json
        user_data = json.loads(validated_data.get('user', '{}'))
        user_id = user_data.get('id')
        
        if not user_id:
            return web.json_response(
                {'error': 'User ID not found'},
                status=400
            )
        
        # Получаем информацию о пользователе из БД
        stats = await db.get_user_stats_detailed(user_id)
        
        if not stats:
            return web.json_response(
                {'error': 'User not found'},
                status=404
            )
        
        user = stats['user']
        
        # Формируем список ключей
        keys_list = []
        now = datetime.now()
        
        for key in stats['keys']:
            # Определяем статус ключа
            is_active = key.expires_at > now
            
            # Вычисляем оставшееся время
            if is_active:
                time_left = key.expires_at - now
                days_left = time_left.days
                hours_left = time_left.seconds // 3600
            else:
                days_left = 0
                hours_left = 0
            
            # Определяем тип ключа
            if key.order_id:
                key_type = "paid"
                product_name = key.product_name or "Платный"
            else:
                key_type = "trial"
                product_name = "Пробный (24ч)"
            
            # Извлекаем страну из vless_key
            country = "Unknown"
            try:
                server_ip = key.vless_key.split('@')[1].split(':')[0]
                server_ip_to_country = {s.vless_server: s.country for s in settings.XUI_SERVERS}
                country = server_ip_to_country.get(server_ip, "Unknown")
            except Exception:
                pass
            
            # Формируем URL подписки
            subscription_token = getattr(key, 'subscription_token', '')
            subscription_url = f"{settings.WEBHOOK_HOST}/sub/{subscription_token}"
            
            keys_list.append({
                'id': key.id,
                'type': key_type,
                'product_name': product_name,
                'country': country,
                'is_active': is_active,
                'created_at': key.created_at.isoformat(),
                'expires_at': key.expires_at.isoformat(),
                'days_left': days_left,
                'hours_left': hours_left,
                'subscription_url': subscription_url
            })
        
        # Формируем ответ
        response_data = {
            'user': {
                'id': user.user_id,
                'first_name': user.first_name,
                'username': user.username,
                'created_at': user.created_at.isoformat(),
                'has_received_trial': user.has_received_trial
            },
            'stats': {
                'total_orders': stats['total_orders'],
                'total_spent': stats['total_spent'],
                'total_keys': stats['total_keys_count'],
                'active_keys': stats['active_keys_count']
            },
            'keys': keys_list
        }
        
        return web.json_response(response_data)
        
    except Exception as e:
        log.error(f"Error in webapp_get_user_info: {e}", exc_info=True)
        return web.json_response(
            {'error': 'Internal server error'},
            status=500
        )


async def webapp_health_check(request: web.Request):
    """
    GET /api/webapp/health
    
    Проверка работоспособности API.
    """
    return web.json_response({'status': 'ok'})

