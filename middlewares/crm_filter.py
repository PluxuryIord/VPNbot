"""
Middleware для фильтрации сообщений из CRM-топиков.
Блокирует обработку обычных команд и callback'ов в CRM-группе.
"""
import logging
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, TelegramObject
from config import settings

log = logging.getLogger(__name__)


class CRMFilterMiddleware(BaseMiddleware):
    """
    Middleware, который блокирует обработку обычных команд в CRM-топиках.
    Пропускает только специальные CRM-команды (/info, /trial).
    """
    
    # Команды, которые разрешены в CRM-топиках
    ALLOWED_CRM_COMMANDS = {'/info', '/trial'}
    
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        """
        Проверяет, является ли сообщение из CRM-группы.
        Если да - блокирует обработку обычных команд.
        """
        
        # Проверяем только Message и CallbackQuery
        if not isinstance(event, (Message, CallbackQuery)):
            return await handler(event, data)
        
        # Если CRM не настроен, пропускаем всё
        if not settings.CRM_GROUP_ID:
            return await handler(event, data)
        
        # Получаем chat_id
        if isinstance(event, Message):
            chat_id = event.chat.id
            message_thread_id = event.message_thread_id
        elif isinstance(event, CallbackQuery):
            if not event.message:
                return await handler(event, data)
            chat_id = event.message.chat.id
            message_thread_id = event.message.message_thread_id
        else:
            return await handler(event, data)
        
        # Проверяем, что это CRM-группа с топиком
        is_crm_topic = (chat_id == settings.CRM_GROUP_ID and message_thread_id is not None)
        
        if not is_crm_topic:
            # Не CRM-топик - пропускаем обработку как обычно
            return await handler(event, data)
        
        # Это CRM-топик - проверяем, что за команда
        if isinstance(event, Message):
            # Для сообщений проверяем текст команды
            if event.text and event.text.startswith('/'):
                command = event.text.split()[0].split('@')[0]  # Убираем @botname если есть
                
                if command in self.ALLOWED_CRM_COMMANDS:
                    # Разрешённая CRM-команда - пропускаем
                    log.debug(f"CRM: Разрешена команда {command} в топике {message_thread_id}")
                    return await handler(event, data)
                else:
                    # Запрещённая команда в CRM-топике - блокируем
                    log.debug(f"CRM: Заблокирована команда {command} в топике {message_thread_id}")
                    return None
            else:
                # Обычное сообщение (не команда) в CRM-топике - блокируем
                return None
        
        elif isinstance(event, CallbackQuery):
            # Все callback'и в CRM-топиках блокируем
            log.debug(f"CRM: Заблокирован callback {event.data} в топике {message_thread_id}")
            await event.answer("Эта функция недоступна в CRM-группе.", show_alert=True)
            return None
        
        # По умолчанию пропускаем
        return await handler(event, data)

