import uuid
import logging
import asyncio
from datetime import datetime, timedelta

from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery, PreCheckoutQuery, LabeledPrice
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.models.models import User, Subscription, VPNKey, SubscriptionStatus, Payment, PaymentStatus
from bot.keyboards.keyboards import (
    get_main_menu, 
    get_subscription_plans, 
    get_payment_keyboard, 
    get_profile_keyboard,
    get_payment_methods
)
from backend.services.payments import cryptobot_service
from backend.services.vpn import vpn_service
from bot.services.renderer import render_screen
from backend.services.tasks import parse_payment_payload, process_successful_payment

logger = logging.getLogger(__name__)
router = Router()

@router.message(CommandStart())
async def cmd_start(message: Message, db: AsyncSession):
    """Handle /start command. Register new users and handle referrals."""
    if not message.from_user:
        return

    try:
        stmt = select(User).where(User.telegram_id == message.from_user.id)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()
        
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
            
            try:
                user = User(
                    telegram_id=message.from_user.id,
                    referral_code=referral_code,
                    referred_by=referred_by
                )
                db.add(user)
                await db.commit()
                logger.info(f"New user registered: {message.from_user.id}")
            except Exception as e:
                # Likely a race condition where user was created by another concurrent request
                await db.rollback()
                stmt = select(User).where(User.telegram_id == message.from_user.id)
                result = await db.execute(stmt)
                user = result.scalar_one_or_none()
                if not user:
                    # If it's still not found, it's a real error
                    logger.error(f"Failed to register user {message.from_user.id}: {e}")
                    raise e 
                logger.info(f"User {message.from_user.id} already exists (handled race condition)")
        
        await render_screen(
            message,
            db,
            "main_menu",
            keyboard=get_main_menu()
        )
    except Exception as e:
        logger.error(f"Error in cmd_start: {e}")
        await message.answer("Произошла ошибка при регистрации. Попробуйте позже.")

@router.message(F.text == "Подключиться")
async def process_connect(message: Message, db: AsyncSession):
    await render_screen(
        message,
        db,
        "plans",
        keyboard=get_subscription_plans()
    )

@router.message(F.text == "Мой профиль")
async def process_profile(message: Message, db: AsyncSession):
    if not message.from_user:
        return
    try:
        stmt = select(User).where(User.telegram_id == message.from_user.id)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            return await message.answer("Пожалуйста, используйте /start для регистрации.")
        
        # Get active subscription
        now = datetime.now()
        sub_stmt = select(Subscription).where(
            Subscription.user_id == user.id,
            Subscription.status == SubscriptionStatus.ACTIVE,
            Subscription.end_date > now
        ).order_by(Subscription.end_date.desc()).limit(1)
        sub_result = await db.execute(sub_stmt)
        sub = sub_result.scalar_one_or_none()
        
        # Get latest active VPN key for this user
        vpn_stmt = select(VPNKey).where(
            VPNKey.user_id == user.id,
            VPNKey.expire_at > now
        ).order_by(VPNKey.expire_at.desc()).limit(1)
        vpn_result = await db.execute(vpn_stmt)
        vpn_key = vpn_result.scalar_one_or_none()
        
        status_text = "❌ Нет активной подписки"
        if sub:
            remaining = sub.end_date - now
            days = remaining.days
            status_text = f"✅ Активна до: {sub.end_date.strftime('%d.%m.%Y %H:%M')}\nОсталось дней: {max(0, days)}"
        
        vpn_info = ""
        if vpn_key:
            if vpn_key.is_active:
                vpn_info = f"\n🔑 <b>Ваш VPN Ключ:</b>\n<code>{vpn_key.config}</code>"
            else:
                error_info = ""
                if vpn_key.error_message:
                    error_info = f"\n\n<i>Причина: {vpn_key.error_message}</i>"
                vpn_info = f"\n🔑 <b>VPN Ключ временно недоступен</b>\n<code>⚠️ Ключ в процессе создания или произошла ошибка.</code>{error_info}\n\nПопробуйте нажать кнопку «Обновить ключ» через минуту."
        elif sub:
            vpn_info = f"\n🔑 <b>VPN Ключ еще не создан</b>\nНажмите кнопку «Получить ключ» ниже для генерации ключа."
        
        await render_screen(
            message,
            db,
            "profile",
            keyboard=get_profile_keyboard(bool(sub), bool(vpn_key)),
            telegram_id=user.telegram_id,
            balance=user.balance,
            status_text=status_text,
            vpn_info=vpn_info
        )
    except Exception as e:
        logger.error(f"Error in process_profile: {e}")
        await message.answer("Ошибка при получении профиля.")

