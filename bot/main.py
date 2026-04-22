import asyncio
import logging
import os
from typing import Any, Awaitable, Callable, Dict
from aiogram import Bot, Dispatcher, BaseMiddleware
from aiogram.types import TelegramObject

from backend.core.config import settings
from db.session import AsyncSessionLocal, engine
from db.base import Base
import backend.models.models
from bot.handlers.handlers import router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DatabaseMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        async with AsyncSessionLocal() as session:
            data["db"] = session
            return await handler(event, data)

async def main():
    # Initialize database tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables initialized.")

    bot_token = settings.BOT_TOKEN
    if not bot_token:
        logger.error("BOT_TOKEN not found in .env")
        return

    bot = Bot(token=bot_token)
    dp = Dispatcher()
    
    # Add database middleware
    dp.update.middleware(DatabaseMiddleware())
    
    # Register routers
    dp.include_router(router)
    
    logger.info("Starting bot polling...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
