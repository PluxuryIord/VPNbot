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
    Пропускает только специальные CRM-команды.
    """

    # Команды, которые разрешены в CRM-топиках
    ALLOWED_CRM_COMMANDS = {'/info', '/trial', '/payment', '/key', '/notification'}

    # Префиксы callback-данных, которые разрешены в CRM-топиках
    ALLOWED_CRM_CALLBACKS = {'crm_keys_page:', 'crm_key_details:', 'crm_add_days:', 'crm_key_country:'}
    
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
            # Проверяем, есть ли активное FSM состояние
            state = data.get('state')
            if state:
                current_state = await state.get_state()
                if current_state:
                    # Есть активное FSM состояние - пропускаем (это ответ на запрос бота)
                    log.debug(f"CRM: Разрешено сообщение в FSM состоянии {current_state}")
                    return await handler(event, data)

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
                # Обычное сообщение (не команда) в CRM-топике без FSM - блокируем
                log.debug(f"CRM: Заблокировано обычное сообщение в топике {message_thread_id}")
                return None
        
        elif isinstance(event, CallbackQuery):
            # Проверяем, является ли callback CRM-callback'ом
            callback_data = event.data or ""

            # Проверяем, начинается ли callback с разрешенного префикса
            is_allowed = any(callback_data.startswith(prefix) for prefix in self.ALLOWED_CRM_CALLBACKS)

            if is_allowed:
                # Разрешённый CRM-callback - пропускаем
                log.debug(f"CRM: Разрешен callback {callback_data} в топике {message_thread_id}")
                return await handler(event, data)
            else:
                # Запрещённый callback в CRM-топике - блокируем
                log.debug(f"CRM: Заблокирован callback {callback_data} в топике {message_thread_id}")
                await event.answer("Эта функция недоступна в CRM-группе.", show_alert=True)
                return None
        
        # По умолчанию пропускаем
        return await handler(event, data)

