import asyncio
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.dispatcher.flags import get_flag
from aiogram.types import Message
from cachetools import TTLCache


class ThrottlingMiddleware(BaseMiddleware):
    """
    Простой middleware для защиты от спама (троттлинга).
    Использует TTLCache для хранения ID пользователей.
    """

    def __init__(self, rate_limit: float = 2.0):
        #
        self.cache = TTLCache(maxsize=10_000, ttl=rate_limit)

    async def __call__(
            self,
            handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
            event: Message,
            data: Dict[str, Any],
    ) -> Any:
        user_id = event.from_user.id
        if user_id in self.cache:
            return

        #
        self.cache[user_id] = None

        #
        return await handler(event, data)