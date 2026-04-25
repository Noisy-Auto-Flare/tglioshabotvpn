import logging
from sqlalchemy.ext.asyncio import AsyncSession
from backend.services.content import ContentService

logger = logging.getLogger(__name__)

async def init_screens(db: AsyncSession):
    content_service = ContentService(db)
    
    default_screens = {
        "main_menu": {
            "text": "👋 <b>Добро пожаловать в VPN бот!</b>\n\nМы предоставляем быстрый и надежный VPN.\nВыберите действие в меню ниже:",
            "image_url": "https://img.freepik.com/free-vector/vpn-connectivity-concept-illustration_114360-6483.jpg"
        },
        "buy_menu": {
            "text": "🚀 <b>Подключение</b>\n\nВыберите тип доступа:",
            "image_url": "https://img.freepik.com/free-vector/vpn-connectivity-concept-illustration_114360-6483.jpg"
        },
        "tariff_list": {
            "text": "� <b>Выберите тарифный план</b>\n\nМы подготовили лучшие условия для вас:",
            "image_url": "https://img.freepik.com/free-vector/vpn-connectivity-concept-illustration_114360-6483.jpg"
        },
        "payment": {
            "text": "💳 <b>Оплата покупки</b>\n\nТариф: <b>{plan_label}</b>\nСумма: <b>{price}р</b>\n\nВыберите удобный способ оплаты:",
            "image_url": "https://img.freepik.com/free-vector/vpn-connectivity-concept-illustration_114360-6483.jpg"
        },
        "profile_main": {
            "text": "👤 <b>Мой профиль</b>\n\n🆔 Ваш ID: <code>{telegram_id}</code>\n💰 Баланс: <b>{balance}р</b>\n📝 Статус: <b>{status_text}</b>\n\n{vpn_info}",
            "image_url": "https://img.freepik.com/free-vector/vpn-connectivity-concept-illustration_114360-6483.jpg"
        },
        "statistics": {
            "text": "📊 <b>Статистика</b>\n\n- ID: <code>{user_id}</code>\n- Статус: <b>{status}</b>\n- Остаток дней: <b>{days_left}</b>\n- Кол-во покупок: <b>{total_orders}</b>\n- Текущий протокол: <b>{protocol_type}</b>\n- Лимит трафика: <b>{used_gb}/{total_gb} GB</b>",
            "image_url": "https://img.freepik.com/free-vector/vpn-connectivity-concept-illustration_114360-6483.jpg"
        },
        "deposit_menu": {
            "text": "💰 <b>Пополнение баланса</b>\n\nВыберите способ оплаты для пополнения внутреннего кошелька:",
            "image_url": "https://img.freepik.com/free-vector/vpn-connectivity-concept-illustration_114360-6483.jpg"
        },
        "info_menu": {
            "text": "ℹ️ <b>Информация</b>\n\nЗдесь вы найдете все необходимые инструкции и полезные ссылки для работы с нашим сервисом.",
            "image_url": "https://img.freepik.com/free-vector/vpn-connectivity-concept-illustration_114360-6483.jpg"
        },
        "setup_guides": {
            "text": "📖 <b>Инструкции по настройке</b>\n\nВыберите вашу платформу, чтобы получить подробное руководство:",
            "image_url": "https://img.freepik.com/free-vector/vpn-connectivity-concept-illustration_114360-6483.jpg"
        },
        "referral_system": {
            "text": "👥 <b>Реферальная система</b>\n\nПриглашайте друзей и получайте бонусы на баланс!\n\nКоличество приглашенных: <b>{count}</b>\nВаша ссылка: <code>{ref_link}</code>",
            "image_url": "https://img.freepik.com/free-vector/refer-friend-concept-illustration_114360-7039.jpg"
        }
    }

    for key, data in default_screens.items():
        logger.info(f"Syncing screen: {key}")
        await content_service.update_screen(
            key, 
            text=data["text"], 
            image_url=data.get("image_url")
        )
