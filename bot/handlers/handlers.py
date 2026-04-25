import asyncio
import logging
import uuid
from datetime import datetime, timedelta
from typing import Optional, Union

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message, LabeledPrice, PreCheckoutQuery
from backend.services.payment_service import PaymentService
from backend.services.payments.cryptobot import cryptobot_service
from backend.services.payments.cryptomus import cryptomus_service
from backend.services.payments.freekassa import freekassa_service
from backend.services.payments.abstract import ton_service
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
    get_reset_key_confirm_keyboard,
    get_sub_management_keyboard,
)
from bot.services.renderer import render_screen, safe_edit

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

    vpn_key = None
    if sub:
        vpn_stmt = (
            select(VPNKey)
            .where(
                VPNKey.user_id == user.id, 
                VPNKey.subscription_id == sub.id,
                VPNKey.is_active == True
            )
            .order_by(VPNKey.id.desc())
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

    vpn_data = await asyncio.to_thread(vpn_service.create_user_and_get_link, user.telegram_id, 10, 3)
    if vpn_data:
        db.add(VPNKey(
            user_id=user.id, 
            subscription_id=sub.id, 
            uuid=vpn_data["uuid"],
            config=vpn_data["link"], 
            expire_at=end_date, 
            is_active=True
        ))
    else:
        db.add(VPNKey(
            user_id=user.id, 
            subscription_id=sub.id, 
            config="Error", 
            expire_at=end_date, 
            is_active=False,
            error_message="RemnaWave API error"
        ))
    await db.commit()
    
    await callback.answer("✅ Пробный период активирован на 3 дня!", show_alert=True)
    await _show_profile(callback, db, user)

from aiogram.types import LabeledPrice, PreCheckoutQuery

@router.callback_query(F.data == "profile_main")
async def open_profile_main(callback: CallbackQuery, db: AsyncSession):
    user = await _get_user_by_tg(db, callback.from_user.id)
    if not user: return
    await _show_profile(callback, db, user)
    await callback.answer()

@router.callback_query(F.data == "sub_management")
async def open_sub_management(callback: CallbackQuery, db: AsyncSession):
    user = await _get_user_by_tg(db, callback.from_user.id)
    if not user: return

    # Get active subscription
    sub_stmt = select(Subscription).where(
        Subscription.user_id == user.id,
        Subscription.status == SubscriptionStatus.ACTIVE,
        Subscription.end_date > datetime.now()
    ).order_by(Subscription.end_date.desc()).limit(1)
    sub = (await db.execute(sub_stmt)).scalar_one_or_none()

    if not sub:
        await callback.answer("❌ У вас нет активной подписки.", show_alert=True)
        return

    plan_label = settings.PLANS.get(sub.plan, {}).get("label", f"{sub.plan} дней")
    end_date_str = sub.end_date.strftime("%d.%m.%Y")

    await render_screen(
        callback, db, "sub_management",
        keyboard=get_sub_management_keyboard(),
        plan_label=plan_label,
        end_date=end_date_str
    )
    await callback.answer()

@router.callback_query(F.data == "get_key")
async def process_get_key(callback: CallbackQuery, db: AsyncSession):
    user = await _get_user_by_tg(db, callback.from_user.id)
    if not user: return
    
    # Just show profile which contains the key
    await _show_profile(callback, db, user)
    await callback.answer("🔑 Ваш ключ отображен в профиле")

@router.callback_query(F.data == "reset_key_confirm")
async def confirm_reset_key(callback: CallbackQuery, db: AsyncSession):
    user = await _get_user_by_tg(db, callback.from_user.id)
    if not user: return

    # Get active subscription
    sub_stmt = select(Subscription).where(
        Subscription.user_id == user.id,
        Subscription.status == SubscriptionStatus.ACTIVE,
        Subscription.end_date > datetime.now()
    ).order_by(Subscription.end_date.desc()).limit(1)
    sub = (await db.execute(sub_stmt)).scalar_one_or_none()

    if not sub:
        await callback.answer("❌ У вас нет активной подписки для сброса ключа.", show_alert=True)
        return

    remaining = 3 - sub.reset_count
    if remaining <= 0:
        await callback.answer("❌ Вы исчерпали лимит сбросов ключа (макс. 3) для этой подписки.", show_alert=True)
        return

    await render_screen(
        callback, db, "reset_key_confirm",
        keyboard=get_reset_key_confirm_keyboard(),
        remaining_resets=remaining
    )
    await callback.answer()

@router.callback_query(F.data == "reset_key_execute")
async def execute_reset_key(callback: CallbackQuery, db: AsyncSession):
    user = await _get_user_by_tg(db, callback.from_user.id)
    if not user: return

    # 1. Get active sub and key
    sub_stmt = select(Subscription).where(
        Subscription.user_id == user.id,
        Subscription.status == SubscriptionStatus.ACTIVE,
        Subscription.end_date > datetime.now()
    ).order_by(Subscription.end_date.desc()).limit(1)
    sub = (await db.execute(sub_stmt)).scalar_one_or_none()

    if not sub or sub.reset_count >= 3:
        await callback.answer("❌ Сброс невозможен.", show_alert=True)
        return

    # Get current active key
    vpn_stmt = select(VPNKey).where(
        VPNKey.user_id == user.id,
        VPNKey.subscription_id == sub.id,
        VPNKey.is_active == True
    ).order_by(VPNKey.id.desc()).limit(1)
    old_key = (await db.execute(vpn_stmt)).scalar_one_or_none()

    # 2. Delete old user from RemnaWave
    if old_key:
        if old_key.uuid:
            logger.info(f"Deleting old RemnaWave user: {old_key.uuid}")
            success = await asyncio.to_thread(vpn_service.delete_user, old_key.uuid)
            if success:
                logger.info(f"Successfully deleted RemnaWave user: {old_key.uuid}")
                old_key.is_active = False
                old_key.error_message = "Reset by user"
                await db.commit()
            else:
                logger.error(f"Failed to delete old RemnaWave user {old_key.uuid}, but proceeding with creation")
                # We still deactivate it in DB to not show it
                old_key.is_active = False
                await db.commit()
        else:
            logger.warning(f"Old key found (id={old_key.id}) but has no UUID to delete from RemnaWave")
            old_key.is_active = False
            await db.commit()
    else:
        logger.info(f"No active old key found to delete for user {user.id}")

    # 3. Create new user in RemnaWave
    days_left = max(1, (sub.end_date - datetime.now()).days)
    vpn_data = await asyncio.to_thread(
        vpn_service.create_user_and_get_link,
        user.telegram_id,
        sub.traffic_limit_gb or 30,
        days_left
    )

    if vpn_data:
        new_key = VPNKey(
            user_id=user.id,
            subscription_id=sub.id,
            uuid=vpn_data["uuid"],
            config=vpn_data["link"],
            expire_at=sub.end_date,
            is_active=True
        )
        db.add(new_key)
        sub.reset_count += 1
        await db.commit()
        await callback.answer("✅ Ключ успешно сброшен!", show_alert=True)
    else:
        await callback.answer("❌ Ошибка при создании нового ключа. Обратитесь в поддержку.", show_alert=True)

    await _show_profile(callback, db, user)

@router.callback_query(F.data == "statistics")
async def open_statistics(callback: CallbackQuery, db: AsyncSession):
    user = await _get_user_by_tg(db, callback.from_user.id)
    if not user: return

    # Подсчет покупок
    orders_stmt = select(func.count(Payment.id)).where(Payment.user_id == user.id, Payment.status == PaymentStatus.SUCCESS)
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
        used_gb=0,
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
    if not user or not callback.bot: return
    
    count_stmt = select(func.count(User.id)).where(User.referred_by == user.id)
    count = (await db.execute(count_stmt)).scalar() or 0
    
    bot_info = await callback.bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={user.referral_code}"
    
    await render_screen(callback, db, "referral_system", keyboard=get_back_to_main(), count=count, ref_link=ref_link)
    await callback.answer()

@router.callback_query(F.data.startswith("pay_order_"))
async def open_payment_methods(callback: CallbackQuery, db: AsyncSession):
    if not callback.data: return
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

@router.callback_query(F.data.startswith("pay_balance_"))
async def process_pay_balance(callback: CallbackQuery, db: AsyncSession):
    if not callback.data: return
    plan_id = callback.data.split("_")[2]
    user = await _get_user_by_tg(db, callback.from_user.id)
    plan = settings.PLANS.get(plan_id)
    
    if not user or not plan: return
    
    if user.balance < plan["price"]:
        await callback.answer("❌ Недостаточно средств на балансе!", show_alert=True)
        return
    
    payment_service = PaymentService(db)
    ext_id = f"bal_{user.id}_{int(datetime.now().timestamp())}"
    await payment_service.create_payment(
        user_id=user.id,
        tariff_id=plan_id,
        provider="balance",
        amount=plan["price"],
        external_id=ext_id
    )
    
    user.balance -= plan["price"]
    await payment_service.process_success(ext_id)
    
    await callback.answer("✅ Оплата с баланса прошла успешно!", show_alert=True)
    await _show_profile(callback, db, user)

@router.callback_query(F.data.startswith("pay_cryptobot_"))
async def process_pay_cryptobot(callback: CallbackQuery, db: AsyncSession):
    if not callback.data or not callback.message: return
    plan_id = callback.data.split("_")[2]
    user = await _get_user_by_tg(db, callback.from_user.id)
    plan = settings.PLANS.get(plan_id)
    if not user or not plan: return

    amount_usd = float(plan["price"]) / settings.USD_RUB_RATE
    invoice = await cryptobot_service.create_invoice(
        amount=amount_usd,
        payload=f"{user.id}:{plan_id}",
        currency="USD"
    )
    
    if not invoice:
        await callback.answer("❌ Ошибка CryptoBot. Попробуйте позже.", show_alert=True)
        return

    payment_service = PaymentService(db)
    await payment_service.create_payment(
        user_id=user.id,
        tariff_id=plan_id,
        provider="cryptobot",
        amount=plan["price"],
        external_id=str(invoice["invoice_id"])
    )
    
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Оплатить", url=invoice["pay_url"])],
        [InlineKeyboardButton(text="🔄 Проверить оплату", callback_data=f"check_pay_{invoice['invoice_id']}")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"pay_order_{plan_id}")]
    ])
    
    if isinstance(callback.message, Message):
        await safe_edit(
            callback.message,
            f"🔗 <b>Счет CryptoBot создан!</b>\n\nТариф: {plan['label']}\nСумма: {amount_usd:.2f} USD\n\nНажмите кнопку ниже для оплаты:",
            reply_markup=keyboard
        )
    await callback.answer()

