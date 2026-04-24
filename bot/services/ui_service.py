from typing import Optional, Union
from aiogram.types import Message, CallbackQuery, InputMediaPhoto, InlineKeyboardMarkup

class UIService:
    @staticmethod
    async def render_screen(
        event: Union[Message, CallbackQuery],
        text: str,
        keyboard: Optional[InlineKeyboardMarkup] = None,
        image_url: Optional[str] = None,
        parse_mode: str = "HTML"
    ):
        """
        Universal method to render a screen. 
        If image_url is provided, it will try to edit media or send photo.
        """
        if isinstance(event, CallbackQuery):
            message = event.message
            if message is None:
                return
        else:
            message = event

        if image_url:
            media = InputMediaPhoto(media=image_url, caption=text, parse_mode=parse_mode)
            try:
                # If message has photo, edit it
                if hasattr(message, 'photo') and message.photo:
                    await message.edit_media(media=media, reply_markup=keyboard)
                else:
                    # If message has no photo, we can't edit_media to photo, so send new
                    await message.answer_photo(photo=image_url, caption=text, reply_markup=keyboard, parse_mode=parse_mode)
                    if isinstance(event, CallbackQuery):
                        await message.delete()
            except Exception:
                # Fallback to text if something goes wrong
                try:
                    await message.edit_text(text=text, reply_markup=keyboard, parse_mode=parse_mode)
                except Exception:
                    await message.answer(text=text, reply_markup=keyboard, parse_mode=parse_mode)
        else:
            try:
                # If message has photo, we might want to remove it? 
                if hasattr(message, 'photo') and message.photo:
                    await message.answer(text=text, reply_markup=keyboard, parse_mode=parse_mode)
                    await message.delete()
                else:
                    await message.edit_text(text=text, reply_markup=keyboard, parse_mode=parse_mode)
            except Exception:
                await message.answer(text=text, reply_markup=keyboard, parse_mode=parse_mode)

ui_service = UIService()
