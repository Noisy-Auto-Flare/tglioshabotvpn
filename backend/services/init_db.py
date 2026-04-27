import logging
from sqlalchemy.ext.asyncio import AsyncSession
from backend.services.content import ContentService

logger = logging.getLogger(__name__)

async def init_screens(db: AsyncSession):
    content_service = ContentService(db)
    
    default_screens = {
        "main_menu": {
            "text": "👋 <b>Добро пожаловать в VPN бот!</b>\n\nМы предоставляем быстрый и надежный VPN.\nВыберите действие в меню ниже:",
            "image_url": "https://i.ibb.co/j9PDJHrD/image.png"
        },
        "buy_menu": {
            "text": "🚀 <b>Подключение</b>\n\nВыберите тип доступа:",
            "image_url": "https://i.ibb.co/j9PDJHrD/image.png"
        },
        "tariff_list": {
            "text": "  <b>Выберите тарифный план</b>\n\nМы подготовили лучшие условия для вас:",
            "image_url": "https://i.ibb.co/HDJfqBjp/image.png"
        },
        "payment": {
            "text": "💳 <b>Оплата покупки</b>\n\nТариф: <b>{plan_label}</b>\nСумма: <b>{price}р</b>\n\nВыберите удобный способ оплаты:",
            "image_url": "https://i.ibb.co/3yFztHqy/2.png"
        },
        "profile_main": {
            "text": "<tg-emoji emoji-id=\"5362079447136610876\">👤</tg-emoji> <b>Мой профиль</b>\n\n<tg-emoji emoji-id=\"5395444784611480792\">🆔</tg-emoji> Ваш ID: <code>{telegram_id}</code>\n<tg-emoji emoji-id=\"5278467510604160626\">💰</tg-emoji> Баланс: <b>{balance}₽</b>\n<tg-emoji emoji-id=\"5348178055338671586\">📝</tg-emoji> Статус подписки: {status_text}\n\n<tg-emoji emoji-id=\"5197288647275071607\">🔑</tg-emoji> <b>Ваш ключ:</b>\n<code>{vpn_info}</code>",
            "image_url": "https://i.ibb.co/PvqTBwvW/image.png"
        },
        "statistics": {
            "text": "<tg-emoji emoji-id=\"5449872877929127395\">📊</tg-emoji> <b>Статистика</b>\n\n<tg-emoji emoji-id=\"5346176879751612829\">🆔</tg-emoji> ID: <code>{user_id}</code>\n<tg-emoji emoji-id=\"5346176879751612829\">📝</tg-emoji> Статус подписки: {status}\n<tg-emoji emoji-id=\"5346176879751612829\">📅</tg-emoji> Остаток дней: <b>{days_left}</b>\n<tg-emoji emoji-id=\"5346176879751612829\">🛒</tg-emoji> Кол-во покупок: <b>{total_orders}</b>\n<tg-emoji emoji-id=\"5346176879751612829\">⚙️</tg-emoji> Текущий протокол: <b>{protocol_type}</b>\n<tg-emoji emoji-id=\"5346176879751612829\">📊</tg-emoji> Лимит трафика: <b>{used_gb} / {total_gb} GB</b>",
            "image_url": "https://i.ibb.co/PGxF0KCz/6.png"
        },
        "deposit_menu": {
            "text": "💰 <b>Пополнение баланса</b>\n\nВыберите способ оплаты для пополнения внутреннего кошелька:",
            "image_url": "https://i.ibb.co/PvqTBwvW/image.png"
        },
        "info_menu": {
            "text": "ℹ️ <b>Информация</b>\n\nЗдесь вы найдете все необходимые инструкции и полезные ссылки для работы с нашим сервисом.",
            "image_url": "https://i.ibb.co/7dH56jZ7/3.png"
        },
        "setup_guides": {
            "text": "📖 <b>Инструкции по настройке</b>\n\nВыберите вашу платформу, чтобы получить подробное руководство:",
            "image_url": "https://i.ibb.co/Dgky69mM/5.png"
        },
        "referral_system": {
            "text": "👥 <b>Реферальная система</b>\n\nПриглашайте друзей и получайте <b>+2 дня</b> к вашей подписке за каждого приглашенного!\n\nКоличество приглашенных: <b>{count}</b>\nВаша ссылка: <code>{ref_link}</code>",
            "image_url": "https://i.ibb.co/mk5W6Vt/4.png"
        },
        "reset_key_confirm": {
            "text": "⚠️ <b>Подтверждение сброса ключа</b>\n\nВы уверены что хотите удалить старый ключ и получить новый?\nДанная функция доступна всего лишь 3 раза.\n\nКоличество доступных сбросов для текущей подписки: <b>{remaining_resets}</b>",
        },
        "sub_management": {
            "text": "⚙️ <b>Управление подпиской</b>\n\nЗдесь вы можете управлять вашим VPN-доступом, обновить ключ или продлить текущий тариф.\n\nТариф: <b>{plan_label}</b>\nДо: <b>{end_date}</b>",
        },
        "my_subscriptions": {
            "text": "📜 <b>Ваши подписки</b>\n\nВыберите подписку из списка ниже для управления:",
        },
        "required_sub": {
            "text": "⚠️ <b>Обязательная подписка</b>\n\nДля использования бота вы должны быть подписаны на наш канал {channel}.\n\nПодпишитесь и нажмите кнопку «Проверить подписку».",
            "image_url": "https://i.ibb.co/j9PDJHrD/image.png"
        }
    }

    for key, data in default_screens.items():
        logger.info(f"Syncing screen: {key}")
        await content_service.update_screen(
            key, 
            text=data["text"], 
            image_url=data.get("image_url")
        )
