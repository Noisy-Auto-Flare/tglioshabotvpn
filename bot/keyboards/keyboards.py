from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from backend.core.config import settings
from typing import Optional

def get_main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(icon_custom_emoji_id="5188481279963715781", text="Подключиться", callback_data="buy_menu", style="danger")],
        [InlineKeyboardButton(icon_custom_emoji_id="5920344347152224466", text="Мой профиль", callback_data="profile_main")],
        [
            InlineKeyboardButton(icon_custom_emoji_id="5944970130554359187", text="Реф. система", callback_data="referral_system"),
            InlineKeyboardButton(icon_custom_emoji_id="5436113877181941026", text="Информация", callback_data="info_menu"),
        ],
        [InlineKeyboardButton(icon_custom_emoji_id="5931614414351372818", text="Поддержка", url="https://t.me/StingerSup")],
    ])

def get_buy_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(icon_custom_emoji_id="5348444231641892650", text="Пробный период (3 дня)", callback_data="trial_activate")],
        [InlineKeyboardButton(icon_custom_emoji_id="5274055917766202507", text="Выбрать тариф", callback_data="tariff_list")],
        [InlineKeyboardButton(icon_custom_emoji_id="5258236805890710909", text="Назад", callback_data="main_menu")],
    ])

def get_tariff_list() -> InlineKeyboardMarkup:
    keyboard = []
    for plan_id, plan in settings.PLANS.items():
        text = f"{plan['label']} • {plan['price']}₽"
        keyboard.append([InlineKeyboardButton(text=text, callback_data=f"pay_order_{plan_id}")])
    keyboard.append([InlineKeyboardButton(icon_custom_emoji_id="5258236805890710909", text="Назад", callback_data="buy_menu")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_payment_methods(plan_id: str) -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(icon_custom_emoji_id="5931368295545443065", text="Оплатить с баланса", callback_data=f"pay_balance_{plan_id}", style="danger")],
        [InlineKeyboardButton(icon_custom_emoji_id="5240368741211980660", text="СБП (рубли)", callback_data=f"pay_sbp_{plan_id}", style="danger")],
        [InlineKeyboardButton(icon_custom_emoji_id="5397597950501204351", text="CryptoBot", callback_data=f"pay_cryptobot_{plan_id}")],
        [InlineKeyboardButton(icon_custom_emoji_id="5345837435601305335", text="CryptoMus", callback_data=f"pay_cryptomus_{plan_id}")],
        [InlineKeyboardButton(icon_custom_emoji_id="5438496463044752972", text="Telegram Stars", callback_data=f"pay_stars_{plan_id}")],
        [InlineKeyboardButton(icon_custom_emoji_id="5377620962390857342", text="TON Connect", callback_data=f"pay_ton_{plan_id}")],
        [InlineKeyboardButton(icon_custom_emoji_id="5258236805890710909", text="Назад", callback_data="tariff_list")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_deposit_methods() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(text="100₽", callback_data="dep_amt_100"), InlineKeyboardButton(text="500₽", callback_data="dep_amt_500")],
        [InlineKeyboardButton(text="1000₽", callback_data="dep_amt_1000"), InlineKeyboardButton(text="2500₽", callback_data="dep_amt_2500")],
        [InlineKeyboardButton(icon_custom_emoji_id="5431616900201201900", text="Своя сумма", callback_data="dep_custom_amt")],
        [InlineKeyboardButton(icon_custom_emoji_id="5258236805890710909", text="Назад", callback_data="profile_main")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_deposit_payment_methods(amount: int) -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(icon_custom_emoji_id="5240368741211980660", text="СБП (рубли)", callback_data=f"dep_sbp_{amount}", style="danger")],
        [InlineKeyboardButton(icon_custom_emoji_id="5397597950501204351", text="CryptoBot", callback_data=f"dep_cryptobot_{amount}")],
        [InlineKeyboardButton(icon_custom_emoji_id="5345837435601305335", text="CryptoMus", callback_data=f"dep_cryptomus_{amount}")],
        [InlineKeyboardButton(icon_custom_emoji_id="5438496463044752972", text="Telegram Stars", callback_data=f"dep_stars_{amount}")],
        [InlineKeyboardButton(icon_custom_emoji_id="5377620962390857342", text="TON Connect", callback_data=f"dep_ton_{amount}")],
        [InlineKeyboardButton(icon_custom_emoji_id="5258236805890710909", text="Назад", callback_data="deposit_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_profile_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(icon_custom_emoji_id="5258391025281408576", text="Статистика", callback_data="statistics")],
        [InlineKeyboardButton(icon_custom_emoji_id="5271604874419647061", text="Мои подписки", callback_data="my_subscriptions")],
        [InlineKeyboardButton(icon_custom_emoji_id="5215420556089776398", text="Пополнить баланс", callback_data="deposit_menu")],
        [InlineKeyboardButton(icon_custom_emoji_id="5258236805890710909", text="Назад", callback_data="main_menu")],
    ])

def get_my_subscriptions_keyboard(subscriptions: list) -> InlineKeyboardMarkup:
    keyboard = []
    for sub in subscriptions:
        plan_label = settings.PLANS.get(sub.plan, {}).get("label", f"Подписка #{sub.id}")
        keyboard.append([InlineKeyboardButton(icon_custom_emoji_id="5348388869513447644", text=f"{plan_label}", callback_data=f"manage_sub_{sub.id}")])
    
    keyboard.append([InlineKeyboardButton(icon_custom_emoji_id="5427168083074628963", text="Добавить подписку", callback_data="tariff_list")])
    keyboard.append([InlineKeyboardButton(icon_custom_emoji_id="5258236805890710909", text="Назад в профиль", callback_data="profile_main")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_sub_management_keyboard(sub_id: int, config_url: Optional[str] = None) -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(icon_custom_emoji_id="5307843983102204243", text="Получить ключ", callback_data=f"get_key_{sub_id}")],
        [InlineKeyboardButton(icon_custom_emoji_id="5244758760429213978", text="Обновить ключ", callback_data=f"reset_key_confirm_{sub_id}")],
        [InlineKeyboardButton(icon_custom_emoji_id="5427168083074628963", text="Продлить подписку", callback_data=f"extend_sub_{sub_id}")],
    ]
    
    if config_url:
        keyboard.append([InlineKeyboardButton(icon_custom_emoji_id="5222444124698853913", text="Инструкции", url=config_url)])
    else:
        keyboard.append([InlineKeyboardButton(icon_custom_emoji_id="5222444124698853913", text="Инструкции", callback_data="no_active_sub_alert")])
        
    keyboard.append([InlineKeyboardButton(icon_custom_emoji_id="5258236805890710909", text="К списку подписок", callback_data="my_subscriptions")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_reset_key_confirm_keyboard(sub_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(icon_custom_emoji_id="5346300789558101141", text="Подтвердить", callback_data=f"reset_key_execute_{sub_id}", style="danger")],
        [InlineKeyboardButton(icon_custom_emoji_id="5258236805890710909", text="Назад", callback_data=f"manage_sub_{sub_id}")],
    ])

def get_info_menu_keyboard(config_url: Optional[str] = None) -> InlineKeyboardMarkup:
    keyboard = []
    
    if config_url:
        keyboard.append([InlineKeyboardButton(icon_custom_emoji_id="5222444124698853913", text="Инструкции", url=config_url)])
    else:
        keyboard.append([InlineKeyboardButton(icon_custom_emoji_id="5222444124698853913", text="Инструкции", callback_data="no_active_sub_alert")])

    keyboard.extend([
        [InlineKeyboardButton(icon_custom_emoji_id="5199750217586459631", text="Пользовательское соглашение", url="https://telegra.ph/Polzovatelskoe-soglashenie-04-27-23")],
        [InlineKeyboardButton(icon_custom_emoji_id="5400250414929041085", text="Политика конфиденциальности", url="https://telegra.ph/Politika-konfidencialnosti-04-27-21")],
        [InlineKeyboardButton(icon_custom_emoji_id="5197288647275071607", text="Безопасность", url="https://telegra.ph/Bezopasnost-StingerVPN-04-27")],
        [InlineKeyboardButton(icon_custom_emoji_id="5447410659077661506", text="Проверка IP", url="https://whoer.net")],
        [InlineKeyboardButton(icon_custom_emoji_id="5188481279963715781", text="Скорость интернета", url="https://speedtest.net")],
        [InlineKeyboardButton(icon_custom_emoji_id="5258236805890710909", text="Назад", callback_data="main_menu")],
    ])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_back_to_main() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(icon_custom_emoji_id="5258236805890710909", text="Вернуться в меню", callback_data="main_menu")]
    ])
