from typing import Optional, Any, Union
from aiogram.types import Message, CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession
from backend.services.content import ContentService

async def render_screen(
    event: Union[Message, CallbackQuery],
    db: AsyncSession,
    screen_key: str,
    keyboard: Optional[Any] = None,
    **format_kwargs
):
    """
    Renders a screen based on the screen_key.
    If image_url exists, sends a photo with caption.
    Otherwise, sends a text message.
    """
    content_service = ContentService(db)
    screen = await content_service.get_screen(screen_key)
    
    message = event if isinstance(event, Message) else event.message
    if not message:
        return
    
    if not screen:
        text = f"⚠️ Screen configuration missing: <code>{screen_key}</code>"
        await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
        return

    try:
        text = screen.text.format(**format_kwargs)
    except KeyError as e:
        text = screen.text
        # In production, you might want to log this but not fail
        # text = screen.text.replace("{", "{{").replace("}", "}}") # simple escaping if format fails

    if screen.image_url:
        try:
            await message.answer_photo(
                photo=screen.image_url,
                caption=text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
        except Exception as e:
            # Fallback to text if image fails (e.g. invalid URL/file_id)
            await message.answer(
                text=f"{text}\n\n(Error loading image: {screen.image_url})",
                reply_markup=keyboard,
                parse_mode="HTML",
                disable_web_page_preview=True
            )
    else:
        await message.answer(
            text=text,
            reply_markup=keyboard,
            parse_mode="HTML",
            disable_web_page_preview=True
        )