@router.callback_query(F.data.startswith("pay_stars_"))
async def process_pay_stars(callback: CallbackQuery, db: AsyncSession):
    if not callback.data or not callback.message: return
    plan_id = callback.data.split("_")[2]
    user = await _get_user_by_tg(db, callback.from_user.id)
    plan = settings.PLANS.get(plan_id)
    if not user or not plan: return

    stars_amount = int(plan["price"])
    
    if isinstance(callback.message, Message):
        await callback.message.answer_invoice(
            title=f"VPN: {plan['label']}",
            description=f"Подписка на {plan_id} дней",
            payload=f"stars_{user.id}_{plan_id}",
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice(label="Оплата", amount=stars_amount)]
        )
    await callback.answer()

@router.callback_query(F.data.startswith("pay_sbp_"))
async def process_pay_sbp(callback: CallbackQuery, db: AsyncSession):
    if not callback.data or not callback.message: return
    plan_id = callback.data.split("_")[2]
    user = await _get_user_by_tg(db, callback.from_user.id)
    plan = settings.PLANS.get(plan_id)
    if not user or not plan: return

    amount = plan["price"]
    payment_service = PaymentService(db)
    
    # Create payment record
    payment = await payment_service.create_payment(
        user_id=user.id,
        tariff_id=plan_id,
        provider="sbp",
        amount=amount
    )
    
    # Generate FreeKassa URL
    pay_url = freekassa_service.generate_payment_url(
        amount=amount,
        order_id=str(payment.id)
    )
    
    # Update payment with external_id
    payment.external_id = str(payment.id)
    await db.commit()

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Оплатить через СБП", url=pay_url)],
        [InlineKeyboardButton(text="Проверить оплату", callback_data=f"check_pay_{payment.id}")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"pay_order_{plan_id}")]
    ])
    
    text = (
        f"🚀 <b>Оплата через СБП (FreeKassa)</b>\n\n"
        f"Тариф: {plan['label']}\n"
        f"К оплате: <b>{amount} RUB</b>\n\n"
        f"Нажмите кнопку ниже, чтобы перейти к оплате. "
        f"После оплаты нажмите «Проверить оплату»."
    )
    if isinstance(callback.message, Message):
        await safe_edit(callback.message, text, reply_markup=keyboard)
    await callback.answer()

