import asyncio
import logging
import uuid
from datetime import datetime, timedelta
from typing import Optional, Union

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message, LabeledPrice, PreCheckoutQuery
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.models import (
    Payment,
    PaymentStatus,
    Subscription,
    SubscriptionStatus,
    User,
    VPNKey,
)
from backend.services.tasks import (
    generate_mock_config,
    parse_payment_payload,
    process_successful_payment,
)
from backend.services.vpn import vpn_service
from backend.core.config import settings
from bot.keyboards.keyboards import (
    get_main_menu,
    get_buy_menu,
    get_tariff_list,
    get_payment_methods,
    get_profile_main_keyboard,
    get_info_menu_keyboard,
    get_setup_guides_keyboard,
    get_back_to_main,
    get_deposit_methods,
)
from bot.services.renderer import render_screen

logger = logging.getLogger(__name__)
router = Router()

async def _get_user_by_tg(db: AsyncSession, telegram_id: int) -> Optional[User]:
    stmt = select(User).where(User.telegram_id == telegram_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()

async def _show_profile(event: Union[Message, CallbackQuery], db: AsyncSession, user: User) -> None:
    now = datetime.now()
    sub_stmt = (
        select(Subscription)
        .where(
            Subscription.user_id == user.id,
            Subscription.status == SubscriptionStatus.ACTIVE,
            Subscription.end_date > now,
        )
        .order_by(Subscription.end_date.desc())
        .limit(1)
    )
    sub_result = await db.execute(sub_stmt)
    sub = sub_result.scalar_one_or_none()

    vpn_stmt = (
        select(VPNKey)
        .where(VPNKey.user_id == user.id, VPNKey.expire_at > now)
        .order_by(VPNKey.expire_at.desc())
        .limit(1)
    )
    vpn_result = await db.execute(vpn_stmt)
    vpn_key = vpn_result.scalar_one_or_none()

    status_text = "❌ Нет активной подписки"
    vpn_info = ""
    if sub:
        remaining = sub.end_date - now
        status_text = f"✅ Активна (осталось {max(0, remaining.days)} дн.)"
        
        if vpn_key and vpn_key.is_active:
            vpn_info = f"\n🔑 <b>Ваш ключ:</b>\n<code>{vpn_key.config}</code>"
        elif vpn_key:
            vpn_info = "\n🔑 <b>Ключ в процессе создания...</b>"
        else:
            vpn_info = "\n🔑 <b>Ключ еще не получен.</b>"

    await render_screen(
        event,
        db,
        "profile_main",
        keyboard=get_profile_main_keyboard(),
        telegram_id=user.telegram_id,
        balance=user.balance,
        status_text=status_text,
        vpn_info=vpn_info,
    )

@router.message(CommandStart())
async def cmd_start(message: Message, db: AsyncSession):
    if not message.from_user:
        return
    user = await _get_user_by_tg(db, message.from_user.id)
    if not user:
        referral_code = str(uuid.uuid4())[:8]
        referred_by = None
        if message.text and len(message.text.split()) > 1:
            ref_code = message.text.split()[1]
            ref_stmt = select(User).where(User.referral_code == ref_code)
            inviter = (await db.execute(ref_stmt)).scalar_one_or_none()
            if inviter:
                referred_by = inviter.id

        user = User(
            telegram_id=message.from_user.id,
            referral_code=referral_code,
            referred_by=referred_by,
        )
        db.add(user)
        await db.commit()

    await render_screen(message, db, "main_menu", keyboard=get_main_menu())

@router.callback_query(F.data == "main_menu")
async def open_main_menu(callback: CallbackQuery, db: AsyncSession):
    await render_screen(callback, db, "main_menu", keyboard=get_main_menu())
    await callback.answer()

@router.callback_query(F.data == "buy_menu")
async def open_buy_menu(callback: CallbackQuery, db: AsyncSession):
    await render_screen(callback, db, "buy_menu", keyboard=get_buy_menu())
    await callback.answer()

@router.callback_query(F.data == "tariff_list")
async def open_tariff_list(callback: CallbackQuery, db: AsyncSession):
    await render_screen(callback, db, "tariff_list", keyboard=get_tariff_list())
    await callback.answer()

@router.callback_query(F.data == "trial_activate")
async def process_trial(callback: CallbackQuery, db: AsyncSession):
    user = await _get_user_by_tg(db, callback.from_user.id)
    if not user: return
    
    stmt = select(Subscription).where(Subscription.user_id == user.id, Subscription.plan == "trial")
    if (await db.execute(stmt)).scalar_one_or_none():
        await callback.answer("❌ Пробный период уже использован!", show_alert=True)
        return

    now = datetime.now()
    end_date = now + timedelta(days=3)
    sub = Subscription(user_id=user.id, plan="trial", traffic_limit_gb=10, start_date=now, end_date=end_date)
    db.add(sub)
    await db.flush()

    link = await asyncio.to_thread(vpn_service.create_user_and_get_link, user.telegram_id, 10, 3)
    db.add(VPNKey(user_id=user.id, subscription_id=sub.id, config=link or "Error", expire_at=end_date, is_active=bool(link)))
    await db.commit()
    
    await callback.answer("✅ Пробный период активирован на 3 дня!", show_alert=True)
    await _show_profile(callback, db, user)

@router.callback_query(F.data.startswith("pay_order_"))
async def open_payment_methods(callback: CallbackQuery, db: AsyncSession):
    plan_id = callback.data.split("_")[2]
    plan = settings.PLANS.get(plan_id)
    if not plan: return
    
    await render_screen(
        callback, db, "payment", 
        keyboard=get_payment_methods(plan_id),
        plan_label=plan["label"],
        price=plan["price"]
    )
    await callback.answer()

@router.callback_query(F.data == "profile_main")
async def open_profile_main(callback: CallbackQuery, db: AsyncSession):
    user = await _get_user_by_tg(db, callback.from_user.id)
    if not user: return
    await _show_profile(callback, db, user)
    await callback.answer()

@router.callback_query(F.data == "statistics")
async def open_statistics(callback: CallbackQuery, db: AsyncSession):
    user = await _get_user_by_tg(db, callback.from_user.id)
    if not user: return

    # Подсчет покупок
    orders_stmt = select(func.count(Payment.id)).where(Payment.user_id == user.id, Payment.status == PaymentStatus.COMPLETED)
    total_orders = (await db.execute(orders_stmt)).scalar() or 0

    # Активная подписка
    sub_stmt = select(Subscription).where(Subscription.user_id == user.id, Subscription.status == SubscriptionStatus.ACTIVE).order_by(Subscription.end_date.desc()).limit(1)
    sub = (await db.execute(sub_stmt)).scalar_one_or_none()
    
    days_left = 0
    total_gb = 0
    if sub:
        days_left = max(0, (sub.end_date - datetime.now()).days)
        total_gb = sub.traffic_limit_gb or 0

    await render_screen(
        callback, db, "statistics",
        keyboard=get_back_to_main(),
        user_id=user.telegram_id,
        status="Active" if sub else "Inactive",
        days_left=days_left,
        total_orders=total_orders,
        protocol_type="VLESS/Reality",
        used_gb=0, # Временно 0, пока нет интеграции трафика
        total_gb=total_gb
    )
    await callback.answer()

@router.callback_query(F.data == "deposit_menu")
async def open_deposit_menu(callback: CallbackQuery, db: AsyncSession):
    await render_screen(callback, db, "deposit_menu", keyboard=get_deposit_methods())
    await callback.answer()

@router.callback_query(F.data == "info_menu")
async def open_info_menu(callback: CallbackQuery, db: AsyncSession):
    await render_screen(callback, db, "info_menu", keyboard=get_info_menu_keyboard())
    await callback.answer()

@router.callback_query(F.data == "setup_guides")
async def open_setup_guides(callback: CallbackQuery, db: AsyncSession):
    await render_screen(callback, db, "setup_guides", keyboard=get_setup_guides_keyboard())
    await callback.answer()

@router.callback_query(F.data == "referral_system")
async def open_referral(callback: CallbackQuery, db: AsyncSession):
    user = await _get_user_by_tg(db, callback.from_user.id)
    if not user: return
    
    count_stmt = select(func.count(User.id)).where(User.referred_by == user.id)
    count = (await db.execute(count_stmt)).scalar() or 0
    
    bot_info = await callback.bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={user.referral_code}"
    
    await render_screen(callback, db, "referral_system", keyboard=get_back_to_main(), count=count, ref_link=ref_link)
    await callback.answer()

@router.callback_query(F.data.startswith("pay_balance_"))
async def process_pay_balance(callback: CallbackQuery, db: AsyncSession):
    plan_id = callback.data.split("_")[2]
    user = await _get_user_by_tg(db, callback.from_user.id)
    plan = settings.PLANS.get(plan_id)
    
    if not user or not plan: return
    
    if user.balance < plan["price"]:
        await callback.answer("❌ Недостаточно средств на балансе!", show_alert=True)
        return
    
    user.balance -= plan["price"]
    await process_successful_payment(db, user.id, int(plan_id), plan["price"], f"bal_{user.id}_{int(datetime.now().timestamp())}", traffic_gb=plan["gb"], provider="balance")
    await db.commit()
    await callback.answer("✅ Оплата с баланса прошла успешно!", show_alert=True)
    await _show_profile(callback, db, user)

# Заглушки для других методов оплаты
@router.callback_query(F.data.regexp(r"^(pay|dep)_(sbp|cryptobot|cryptomus|stars|ton)"))
async def process_external_payments(callback: CallbackQuery):
    await callback.answer("🛠 Этот метод оплаты сейчас настраивается...", show_alert=True)
