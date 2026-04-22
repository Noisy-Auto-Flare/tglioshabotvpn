from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

def get_main_menu() -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton(text="Подключиться"), KeyboardButton(text="Мой профиль")],
        [KeyboardButton(text="Реферальная система")],
        [KeyboardButton(text="Информация"), KeyboardButton(text="Поддержка")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_subscription_plans() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(text="Пробный (3 дня) - 0$", callback_data="plan_trial")],
        [InlineKeyboardButton(text="30 дней - 5$", callback_data="plan_30")],
        [InlineKeyboardButton(text="90 дней - 12$", callback_data="plan_90")],
        [InlineKeyboardButton(text="180 дней - 20$", callback_data="plan_180")],
        [InlineKeyboardButton(text="360 дней - 35$", callback_data="plan_360")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_payment_keyboard(invoice_url: str) -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(text="Оплатить через CryptoBot", url=invoice_url)],
        [InlineKeyboardButton(text="Проверить оплату", callback_data="check_payment")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)