@router.message(F.text == "Реферальная система")
async def process_referral(message: Message, db: AsyncSession):
    if not message.from_user or not message.bot:
        return
    try:
        stmt = select(User).where(User.telegram_id == message.from_user.id)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            return await message.answer("Пожалуйста, используйте /start для регистрации.")
        
        # Count referrals
        count_stmt = select(User).where(User.referred_by == user.id)
        count_result = await db.execute(count_stmt)
        count = len(count_result.scalars().all())
        
        bot_info = await message.bot.get_me()
        ref_link = f"https://t.me/{bot_info.username}?start={user.referral_code}"
        
        await render_screen(
            message,
            db,
            "referral",
            count=count,
            ref_link=ref_link
        )
    except Exception as e:
        logger.error(f"Error in process_referral: {e}")

@router.message(F.text == "Информация")
async def process_info(message: Message, db: AsyncSession):
    await render_screen(message, db, "info")

@router.message(F.text == "Поддержка")
async def process_support(message: Message, db: AsyncSession):
    await render_screen(message, db, "support")

@router.callback_query(F.data.startswith("plan_"))
async def process_plan_selection(callback: CallbackQuery, db: AsyncSession):
    if not callback.data:
        return
    plan_id = callback.data.split("_")[1]
    
    try:
        user_stmt = select(User).where(User.telegram_id == callback.from_user.id)
        user_res = await db.execute(user_stmt)
        user = user_res.scalar_one_or_none()
        
        if not user:
            return await callback.answer("Пожалуйста, используйте /start для регистрации.", show_alert=True)

        if plan_id == "trial":
            # ... (keep trial logic)
            stmt = select(Subscription).where(
                Subscription.user_id == user.id,
                Subscription.plan == "trial"
            )
            res = await db.execute(stmt)
            if res.scalar_one_or_none():
                return await callback.answer("Вы уже использовали пробный период!", show_alert=True)
            
            now = datetime.now()
            end_date = now + timedelta(days=3)
            
            sub = Subscription(
                user_id=user.id,
                plan="trial",
                traffic_limit_gb=10,
                start_date=now,
                end_date=end_date,
                status=SubscriptionStatus.ACTIVE
            )
            db.add(sub)
            await db.flush() # Get sub.id
            
            # Provision VPN via curl_cffi path (more stable for this panel)
            subscription_link = await asyncio.to_thread(
                vpn_service.create_user_and_get_link,
                user.telegram_id,
                10,
                3
            )
            config = None
            is_active = False
            uuid = None
            error_message = None
            if subscription_link:
                config = subscription_link
                is_active = True
                uuid = subscription_link.rstrip("/").split("/")[-1]
            else:
                from backend.services.tasks import generate_mock_config
                import uuid as uuid_lib
                fallback_uuid = str(uuid_lib.uuid4())
                uuid = fallback_uuid
                config = generate_mock_config(user.telegram_id, uuid)
                error_message = "RemnaWave link creation failed"

            new_vpn = VPNKey(
                user_id=user.id,
                subscription_id=sub.id,
                uuid=uuid,
                config=config,
                expire_at=end_date,
                is_active=is_active,
                error_message=error_message
            )
            db.add(new_vpn)
            
            await db.commit()
            
            # Send success message as a new message (to support banner)
            if isinstance(callback.message, Message):
                await callback.message.delete()
                await callback.message.answer(
                    "✅ Пробный период активирован на 3 дня!\n\n"
                    "Ваш ключ создан и доступен в профиле.",
                    reply_markup=get_main_menu()
                )
            return

        # Show payment methods for paid plans
        from backend.core.config import settings
        plan = settings.PLANS.get(plan_id)
        if not plan:
            return await callback.answer("Выбранный тарифный план не найден.", show_alert=True)
            
        if isinstance(callback.message, Message):
            await callback.message.edit_text(
                f"Выберите способ оплаты для тарифа {plan['label']}:",
                reply_markup=get_payment_methods(plan_id)
            )

    except Exception as e:
        logger.error(f"Error in process_plan_selection: {e}")
        await callback.answer("Ошибка при выборе плана.", show_alert=True)

