from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from backend.core.config import settings

def get_main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Подключиться", callback_data="connect")],
        [InlineKeyboardButton(text="👤 Профиль", callback_data="profile")],
        [
            InlineKeyboardButton(text="👥 Рефералы", callback_data="ref"),
            InlineKeyboardButton(text="ℹ️ Информация", callback_data="info"),
        ],
        [InlineKeyboardButton(text="🆘 Поддержка", url="https://t.me/stingersup")],
    ])

def get_subscription_plans() -> InlineKeyboardMarkup:
    keyboard = [[InlineKeyboardButton(text="Пробный (3 дня) - 0$", callback_data="plan_trial")]]
    
    for plan_id, plan in settings.PLANS.items():
        keyboard.append([InlineKeyboardButton(text=plan["label"], callback_data=f"plan_{plan_id}")])
        
    keyboard.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_payment_methods(plan_id: str, ton_url: str) -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(text="💳 CryptoBot", callback_data=f"pay_crypto_{plan_id}")],
        [InlineKeyboardButton(text="⭐ Telegram Stars", callback_data=f"pay_stars_{plan_id}")],
        [InlineKeyboardButton(text="💎 Оплатить TON", url=ton_url)],
        [InlineKeyboardButton(text="✅ Я оплатил TON", callback_data=f"check_ton_{plan_id}")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="connect")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_payment_keyboard(invoice_url: str, plan_id: str) -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(text="Оплатить через CryptoBot", url=invoice_url)],
        [InlineKeyboardButton(text="Проверить оплату", callback_data="check_payment")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"plan_{plan_id}")],
        [InlineKeyboardButton(text="🏠 В меню", callback_data="menu")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_profile_keyboard(has_sub: bool, has_key: bool) -> InlineKeyboardMarkup:
    keyboard = []
    if has_sub and not has_key:
        keyboard.append([InlineKeyboardButton(text="🎁 Получить ключ", callback_data="get_vpn_key")])
    elif has_sub and has_key:
        keyboard.append([InlineKeyboardButton(text="🔄 Обновить ключ", callback_data="get_vpn_key")])
    
    if not has_sub:
        keyboard.append([InlineKeyboardButton(text="💳 Купить подписку", callback_data="connect")])
    keyboard.append([InlineKeyboardButton(text="🏠 В меню", callback_data="menu")])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)
