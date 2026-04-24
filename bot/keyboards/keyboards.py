from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def get_main_menu_kb() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(text="🚀 Подключиться", callback_data="connect")],
        [InlineKeyboardButton(text="👤 Профиль", callback_data="profile")],
        [
            InlineKeyboardButton(text="👥 Рефералы", callback_data="ref"),
            InlineKeyboardButton(text="ℹ️ Информация", callback_data="info"),
        ],
        [InlineKeyboardButton(text="🆘 Поддержка", callback_data="support")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_subscription_plans_kb() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(text="🎁 Пробный (3 дня) - 0$", callback_data="plan_trial")],
        [InlineKeyboardButton(text="⚡ 30 дней - 5$", callback_data="plan_30")],
        [InlineKeyboardButton(text="🔥 90 дней - 12$", callback_data="plan_90")],
        [InlineKeyboardButton(text="💎 180 дней - 20$", callback_data="plan_180")],
        [InlineKeyboardButton(text="🏆 360 дней - 35$", callback_data="plan_360")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_payment_keyboard(cryptobot_url: str = None, stars_enabled: bool = True, ton_url: str = None) -> InlineKeyboardMarkup:
    keyboard = []
    if cryptobot_url:
        keyboard.append([InlineKeyboardButton(text="💳 CryptoBot", url=cryptobot_url)])
    
    if stars_enabled:
        keyboard.append([InlineKeyboardButton(text="⭐ Telegram Stars", callback_data="pay_stars")])
    
    if ton_url:
        keyboard.append([InlineKeyboardButton(text="💎 TON (Tonkeeper)", url=ton_url)])
    
    keyboard.append([InlineKeyboardButton(text="🔄 Проверить оплату", callback_data="check_payment")])
    keyboard.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="connect")])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_profile_keyboard(has_sub: bool, has_key: bool) -> InlineKeyboardMarkup:
    keyboard = []
    if has_sub:
        keyboard.append([InlineKeyboardButton(text="🔄 Обновить ключ", callback_data="get_vpn_key")])
    else:
        keyboard.append([InlineKeyboardButton(text="� Купить подписку", callback_data="connect")])
    
    keyboard.append([InlineKeyboardButton(text="🏠 В меню", callback_data="menu")])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_back_to_menu_kb() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(text="🏠 В меню", callback_data="menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)
