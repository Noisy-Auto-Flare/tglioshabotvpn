import asyncio
import logging
from typing import Any, Awaitable, Callable, Dict
from aiogram import Bot, Dispatcher, BaseMiddleware
from aiogram.types import TelegramObject

from backend.core.config import settings
from db.session import AsyncSessionLocal, engine
from db.base import Base
from db.migrations import run_migrations
import backend.models.models
from bot.handlers.handlers import router, _check_channel_sub
from backend.services.init_db import init_screens
from bot.services.renderer import render_screen
from bot.webhook_server import run_internal_server
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

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

class SubscriptionMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        if not isinstance(event, (Message, CallbackQuery)) or not event.from_user:
            return await handler(event, data)
        
        user_id = event.from_user.id
        
        # Skip check for commands like /start or check_sub_status callback
        is_start_command = isinstance(event, Message) and event.text and event.text.startswith("/start")
        is_check_callback = isinstance(event, CallbackQuery) and event.data == "check_sub_status"
        is_admin = user_id in settings.ADMIN_IDS

        if is_start_command or is_check_callback or is_admin:
            return await handler(event, data)
        
        bot = data["bot"]
        db = data["db"]
        
        is_subbed = await _check_channel_sub(bot, user_id)
        if not is_subbed:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📢 Подписаться на канал", url=f"https://t.me/{settings.REQUIRED_CHANNEL.lstrip('@')}")],
                [InlineKeyboardButton(text="✅ Проверить подписку", callback_data="check_sub_status")]
            ])
            await render_screen(event, db, "required_sub", keyboard=keyboard, channel=settings.REQUIRED_CHANNEL)
            return
        
        return await handler(event, data)

async def main():
    # Initialize database tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # Run manual migrations for SQLite
    await run_migrations(engine)
    
    # Initialize default screens
    async with AsyncSessionLocal() as db:
        await init_screens(db)
    
    logger.info("Database tables and schema initialized.")

    bot_token = settings.BOT_TOKEN
    if not bot_token:
        logger.error("BOT_TOKEN not found in .env")
        return

    bot = Bot(token=bot_token)
    dp = Dispatcher()
    
    # Add database middleware
    dp.update.middleware(DatabaseMiddleware())
    dp.update.middleware(SubscriptionMiddleware())
    
    # Register routers
    dp.include_router(router)
    
    # Start internal webhook server for multi-server setup
    asyncio.create_task(run_internal_server(bot))
    
    logger.info("Starting bot polling...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
