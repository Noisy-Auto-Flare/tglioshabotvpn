import uuid
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery, PreCheckoutQuery, LabeledPrice
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.models.models import User, Subscription, VPNKey, SubscriptionStatus, Payment, PaymentStatus
from bot.keyboards.keyboards import (
    get_main_menu_kb, 
    get_subscription_plans_kb, 
    get_payment_keyboard, 
    get_profile_keyboard,
    get_back_to_menu_kb
)
from backend.services.payments import cryptobot_service
from backend.services.vpn import vpn_service
from bot.services.ui_service import ui_service
from backend.core.config import settings

logger = logging.getLogger(__name__)
router = Router()

# --- Utility Functions ---

async def get_user(db: AsyncSession, telegram_id: int) -> Optional[User]:
    stmt = select(User).where(User.telegram_id == telegram_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()

# --- Command Handlers ---

@router.message(CommandStart())
async def cmd_start(message: Message, db: AsyncSession):
    """Handle /start command. Register new users and handle referrals."""
    try:
        user = await get_user(db, message.from_user.id)
        
        if not user:
            referral_code = str(uuid.uuid4())[:8]
            # Referral logic
            referred_by = None
            if message.text:
                args = message.text.split()
                if len(args) > 1:
                    ref_stmt = select(User).where(User.referral_code == args[1])
                    ref_result = await db.execute(ref_stmt)
                    inviter = ref_result.scalar_one_or_none()
                    if inviter:
                        referred_by = inviter.id
            
            user = User(
                telegram_id=message.from_user.id,
                referral_code=referral_code,
                referred_by=referred_by
            )
            db.add(user)
            await db.commit()
            logger.info(f"New user registered: {message.from_user.id}")
        
        await ui_service.render_screen(
            message,
            "👋 <b>Добро пожаловать в VPN бот!</b>\n\n"
            "Мы предоставляем быстрый и надежный VPN с премиальным качеством соединения.\n\n"
            "🚀 <b>Нажмите «Подключиться», чтобы начать!</b>",
            keyboard=get_main_menu_kb()
        )
    except Exception as e:
        logger.error(f"Error in cmd_start: {e}")
        await message.answer("Произошла ошибка при регистрации. Попробуйте позже.")

# --- Navigation Handlers ---

@router.callback_query(F.data == "menu")
async def show_menu(callback: CallbackQuery):
    await ui_service.render_screen(
        callback,
        "👋 <b>Главное меню</b>\n\n"
        "Выберите нужное действие:",
        keyboard=get_main_menu_kb()
    )

@router.callback_query(F.data == "connect")
async def process_connect(callback: CallbackQuery):
    await ui_service.render_screen(
        callback,
        "⚡ <b>Выберите тарифный план</b>\n\n"
        "Мы предлагаем стабильное соединение без ограничений по скорости.\n"
        "Пробный период доступен для новых пользователей!",
        keyboard=get_subscription_plans_kb()
    )

@router.callback_query(F.data == "profile")
async def process_profile(callback: CallbackQuery, db: AsyncSession):
    try:
        user = await get_user(db, callback.from_user.id)
        if not user:
            return await callback.answer("Пожалуйста, используйте /start", show_alert=True)
        
        now = datetime.now()
        sub_stmt = select(Subscription).where(
            Subscription.user_id == user.id,
            Subscription.status == SubscriptionStatus.ACTIVE,
            Subscription.end_date > now
        ).order_by(Subscription.end_date.desc()).limit(1)
        sub_result = await db.execute(sub_stmt)
        sub = sub_result.scalar_one_or_none()
        
        vpn_stmt = select(VPNKey).where(
            VPNKey.user_id == user.id,
            VPNKey.expire_at > now
        ).order_by(VPNKey.expire_at.desc()).limit(1)
        vpn_result = await db.execute(vpn_stmt)
        vpn_key = vpn_result.scalar_one_or_none()
        
        status_text = "❌ <b>Нет активной подписки</b>"
        if sub:
            days = (sub.end_date - now).days
            status_text = f"✅ <b>Активна до:</b> {sub.end_date.strftime('%d.%m.%Y')}\n⏳ <b>Осталось:</b> {max(0, days)} дней"
        
        profile_text = (
            f"👤 <b>Ваш профиль</b>\n\n"
            f"🆔 <b>ID:</b> <code>{user.telegram_id}</code>\n"
            f"💰 <b>Баланс:</b> {user.balance}$\n"
            f"📝 <b>Статус:</b> {status_text}\n"
        )
        
        if vpn_key and vpn_key.is_active:
            profile_text += f"\n🔑 <b>Ваш VPN Ключ:</b>\n<code>{vpn_key.config}</code>"
        elif sub:
            profile_text += f"\n🔑 <b>Ключ еще не создан</b>\nНажмите кнопку ниже, чтобы получить доступ."
        
        await ui_service.render_screen(
            callback,
            profile_text,
            keyboard=get_profile_keyboard(bool(sub), bool(vpn_key))
        )
    except Exception as e:
        logger.error(f"Error in process_profile: {e}")
        await callback.answer("Ошибка при получении профиля.")

@router.callback_query(F.data == "ref")
async def process_referral(callback: CallbackQuery, db: AsyncSession):
    try:
        user = await get_user(db, callback.from_user.id)
        if not user or not callback.bot: return await callback.answer("Ошибка")
        
        count_stmt = select(User).where(User.referred_by == user.id)
        count_result = await db.execute(count_stmt)
        count = len(count_result.scalars().all())
        
        bot_info = await callback.bot.get_me()
        ref_link = f"https://t.me/{bot_info.username}?start={user.referral_code}"
        
        text = (
            f"👥 <b>Реферальная система</b>\n\n"
            f"Приглашайте друзей и получайте <b>15%</b> от их пополнений на ваш бонусный баланс!\n\n"
            f"📈 <b>Ваша статистика:</b>\n"
            f"└ Приглашено: {count} чел.\n"
            f"└ Заработано: 0.00$\n\n"
            f"🔗 <b>Ваша ссылка:</b>\n<code>{ref_link}</code>"
        )
        await ui_service.render_screen(callback, text, keyboard=get_back_to_menu_kb())
    except Exception as e:
        logger.error(f"Error in process_referral: {e}")

@router.callback_query(F.data == "info")
async def process_info(callback: CallbackQuery):
    info_text = (
        "ℹ️ <b>Информация</b>\n\n"
        "🚀 <b>Как начать пользоваться:</b>\n"
        "1. Установите приложение <b>v2raytun</b>\n"
        "2. Купите подписку в меню «Подключиться»\n"
        "3. Скопируйте ключ из «Профиля»\n"
        "4. Вставьте ключ в приложение и нажмите <b>Connect</b>\n\n"
        "🌍 <b>Наши преимущества:</b>\n"
        "└ Высокая скорость (до 1 Гбит/с)\n"
        "└ Нет ограничений по трафику\n"
        "└ Работает во всех странах\n\n"
        "🆘 <b>Нужна помощь?</b>\n"
        "Пишите в нашу поддержку!"
    )
    await ui_service.render_screen(callback, info_text, keyboard=get_back_to_menu_kb())

@router.callback_query(F.data == "support")
async def process_support(callback: CallbackQuery):
    await ui_service.render_screen(
        callback,
        "🆘 <b>Центр поддержки</b>\n\n"
        "Если у вас возникли проблемы с подключением или оплатой, "
        "наш агент поддержки поможет вам в кратчайшие сроки.\n\n"
        "👤 <b>Администратор:</b> @admin",
        keyboard=get_back_to_menu_kb()
    )

# --- Payment Handlers ---

@router.callback_query(F.data.startswith("plan_"))
async def process_plan_selection(callback: CallbackQuery, db: AsyncSession):
    plan_id = callback.data.split("_")[1]
    
    try:
        user = await get_user(db, callback.from_user.id)
        if not user: return await callback.answer("Ошибка")

        if plan_id == "trial":
            stmt = select(Subscription).where(Subscription.user_id == user.id, Subscription.plan == "trial")
            res = await db.execute(stmt)
            if res.scalar_one_or_none():
                return await callback.answer("❌ Вы уже использовали пробный период!", show_alert=True)
            
            # ... existing trial logic ... (keeping it but using ui_service)
            now = datetime.now()
            end_date = now + timedelta(days=3)
            sub = Subscription(user_id=user.id, plan="trial", traffic_limit_gb=10, start_date=now, end_date=end_date, status=SubscriptionStatus.ACTIVE)
            db.add(sub)
            await db.flush()
            
            subscription_link = await asyncio.to_thread(vpn_service.create_user_and_get_link, user.telegram_id, 10, 3)
            config = subscription_link or f"vless://{uuid.uuid4()}@mock.vpn:443?type=grpc&serviceName=grpc#VPN"
            
            new_vpn = VPNKey(user_id=user.id, subscription_id=sub.id, uuid=str(uuid.uuid4()), config=config, expire_at=end_date, is_active=bool(subscription_link))
            db.add(new_vpn)
            await db.commit()
            
            await ui_service.render_screen(callback, "✅ <b>Пробный период активирован!</b>\n\nВаш ключ уже ждет вас в профиле.", keyboard=get_back_to_menu_kb())
            return

        # Paid plans
        plans = {
            "30": {"price": 5, "gb": 90, "stars": 500},
            "90": {"price": 12, "gb": 90, "stars": 1200},
            "180": {"price": 20, "gb": 180, "stars": 2000},
            "360": {"price": 35, "gb": 360, "stars": 3500},
        }
        plan = plans.get(plan_id)
        if not plan: return
        
        # CryptoBot Invoice
        invoice = await cryptobot_service.create_invoice(amount=plan["price"], payload=f"{user.id}:{plan_id}:{plan['gb']}")
        cryptobot_url = invoice["pay_url"] if invoice else None
        
        # TON Link
        ton_amount = plan["price"] * 0.5 # Simplified conversion 1 TON = 2$ roughly
        ton_url = f"https://app.tonkeeper.com/transfer/{settings.TON_WALLET}?amount={int(ton_amount * 1e9)}&text=vpn_{user.id}_{plan_id}"

        # Add Stars callback data to the payment keyboard
        keyboard = get_payment_keyboard(
            cryptobot_url=cryptobot_url or "", 
            ton_url=ton_url
        )
        # Update the pay_stars button to include plan_id
        for row in keyboard.inline_keyboard:
            for button in row:
                if button.callback_data == "pay_stars":
                    button.callback_data = f"pay_stars_{plan_id}"

        await ui_service.render_screen(
            callback,
            f"💳 <b>Оплата подписки</b>\n\n"
            f"📦 <b>Тариф:</b> {plan_id} дней\n"
            f"📊 <b>Трафик:</b> {plan['gb']} GB\n"
            f"💰 <b>Цена:</b> {plan['price']}$\n\n"
            f"Выберите удобный способ оплаты:",
            keyboard=keyboard
        )
    except Exception as e:
        logger.error(f"Error in process_plan_selection: {e}")

@router.callback_query(F.data.startswith("pay_stars_"))
async def process_stars_payment(callback: CallbackQuery):
    if not callback.message or not callback.bot: return
    
    plan_id = callback.data.split("_")[2]
    plans = {
        "30": {"price": 5, "gb": 90, "stars": 500},
        "90": {"price": 12, "gb": 90, "stars": 1200},
        "180": {"price": 20, "gb": 180, "stars": 2000},
        "360": {"price": 35, "gb": 360, "stars": 3500},
    }
    plan = plans.get(plan_id)
    if not plan: return

    await callback.bot.send_invoice(
        chat_id=callback.from_user.id,
        title=f"VPN {plan_id} дней",
        description=f"Подписка на VPN сервис ({plan['gb']} GB трафика)",
        payload=f"stars:{plan_id}:{plan['gb']}",
        provider_token="", # Empty for Stars
        currency="XTR",
        prices=[LabeledPrice(label="VPN", amount=plan["stars"])]
    )
    await callback.answer()

@router.pre_checkout_query()
async def process_pre_checkout(pre_checkout_query: PreCheckoutQuery):
    await pre_checkout_query.answer(ok=True)

@router.message(F.successful_payment)
async def process_successful_payment(message: Message, db: AsyncSession):
    if not message.successful_payment: return
    
    payload = message.successful_payment.invoice_payload
    if payload.startswith("stars:"):
        _, plan_id, traffic_gb = payload.split(":")
        
        user = await get_user(db, message.from_user.id)
        if not user: return
        
        # Activate subscription
        now = datetime.now()
        end_date = now + timedelta(days=int(plan_id))
        
        sub = Subscription(
            user_id=user.id,
            plan=plan_id,
            traffic_limit_gb=int(traffic_gb),
            start_date=now,
            end_date=end_date,
            status=SubscriptionStatus.ACTIVE
        )
        db.add(sub)
        await db.commit()
        
        await message.answer(
            "✅ <b>Оплата прошла успешно!</b>\n\n"
            "Ваша подписка активирована. Перейдите в профиль, чтобы получить ключ.",
            reply_markup=get_main_menu_kb()
        )

@router.callback_query(F.data == "check_payment")
async def process_check_payment(callback: CallbackQuery):
    await callback.answer("⏳ Платеж проверяется... Если вы оплатили через CryptoBot или TON, подписка активируется в течение 2-5 минут.", show_alert=True)

@router.callback_query(F.data == "buy_subscription")
async def process_buy_sub_callback(callback: CallbackQuery):
    await process_connect(callback)

@router.callback_query(F.data == "get_vpn_key")
async def process_get_vpn_key(callback: CallbackQuery, db: AsyncSession):
    try:
        user = await get_user(db, callback.from_user.id)
        if not user: return await callback.answer("Ошибка")

        now = datetime.now()
        sub_stmt = select(Subscription).where(
            Subscription.user_id == user.id,
            Subscription.status == SubscriptionStatus.ACTIVE,
            Subscription.end_date > now
        ).order_by(Subscription.end_date.desc()).limit(1)
        sub_result = await db.execute(sub_stmt)
        sub = sub_result.scalar_one_or_none()

        if not sub:
            return await callback.answer("У вас нет активной подписки.", show_alert=True)

        await callback.answer("⚙️ Генерируем ключ... Пожалуйста, подождите.", show_alert=False)
        
        remaining_days = max(1, (sub.end_date - now).days)
        traffic_gb = sub.traffic_limit_gb or 30
        
        subscription_link = await asyncio.to_thread(
            vpn_service.create_user_and_get_link,
            user.telegram_id,
            traffic_gb,
            remaining_days
        )
        
        config = subscription_link or f"vless://{uuid.uuid4()}@mock.vpn:443?type=grpc&serviceName=grpc#VPN"
        is_active = bool(subscription_link)

        # Update or create VPNKey
        vpn_stmt = select(VPNKey).where(VPNKey.user_id == user.id).order_by(VPNKey.expire_at.desc()).limit(1)
        vpn_res = await db.execute(vpn_stmt)
        existing_vpn = vpn_res.scalar_one_or_none()
        
        if existing_vpn:
            existing_vpn.config = config
            existing_vpn.is_active = is_active
            existing_vpn.expire_at = sub.end_date
        else:
            new_vpn = VPNKey(
                user_id=user.id,
                subscription_id=sub.id,
                uuid=str(uuid.uuid4()),
                config=config,
                expire_at=sub.end_date,
                is_active=is_active
            )
            db.add(new_vpn)
            
        await db.commit()
        await ui_service.render_screen(callback, "✅ <b>Ключ успешно обновлен!</b>\n\nПроверьте ваш профиль.", keyboard=get_main_menu_kb())
            
    except Exception as e:
        logger.error(f"Error in process_get_vpn_key: {e}")
        await callback.answer("Ошибка при получении ключа.", show_alert=True)
