from aiogram import Router, F
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession
from backend.core.config import settings
from backend.services.content import ContentService

router = Router()

@router.message(Command("set_text"))
async def cmd_set_text(message: Message, command: CommandObject, db: AsyncSession):
    if not message.from_user or message.from_user.id not in settings.ADMIN_IDS:
        return
    
    args = command.args
    if not args or " " not in args:
        await message.answer("Usage: /set_text <key> <text>")
        return
    
    key, text = args.split(" ", 1)
    content_service = ContentService(db)
    await content_service.update_screen(key, text=text)
    await message.answer(f"✅ Text for screen <code>{key}</code> updated.", parse_mode="HTML")

@router.message(Command("set_image"))
async def cmd_set_image(message: Message, command: CommandObject, db: AsyncSession):
    if not message.from_user or message.from_user.id not in settings.ADMIN_IDS:
        return
    
    args = command.args
    if not args:
        await message.answer("Usage: /set_image <key> [url] (or reply to an image)")
        return
    
    parts = args.split(" ", 1)
    key = parts[0]
    image_url = parts[1] if len(parts) > 1 else None
    
    if not image_url:
        if message.reply_to_message:
            if message.reply_to_message.photo:
                image_url = message.reply_to_message.photo[-1].file_id
            elif message.reply_to_message.document and message.reply_to_message.document.mime_type and message.reply_to_message.document.mime_type.startswith("image/"):
                image_url = message.reply_to_message.document.file_id
    
    if not image_url:
        await message.answer("Please reply to an image or provide a URL: /set_image <key> <url>")
        return
        
    content_service = ContentService(db)
    await content_service.update_screen(key, image_url=image_url)
    await message.answer(f"✅ Image for screen <code>{key}</code> updated to: <code>{image_url}</code>", parse_mode="HTML")