@router.callback_query(F.data.startswith("pay_crypto_"))
async def process_pay_crypto(callback: CallbackQuery, db: AsyncSession):
    if not callback.data:
        return
    plan_id = callback.data.split("_")[2]
    try:
        user_stmt = select(User).where(User.telegram_id == callback.from_user.id)
        user_res = await db.execute(user_stmt)
        user = user_res.scalar_one_or_none()
        
        if not user:
            return await callback.answer("Пожалуйста, используйте /start для регистрации.", show_alert=True)

        from backend.core.config import settings
        plan = settings.PLANS.get(plan_id)
        if not plan:
            return await callback.answer("План не найден.", show_alert=True)
            
        price = plan["price"]
        traffic_gb = plan["gb"]
        
        invoice = await cryptobot_service.create_invoice(
            amount=price,
            payload=f"{user.id}:{plan_id}:{traffic_gb}"
        )
        
        if invoice:
            payment = Payment(
                user_id=user.id,
                amount=float(price),
                provider="cryptobot",
                status=PaymentStatus.PENDING,
                external_id=str(invoice["invoice_id"])
            )
            db.add(payment)
            await db.commit()

            if isinstance(callback.message, Message):
                await callback.message.edit_text(
                    f"Оплатите {price}$ через CryptoBot для активации подписки на {plan_id} дней ({traffic_gb} GB):",
                    reply_markup=get_payment_keyboard(invoice["pay_url"])
                )
        else:
            await callback.answer("Ошибка создания счета CryptoBot. Попробуйте позже.", show_alert=True)
    except Exception as e:
        logger.error(f"Error in process_pay_crypto: {e}")
        await callback.answer("Ошибка при создании счета.", show_alert=True)

@router.callback_query(F.data.startswith("pay_stars_"))
async def process_pay_stars(callback: CallbackQuery, db: AsyncSession):
    if not callback.data:
        return
    plan_id = callback.data.split("_")[2]
    try:
        user_stmt = select(User).where(User.telegram_id == callback.from_user.id)
        user_res = await db.execute(user_stmt)
        user = user_res.scalar_one_or_none()
        
        if not user:
            return await callback.answer("Пожалуйста, используйте /start для регистрации.", show_alert=True)

        from backend.core.config import settings
        plan = settings.PLANS.get(plan_id)
        if not plan:
            return await callback.answer("План не найден.", show_alert=True)

        # Convert USD to Stars
        stars_amount = int(plan["price"] * settings.STARS_CONVERSION_RATE)
        traffic_gb = plan["gb"]
        
        if isinstance(callback.message, Message):
            # Invoices with Stars don't need a provider_token (it's empty)
            await callback.message.answer_invoice(
                title=f"VPN Подписка: {plan_id} дней",
                description=f"Подписка на {plan_id} дней ({traffic_gb} GB трафика)",
                payload=f"{user.id}:{plan_id}:{traffic_gb}",
                currency="XTR",
                prices=[LabeledPrice(label="Звезды", amount=stars_amount)],
                provider_token=""
            )
        await callback.answer()
    except Exception as e:
        logger.error(f"Error in process_pay_stars: {e}")
        await callback.answer("Ошибка при создании счета Stars.", show_alert=True)

@router.pre_checkout_query()
async def process_pre_checkout(pre_checkout_query: PreCheckoutQuery):
    await pre_checkout_query.answer(ok=True)

@router.message(F.successful_payment)
async def process_successful_stars_payment(message: Message, db: AsyncSession):
    if not message.successful_payment:
        return
        
    payload = message.successful_payment.invoice_payload
    external_id = message.successful_payment.telegram_payment_charge_id
    amount_stars = message.successful_payment.total_amount
    
    parsed = parse_payment_payload(payload)
    if parsed:
        user_id, plan_days, traffic_gb = parsed
        # Convert stars back to approximate USD for record
        from backend.core.config import settings
        amount_usd = amount_stars / settings.STARS_CONVERSION_RATE
        
        await process_successful_payment(
            db,
            user_id,
            plan_days,
            amount_usd,
            external_id,
            traffic_gb=traffic_gb,
            provider="stars"
        )
        await message.answer("✅ Оплата звездами прошла успешно! Ваша подписка активирована.")

