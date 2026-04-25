import logging
from typing import Optional, Any, Union
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message, CallbackQuery, InputMediaPhoto
from sqlalchemy.ext.asyncio import AsyncSession
from backend.services.content import ContentService

logger = logging.getLogger(__name__)

async def safe_edit(
    message: Message,
    text: str,
    reply_markup: Optional[Any] = None,
    parse_mode: str = "HTML"
) -> None:
    """Safely edit a message, handling both text and media (photo) messages."""
    try:
        # Try to edit as text message
        await message.edit_text(
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
            disable_web_page_preview=True
        )
    except TelegramBadRequest as e:
        if "message is not modified" in str(e):
            return
        # If it has a photo/media, use edit_caption
        if "there is no text in the message to edit" in str(e) or "message can't be edited" in str(e):
            try:
                await message.edit_caption(
                    caption=text,
                    reply_markup=reply_markup,
                    parse_mode=parse_mode
                )
            except TelegramBadRequest as e2:
                if "message is not modified" not in str(e2):
                    logger.error(f"Failed to edit caption: {e2}")
        else:
            logger.error(f"Failed to edit text: {e}")

async def render_screen(
    event: Union[Message, CallbackQuery],
    db: AsyncSession,
    screen_key: str,
    keyboard: Optional[Any] = None,
    **format_kwargs
) -> None:
    """Render one logical screen with edit-first strategy for callback navigation."""
    content_service = ContentService(db)
    screen = await content_service.get_screen(screen_key)
    
    message = event if isinstance(event, Message) else event.message
    if not message:
        return
    
    if not screen:
        text = f"⚠️ Screen configuration missing: <code>{screen_key}</code>"
        try:
            if isinstance(event, CallbackQuery) and isinstance(message, Message):
                await safe_edit(message, text, reply_markup=keyboard)
            else:
                await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
        except TelegramBadRequest as e:
            if "message is not modified" not in str(e):
                logger.error(f"Error rendering missing screen: {e}")
        return

    try:
        text = screen.text.format(**format_kwargs)
    except KeyError:
        text = screen.text

    if isinstance(event, CallbackQuery):
        if not isinstance(message, Message):
            return
        
        try:
            if screen.image_url:
                try:
                    await message.edit_media(
                        InputMediaPhoto(media=screen.image_url, caption=text, parse_mode="HTML"),
                        reply_markup=keyboard,
                    )
                    return
                except TelegramBadRequest as e:
                    # If edit_media fails (e.g. current message has no media or same media)
                    if "message is not modified" in str(e):
                        return
                    # If it's not a media message, we'll fall through to edit_text/edit_caption
            
            # Try to edit text or caption
            await safe_edit(message, text, reply_markup=keyboard)
        except TelegramBadRequest as e:
            if "message is not modified" not in str(e):
                logger.error(f"Error in callback render: {e}")
        except Exception as e:
            logger.error(f"Unexpected error in callback render: {e}")
        return

    # For Message events (like /start)
    if screen.image_url:
        try:
            await message.answer_photo(
                photo=screen.image_url,
                caption=text,
                reply_markup=keyboard,
                parse_mode="HTML",
            )
            return
        except Exception as e:
            logger.error(f"Error sending photo {screen.image_url}: {e}")
            # Fallback to text message if photo fails
    
    await message.answer(
        text=text,
        reply_markup=keyboard,
        parse_mode="HTML",
        disable_web_page_preview=True,
    )
