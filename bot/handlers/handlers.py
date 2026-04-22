import os
import uuid
from datetime import datetime, timedelta, timezone
from aiogram import Router, F, types
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from backend.models.models import User, Subscription, VPNKey, SubscriptionStatus, Payment, PaymentStatus
from bot.keyboards.keyboards import get_main_menu, get_subscription_plans, get_payment_keyboard
from backend.services.payments import cryptobot_service
from backend.services.vpn import vpn_service

router = Router()

@router.message(CommandStart())
async def cmd_start(message: Message, db: AsyncSession):
    # Register user if not exists
    stmt = select(User).where(User.telegram_id == message.from_user.id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    
    if not user:
        # Generate referral code
        referral_code = str(uuid.uuid4())[:8]
        
        # Check if invited by someone
        args = message.text.split()
        referred_by = None
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
    
    await message.answer(
        "👋 Добро пожаловать в VPN бот!\n\n"
        "Мы предоставляем быстрый и надежный VPN.\n"
        "Выберите действие в меню ниже:",
        reply_markup=get_main_menu()
    )

@router.message(F.text == "Подключиться")
async def process_connect(message: Message):
    await message.answer(
        "Выберите подходящий тарифный план:",
        reply_markup=get_subscription_plans()
    )

@router.message(F.text == "Мой профиль")
async def process_profile(message: Message, db: AsyncSession):
    stmt = select(User).where(User.telegram_id == message.from_user.id)
    result = await db.execute(stmt)
    user = result.scalar_one()
    
    # Get active subscription
    sub_stmt = select(Subscription).where(
        Subscription.user_id == user.id,
        Subscription.status == SubscriptionStatus.ACTIVE
    ).order_by(Subscription.end_date.desc()).limit(1)
    sub_result = await db.execute(sub_stmt)
    sub = sub_result.scalar_one_or_none()
    
    # Get VPN config
    vpn_stmt = select(VPNKey).where(VPNKey.user_id == user.id)
    vpn_result = await db.execute(vpn_stmt)
    vpn_key = vpn_result.scalar_one_or_none()
    
    status_text = "❌ Нет активной подписки"
    if sub:
        now = datetime.now()
        remaining = sub.end_date - now
        days = remaining.days
        status_text = f"✅ Активна до: {sub.end_date.strftime('%d.%m.%Y %H:%M')}\nОсталось дней: {max(0, days)}"
    
    profile_text = (
        f"👤 Профиль\n\n"
        f"🆔 Ваш ID: {user.telegram_id}\n"
        f"💰 Баланс: {user.balance}$\n"
        f"📝 Статус: {status_text}\n"
    )
    
    if vpn_key:
        profile_text += f"\n🔑 VPN Ключ:\n<code>{vpn_key.config}</code>"
    
    await message.answer(profile_text, parse_mode="HTML")

@router.message(F.text == "Реферальная система")
async def process_referral(message: Message, db: AsyncSession):
    stmt = select(User).where(User.telegram_id == message.from_user.id)
    result = await db.execute(stmt)
    user = result.scalar_one()
    
    # Count referrals
    count_stmt = select(User).where(User.referred_by == user.id)
    count_result = await db.execute(count_stmt)
    count = len(count_result.scalars().all())
    
    bot_info = await message.bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={user.referral_code}"
    
    text = (
        f"👥 Реферальная система\n\n"
        f"Приглашайте друзей и получайте бонусы на баланс!\n\n"
        f"Количество приглашенных: {count}\n"
        f"Ваша ссылка: {ref_link}"
    )
    await message.answer(text)

@router.message(F.text == "Информация")
async def process_info(message: Message):
    text = (
        "ℹ️ Информация\n\n"
        "Наш VPN работает на протоколе VLESS (через RemnaWave).\n"
        "📍 Как подключиться:\n"
        "1. Скачайте приложение (v2rayNG для Android, Streisand для iOS)\n"
        "2. Скопируйте ключ из профиля\n"
        "3. Импортируйте ключ в приложение\n\n"
        "🔗 Ссылки:\n"
        "- Проверка IP: https://whoer.net\n"
        "- Speedtest: https://speedtest.net"
    )
    await message.answer(text)

@router.message(F.text == "Поддержка")
async def process_support(message: Message):
    await message.answer("По всем вопросам пишите @admin")

@router.callback_query(F.data.startswith("plan_"))
async def process_plan_selection(callback: CallbackQuery, db: AsyncSession):
    plan_id = callback.data.split("_")[1]
    
    # Check for trial plan
    if plan_id == "trial":
        stmt = select(Subscription).where(
            Subscription.user_id == (select(User.id).where(User.telegram_id == callback.from_user.id)),
            Subscription.plan == "trial"
        )
        res = await db.execute(stmt)
        if res.scalar_one_or_none():
            await callback.answer("Вы уже использовали пробный период!", show_alert=True)
            return
        
        # Give trial plan directly
        # Need user object
        user_stmt = select(User).where(User.telegram_id == callback.from_user.id)
        user_res = await db.execute(user_stmt)
        user = user_res.scalar_one()
        
        now = datetime.now()
        end_date = now + timedelta(days=3)
        
        sub = Subscription(
            user_id=user.id,
            plan="trial",
            start_date=now,
            end_date=end_date,
            status=SubscriptionStatus.ACTIVE
        )
        db.add(sub)
        
        # Provision VPN
        vpn_data = await vpn_service.create_vpn_user(user.telegram_id, expire_at=int(end_date.timestamp()))
        if vpn_data:
            config = await vpn_service.get_vpn_config(vpn_data["uuid"])
            new_vpn = VPNKey(
                user_id=user.id,
                uuid=vpn_data["uuid"],
                config=config or "Config will be available soon...",
                expire_at=end_date
            )
            db.add(new_vpn)
            
        await db.commit()
        await callback.message.edit_text("✅ Пробный период активирован на 3 дня!")
        return

    # For paid plans, create invoice
    plans = {"30": 5, "90": 12, "180": 20, "360": 35}
    price = plans.get(plan_id, 5)
    
    user_stmt = select(User).where(User.telegram_id == callback.from_user.id)
    user_res = await db.execute(user_stmt)
    user = user_res.scalar_one()
    
    invoice = await cryptobot_service.create_invoice(
        amount=price,
        payload=f"{user.id}:{plan_id}"
    )
    
    if invoice:
        await callback.message.edit_text(
            f"Оплатите {price}$ для активации подписки на {plan_id} дней:",
            reply_markup=get_payment_keyboard(invoice["pay_url"])
        )
    else:
        await callback.answer("Ошибка создания счета. Попробуйте позже.", show_alert=True)