@router.callback_query(F.data.startswith("pay_ton_"))
async def process_pay_ton(callback: CallbackQuery, db: AsyncSession):
    if not callback.data:
        return
    plan_id = callback.data.split("_")[2]
    try:
        user_stmt = select(User).where(User.telegram_id == callback.from_user.id)
        user_res = await db.execute(user_stmt)
        user = user_res.scalar_one_or_none()
        
        if not user:
            return await callback.answer("Пожалуйста, используйте /start для регистрации.", show_alert=True)

        from backend.core.config import settings
        plan = settings.PLANS.get(plan_id)
        if not plan:
            return await callback.answer("План не найден.", show_alert=True)

        # Manual TON payment instruction flow.
        ton_address = settings.TON_WALLET_ADDRESS or "YOUR_TON_WALLET_HERE"
        comment = f"{user.id}:{plan_id}"
        
        # Deep link for TON transfer: ton://transfer/<address>?amount=<nanotons>&text=<comment>
        # We'll just show the address and comment for now.
        
        text = (
            f"💎 <b>Оплата через TON кошелек</b>\n\n"
            f"Для оплаты тарифа {plan['label']} отправьте эквивалент в TON на адрес:\n"
            f"<code>{ton_address}</code>\n\n"
            f"⚠️ <b>ОБЯЗАТЕЛЬНО</b> укажите этот комментарий к платежу:\n"
            f"<code>{comment}</code>\n\n"
            f"<i>После отправки платежа напишите в поддержку для проверки и активации.</i>"
        )
        
        if isinstance(callback.message, Message):
            await callback.message.edit_text(text)
        await callback.answer()
    except Exception as e:
        logger.error(f"Error in process_pay_ton: {e}")
        await callback.answer("Ошибка при подготовке оплаты TON.", show_alert=True)

@router.callback_query(F.data == "check_payment")
async def process_check_payment(callback: CallbackQuery):
    await callback.answer("Платеж проверяется автоматически. Пожалуйста, подождите несколько минут.", show_alert=True)

@router.callback_query(F.data == "buy_subscription")
async def process_buy_sub_callback(callback: CallbackQuery, db: AsyncSession):
    if isinstance(callback.message, Message):
        await callback.message.delete()
    await render_screen(
        callback,
        db,
        "plans",
        keyboard=get_subscription_plans()
    )

@router.callback_query(F.data == "get_vpn_key")
async def process_get_vpn_key(callback: CallbackQuery, db: AsyncSession):
    try:
        stmt = select(User).where(User.telegram_id == callback.from_user.id)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            return await callback.answer("Пожалуйста, используйте /start для регистрации.", show_alert=True)

        # Check for active sub
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

        await callback.answer("Генерируем ключ... Пожалуйста, подождите.", show_alert=False)
        
        from backend.services.vpn import vpn_service
        from backend.services.tasks import generate_mock_config
        import uuid as uuid_lib
        remaining_days = max(1, (sub.end_date - now).days)
        traffic_gb = sub.traffic_limit_gb or 30
        subscription_link = await asyncio.to_thread(
            vpn_service.create_user_and_get_link,
            user.telegram_id,
            traffic_gb,
            remaining_days
        )
        
        config = None
        is_active = False
        uuid = None
        error_message = None

        if subscription_link:
            config = subscription_link
            is_active = True
            uuid = subscription_link.rstrip("/").split("/")[-1]
        else:
            error_message = "RemnaWave link creation failed"

        if not config:
            fallback_uuid = str(uuid_lib.uuid4())
            uuid = uuid or fallback_uuid
            config = generate_mock_config(user.telegram_id, uuid)

        # Update or create VPNKey
        vpn_stmt = select(VPNKey).where(VPNKey.user_id == user.id).order_by(VPNKey.expire_at.desc()).limit(1)
        vpn_res = await db.execute(vpn_stmt)
        existing_vpn = vpn_res.scalar_one_or_none()
        
        if existing_vpn:
            existing_vpn.uuid = uuid
            existing_vpn.config = config
            existing_vpn.is_active = is_active
            existing_vpn.error_message = error_message
            existing_vpn.expire_at = sub.end_date
            existing_vpn.subscription_id = sub.id
        else:
            new_vpn = VPNKey(
                user_id=user.id,
                subscription_id=sub.id,
                uuid=uuid,
                config=config,
                expire_at=sub.end_date,
                is_active=is_active,
                error_message=error_message
            )
            db.add(new_vpn)
            
        await db.commit()
        
        if is_active:
            if isinstance(callback.message, Message):
                await callback.message.answer("✅ Ключ успешно обновлен! Проверьте ваш профиль.", reply_markup=get_main_menu())
        else:
            if isinstance(callback.message, Message):
                await callback.message.answer(f"⚠️ Не удалось сгенерировать активный ключ: {error_message or 'ошибка панели'}. Мы попробуем создать его автоматически в фоновом режиме.", reply_markup=get_main_menu())
            
    except Exception as e:
        logger.error(f"Error in process_get_vpn_key: {e}")
        await callback.answer("Ошибка при получении ключа.", show_alert=True)
