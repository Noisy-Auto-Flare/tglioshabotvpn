import logging
import re
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
) -> bool:
    """Safely edit a message, handling both text and media (photo) messages. Returns True if successful."""
    try:
        await message.edit_text(
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
            disable_web_page_preview=True
        )
        return True
    except TelegramBadRequest as e:
        if "message is not modified" in str(e):
            return True
        
        # DOCUMENT_INVALID can happen if text contains invalid custom emojis
        if "DOCUMENT_INVALID" in str(e) and parse_mode == "HTML":
            logger.warning(f"DOCUMENT_INVALID in edit_text, stripping HTML and retrying: {e}")
            clean_text = re.sub(r'<[^>]+>', '', text)
            try:
                await message.edit_text(
                    text=clean_text,
                    reply_markup=reply_markup,
                    parse_mode=None,
                    disable_web_page_preview=True
                )
                return True
            except Exception as e3:
                logger.error(f"Failed even with clean text: {e3}")

        if any(msg in str(e) for msg in ["there is no text in the message to edit", "message can't be edited", "MESSAGE_ID_INVALID", "DOCUMENT_INVALID"]):
            try:
                await message.edit_caption(
                    caption=text,
                    reply_markup=reply_markup,
                    parse_mode=parse_mode
                )
                return True
            except TelegramBadRequest as e2:
                if "message is not modified" in str(e2):
                    return True
                
                if "DOCUMENT_INVALID" in str(e2) and parse_mode == "HTML":
                    logger.warning(f"DOCUMENT_INVALID in edit_caption, stripping HTML and retrying: {e2}")
                    clean_text = re.sub(r'<[^>]+>', '', text)
                    try:
                        await message.edit_caption(
                            caption=clean_text,
                            reply_markup=reply_markup,
                            parse_mode=None
                        )
                        return True
                    except Exception:
                        pass
                
                if "DOCUMENT_INVALID" in str(e2):
                    logger.warning(f"Failed to edit caption (DOCUMENT_INVALID): {e2}")
                    return False
                logger.warning(f"Failed to edit caption: {e2}")
        else:
            if "DOCUMENT_INVALID" in str(e):
                logger.warning(f"Failed to edit text (DOCUMENT_INVALID): {e}")
                return False
            logger.warning(f"Failed to edit text: {e}")
    return False

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
                if not await safe_edit(message, text, reply_markup=keyboard):
                    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
            else:
                await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Error rendering missing screen: {e}")
        return

    try:
        text = screen.text.format(**format_kwargs)
    except KeyError:
        text = screen.text

    if isinstance(event, CallbackQuery):
        if not isinstance(message, Message):
            return
        
        edit_success = False
        try:
            if screen.image_url:
                try:
                    await message.edit_media(
                        InputMediaPhoto(media=screen.image_url, caption=text, parse_mode="HTML"),
                        reply_markup=keyboard,
                    )
                    edit_success = True
                except TelegramBadRequest as e:
                    if "message is not modified" in str(e):
                        return
                    # If edit_media fails, we'll try safe_edit below
                    logger.debug(f"edit_media failed, falling back to safe_edit: {e}")
            
            if not edit_success:
                edit_success = await safe_edit(message, text, reply_markup=keyboard)
            
            if edit_success:
                return
        except Exception as e:
            logger.warning(f"Edit failed in callback render, will try to send new message: {e}")

        # If editing failed (e.g. DOCUMENT_INVALID, or message too old), send a new message
        try:
            # Try to delete old message to keep chat clean
            await message.delete()
        except Exception:
            pass

        # Fall through to sending a new message
    
    # Send as a new message (used for non-callbacks or as fallback)
    try:
        if screen.image_url:
            try:
                await message.answer_photo(
                    photo=screen.image_url,
                    caption=text,
                    reply_markup=keyboard,
                    parse_mode="HTML",
                )
            except TelegramBadRequest as e:
                if "DOCUMENT_INVALID" in str(e):
                    logger.warning(f"Failed to send photo (DOCUMENT_INVALID), falling back to text: {e}")
                    try:
                        await message.answer(
                            text=text,
                            reply_markup=keyboard,
                            parse_mode="HTML",
                            disable_web_page_preview=True,
                        )
                    except TelegramBadRequest as e_text:
                        if "DOCUMENT_INVALID" in str(e_text):
                            logger.warning(f"DOCUMENT_INVALID even in text message, stripping HTML: {e_text}")
                            clean_text = re.sub(r'<[^>]+>', '', text)
                            await message.answer(
                                text=clean_text,
                                reply_markup=keyboard,
                                parse_mode=None,
                                disable_web_page_preview=True,
                            )
                        else:
                            raise e_text
                else:
                    raise e
        else:
            await message.answer(
                text=text,
                reply_markup=keyboard,
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
    except Exception as e:
        logger.error(f"Error sending message in render_screen: {e}")