@router.callback_query(F.data.startswith("pay_ton_"))
async def process_pay_ton(callback: CallbackQuery, db: AsyncSession):
    if not callback.data or not callback.message: return
    plan_id = callback.data.split("_")[2]
    user = await _get_user_by_tg(db, callback.from_user.id)
    plan = settings.PLANS.get(plan_id)
    if not user or not plan: return

    amount = plan["price"]
    payment_service = PaymentService(db)
    
    # Create payment record
    payment = await payment_service.create_payment(
        user_id=user.id,
        tariff_id=plan_id,
        provider="ton",
        amount=amount
    )
    
    # Generate TON payment info
    ton_info = await ton_service.create_invoice(amount, str(payment.id))
    pay_url = ton_info["pay_url"]
    ton_amount = ton_info.get("ton_amount", "...")
    
    # Update payment with external_id
    payment.external_id = str(payment.id)
    await db.commit()

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Открыть TON Кошелек", url=pay_url)],
        [InlineKeyboardButton(text="Проверить оплату", callback_data=f"check_pay_{payment.id}")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"pay_order_{plan_id}")]
    ])
    
    text = (
        f"💎 <b>Оплата через TON Connect</b>\n\n"
        f"Тариф: {plan['label']}\n"
        f"К оплате: <b>{ton_amount} TON</b>\n\n"
        f"Адрес для перевода: <code>{ton_service.wallet_address}</code>\n"
        f"Комментарий (ОБЯЗАТЕЛЬНО): <code>{payment.id}</code>\n\n"
        f"Нажмите кнопку ниже или переведите вручную с указанием комментария."
    )
    if isinstance(callback.message, Message):
        await safe_edit(callback.message, text, reply_markup=keyboard)
    await callback.answer()

