import logging
from sqlalchemy.ext.asyncio import AsyncSession
from backend.services.content import ContentService

logger = logging.getLogger(__name__)

async def init_screens(db: AsyncSession):
    content_service = ContentService(db)
    
    default_screens = {
        "main_menu": {
            "text": "👋 Добро пожаловать в VPN бот!\n\nМы предоставляем быстрый и надежный VPN.\nВыберите действие в меню ниже:",
            "image_url": "https://img.freepik.com/free-vector/vpn-connectivity-concept-illustration_114360-6483.jpg"
        },
        "plans": {
            "text": "Выберите подходящий тарифный план:",
            "image_url": "https://img.freepik.com/free-vector/vpn-connectivity-concept-illustration_114360-6483.jpg"
        },
        "connect_menu": {
            "text": "🚀 <b>Подключение</b>\n\nВыберите тарифный план:",
            "image_url": "https://img.freepik.com/free-vector/vpn-connectivity-concept-illustration_114360-6483.jpg"
        },
        "payment": {
            "text": "💳 <b>Выберите способ оплаты</b>\n\nТариф: <b>{plan_label}</b>",
            "image_url": "https://img.freepik.com/free-vector/vpn-connectivity-concept-illustration_114360-6483.jpg"
        },
        "profile": {
            "text": "👤 Профиль\n\n🆔 Ваш ID: <code>{telegram_id}</code>\n💰 Баланс: {balance}$\n📝 Статус: {status_text}\n{vpn_info}",
            "image_url": "https://img.freepik.com/free-vector/vpn-connectivity-concept-illustration_114360-6483.jpg"
        },
        "info": {
            "text": "ℹ️ <b>Информация</b>\n\n📍 <b>Как подключиться:</b>\n1. Скачайте приложение <b>v2raytun</b> для Android или iOS.\n2. Купите подписку в разделе «Подключиться».\n3. Перейдите в «Мой профиль» и скопируйте VPN-ключ (начинается с vless://).\n4. В приложении v2raytun нажмите «+» или «Импорт» и вставьте ключ.\n5. Нажмите на кнопку подключения.\n\n🔗 <b>Полезные ссылки:</b>\n- Проверка IP: <a href='https://whoer.net'>whoer.net</a>\n- Speedtest: <a href='https://speedtest.net'>speedtest.net</a>\n\n⚠️ Если ключ не отображается в профиле, нажмите кнопку «Получить ключ».",
            "image_url": "https://img.freepik.com/free-vector/vpn-connectivity-concept-illustration_114360-6483.jpg"
        },
        "support": {
            "text": "По всем вопросам пишите @admin",
            "image_url": "https://img.freepik.com/free-vector/customer-support-flat-design-concept_23-2148291411.jpg"
        },
        "referral": {
            "text": "👥 Реферальная система\n\nПриглашайте друзей и получайте бонусы на баланс!\n\nКоличество приглашенных: {count}\nВаша ссылка: {ref_link}",
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
