import logging
from typing import Optional, Any, Union
from aiogram.types import Message, CallbackQuery, InputMediaPhoto
from sqlalchemy.ext.asyncio import AsyncSession
from backend.services.content import ContentService

logger = logging.getLogger(__name__)

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
        if isinstance(event, CallbackQuery) and isinstance(message, Message):
            await message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
        else:
            await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
        return

    try:
        text = screen.text.format(**format_kwargs)
    except KeyError:
        text = screen.text

    if isinstance(event, CallbackQuery):
        if not isinstance(message, Message):
            return
        if screen.image_url:
            try:
                await message.edit_media(
                    InputMediaPhoto(media=screen.image_url, caption=text, parse_mode="HTML"),
                    reply_markup=keyboard,
                )
                return
            except Exception:
                # If message is not media, fallback to text edit to avoid spam.
                pass
        try:
            await message.edit_text(
                text=text,
                reply_markup=keyboard,
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
        except Exception:
            # Final fallback for media messages when text edit is unsupported.
            await message.edit_caption(
                caption=text,
                reply_markup=keyboard,
                parse_mode="HTML",
            )
        return

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