@router.callback_query(F.data.startswith("pay_cryptomus_"))
async def process_pay_cryptomus(callback: CallbackQuery, db: AsyncSession):
    if not callback.data or not callback.message: return
    plan_id = callback.data.split("_")[2]
    user = await _get_user_by_tg(db, callback.from_user.id)
    plan = settings.PLANS.get(plan_id)
    if not user or not plan: return

    payment_service = PaymentService(db)
    order_id = f"mus_{user.id}_{int(datetime.now().timestamp())}"
    
    invoice = await cryptomus_service.create_invoice(
        amount=float(plan["price"]),
        order_id=order_id
    )
    
    if not invoice:
        await callback.answer("❌ Ошибка CryptoMus. Попробуйте позже.", show_alert=True)
        return

    await payment_service.create_payment(
        user_id=user.id,
        tariff_id=plan_id,
        provider="cryptomus",
        amount=plan["price"],
        external_id=invoice["uuid"] # Cryptomus transaction UUID
    )
    
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Оплатить", url=invoice["url"])],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"pay_order_{plan_id}")]
    ])
    
    if isinstance(callback.message, Message):
        await safe_edit(
            callback.message,
            f"🔗 <b>Счет CryptoMus создан!</b>\n\nТариф: {plan['label']}\nСумма: {plan['price']} RUB\n\nНажмите кнопку ниже для оплаты:",
            reply_markup=keyboard
        )
    await callback.answer()

@router.callback_query(F.data.startswith("check_pay_"))
async def process_check_pay(callback: CallbackQuery, db: AsyncSession):
    if not callback.data or not callback.message: return
    payment_id = int(callback.data.split("_")[2])
    
    # Get payment from DB
    stmt = select(Payment).where(Payment.id == payment_id)
    res = await db.execute(stmt)
    payment = res.scalar_one_or_none()
    
    if not payment:
        await callback.answer("⚠️ Платеж не найден.", show_alert=True)
        return
        
    if payment.status == PaymentStatus.SUCCESS:
         from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
         if isinstance(callback.message, Message):
             await safe_edit(
                 callback.message,
                 "✅ <b>Оплата получена!</b>\n\nВаша подписка активирована. Перейдите в профиль, чтобы получить ключ.",
                 reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                     [InlineKeyboardButton(text="👤 Профиль", callback_data="profile_main")],
                     [InlineKeyboardButton(text="🏠 Меню", callback_data="main_menu")]
                 ])
             )
    else:
        # If TON, we could potentially check the blockchain here
        if payment.provider == "ton":
            is_paid = await ton_service.check_transaction(str(payment.id))
            if is_paid:
                payment_service = PaymentService(db)
                await payment_service.process_success(str(payment.id))
                from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
                if isinstance(callback.message, Message):
                    await safe_edit(
                        callback.message,
                        "✅ <b>Оплата через TON получена!</b>\n\nВаша подписка активирована. Перейдите в профиль, чтобы получить ключ.",
                        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                            [InlineKeyboardButton(text="👤 Профиль", callback_data="profile_main")],
                            [InlineKeyboardButton(text="🏠 Меню", callback_data="main_menu")]
                        ])
                    )
                return
            else:
                await callback.answer("⏳ Транзакция еще не найдена в блокчейне. Обычно это занимает 1-3 минуты.", show_alert=True)
        else:
            await callback.answer("⏳ Оплата еще не поступила. Попробуйте через минуту.", show_alert=True)

@router.pre_checkout_query()
async def process_pre_checkout(pre_checkout_query: PreCheckoutQuery):
    await pre_checkout_query.answer(ok=True)

@router.message(F.successful_payment)
async def process_successful_payment_handler(message: Message, db: AsyncSession):
    if not message.successful_payment: return
    payload = message.successful_payment.invoice_payload
    if payload.startswith("stars_"):
        parts = payload.split("_")
        user_id = int(parts[1])
        plan_id = parts[2]
        external_id = message.successful_payment.telegram_payment_charge_id
        
        payment_service = PaymentService(db)
        await payment_service.create_payment(
            user_id=user_id,
            tariff_id=plan_id,
            provider="stars",
            amount=message.successful_payment.total_amount,
            currency="XTR",
            external_id=external_id
        )
        await payment_service.process_success(external_id)
        await message.answer("✅ Оплата Stars прошла успешно! Подписка активирована.")


