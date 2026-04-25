from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from backend.core.config import settings

def get_main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Подключиться", callback_data="buy_menu", style="danger")],
        [InlineKeyboardButton(text="👤 Мой профиль", callback_data="profile_main")],
        [
            InlineKeyboardButton(text="👥 Реф. система", callback_data="referral_system"),
            InlineKeyboardButton(text="ℹ️ Информация", callback_data="info_menu"),
        ],
        [InlineKeyboardButton(text="🆘 Поддержка", url="https://t.me/StingerSup")],
    ])

def get_buy_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎁 Пробный период (3 дня)", callback_data="trial_activate")],
        [InlineKeyboardButton(text="📅 Выбрать тариф", callback_data="tariff_list")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="main_menu")],
    ])

def get_tariff_list() -> InlineKeyboardMarkup:
    keyboard = []
    for plan_id, plan in settings.PLANS.items():
        keyboard.append([InlineKeyboardButton(text=plan["label"], callback_data=f"pay_order_{plan_id}")])
    keyboard.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="buy_menu")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_payment_methods(plan_id: str) -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(text="💳 Оплатить с баланса", callback_data=f"pay_balance_{plan_id}", style="danger")],
        [InlineKeyboardButton(text="🇷🇺 СБП (рубли)", callback_data=f"pay_sbp_{plan_id}", style="danger")],
        [InlineKeyboardButton(text="🤖 CryptoBot", callback_data=f"pay_cryptobot_{plan_id}")],
        [InlineKeyboardButton(text="💳 CryptoMus", callback_data=f"pay_cryptomus_{plan_id}")],
        [InlineKeyboardButton(text="⭐️ Telegram Stars", callback_data=f"pay_stars_{plan_id}")],
        [InlineKeyboardButton(text="💎 TON Connect", callback_data=f"pay_ton_{plan_id}")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="tariff_list")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_deposit_methods() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(text="🇷🇺 СБП (рубли)", callback_data="dep_sbp", style="danger")],
        [InlineKeyboardButton(text="🤖 CryptoBot", callback_data="dep_cryptobot")],
        [InlineKeyboardButton(text="💳 CryptoMus", callback_data="dep_cryptomus")],
        [InlineKeyboardButton(text="⭐️ Telegram Stars", callback_data="dep_stars")],
        [InlineKeyboardButton(text="💎 TON Connect", callback_data="dep_ton")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="profile_main")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_profile_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="statistics")],
        [InlineKeyboardButton(text="📜 Мои подписки", callback_data="my_subscriptions")],
        [InlineKeyboardButton(text="� Пополнить баланс", callback_data="deposit_menu")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="main_menu")],
    ])

def get_my_subscriptions_keyboard(subscriptions: list) -> InlineKeyboardMarkup:
    keyboard = []
    for sub in subscriptions:
        plan_label = settings.PLANS.get(sub.plan, {}).get("label", f"Подписка #{sub.id}")
        keyboard.append([InlineKeyboardButton(text=f"📦 {plan_label}", callback_data=f"manage_sub_{sub.id}")])
    
    keyboard.append([InlineKeyboardButton(text="➕ Добавить подписку", callback_data="tariff_list")])
    keyboard.append([InlineKeyboardButton(text="⬅️ Назад в профиль", callback_data="profile_main")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_sub_management_keyboard(sub_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔑 Получить ключ", callback_data=f"get_key_{sub_id}")],
        [InlineKeyboardButton(text="🔄 Обновить ключ", callback_data=f"reset_key_confirm_{sub_id}")],
        [InlineKeyboardButton(text="➕ Продлить подписку", callback_data=f"extend_sub_{sub_id}")],
        [InlineKeyboardButton(text="📖 Инструкции", callback_data="setup_guides")],
        [InlineKeyboardButton(text="⬅️ К списку подписок", callback_data="my_subscriptions")],
    ])

def get_reset_key_confirm_keyboard(sub_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"reset_key_execute_{sub_id}", style="danger")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"manage_sub_{sub_id}")],
    ])

def get_info_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📖 Инструкции по настройке", callback_data="setup_guides")],
        [InlineKeyboardButton(text="📜 Условия пользования", url="https://telegra.ph/link_to_rules")],
        [InlineKeyboardButton(text="⚖️ Публичная оферта", url="https://telegra.ph/link_to_offer")],
        [InlineKeyboardButton(text="🛡 Безопасность", url="https://telegra.ph/link_to_security")],
        [InlineKeyboardButton(text="🌐 Проверка IP", url="https://whoer.net")],
        [InlineKeyboardButton(text="🚀 Скорость интернета", url="https://speedtest.net")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="main_menu")],
    ])

def get_setup_guides_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📱 iOS", url="https://telegra.ph/ios-setup"),
            InlineKeyboardButton(text="🤖 Android", url="https://telegra.ph/android-setup"),
        ],
        [
            InlineKeyboardButton(text="💻 Windows", url="https://telegra.ph/windows-setup"),
            InlineKeyboardButton(text="🍎 macOS", url="https://telegra.ph/macos-setup"),
        ],
        [
            InlineKeyboardButton(text="🐧 Linux", url="https://telegra.ph/linux-setup"),
            InlineKeyboardButton(text="📺 Android TV", url="https://telegra.ph/android-tv-setup"),
        ],
        [
            InlineKeyboardButton(text="🌐 Роутеры", url="https://telegra.ph/router-setup"),
            InlineKeyboardButton(text="🍎 Apple TV", url="https://telegra.ph/apple-tv-setup"),
        ],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="info_menu")],
    ])

def get_back_to_main() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Вернуться в меню", callback_data="main_menu")]
    ])
