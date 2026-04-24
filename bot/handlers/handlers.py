import asyncio
import logging
import time
import uuid
from datetime import datetime, timedelta
from typing import Optional, Union
from urllib.parse import quote_plus

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, LabeledPrice, Message, PreCheckoutQuery
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.models import (
    Payment,
    PaymentStatus,
    Subscription,
    SubscriptionStatus,
    User,
    VPNKey,
)
from backend.services.payments import cryptobot_service
from backend.services.tasks import (
    generate_mock_config,
    parse_payment_payload,
    process_successful_payment,
)
from backend.services.vpn import vpn_service
from bot.keyboards.keyboards import (
    get_main_menu,
    get_payment_keyboard,
    get_payment_methods,
    get_profile_keyboard,
    get_subscription_plans,
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
    if sub:
        remaining = sub.end_date - now
        status_text = (
            f"✅ Активна до: {sub.end_date.strftime('%d.%m.%Y %H:%M')}\n"
            f"Осталось дней: {max(0, remaining.days)}"
        )

    vpn_info = ""
    if vpn_key:
        if vpn_key.is_active:
            vpn_info = f"\n🔑 <b>Ваш VPN ключ:</b>\n<code>{vpn_key.config}</code>"
        else:
            error_info = (
                f"\n\n<i>Причина: {vpn_key.error_message}</i>" if vpn_key.error_message else ""
            )
            vpn_info = (
                "\n🔑 <b>VPN ключ временно недоступен</b>\n"
                "<code>⚠️ Ключ в процессе создания или произошла ошибка.</code>"
                f"{error_info}\n\nНажмите «Обновить ключ» через минуту."
            )
    elif sub:
        vpn_info = "\n🔑 <b>VPN ключ еще не создан</b>\nНажмите «Получить ключ»."

    await render_screen(
        event,
        db,
        "profile",
        keyboard=get_profile_keyboard(bool(sub), bool(vpn_key)),
        telegram_id=user.telegram_id,
        balance=user.balance,
        status_text=status_text,
        vpn_info=vpn_info,
    )


def _build_tonkeeper_url(wallet: str, amount_usd: float, ton_price_usd: float, comment: str) -> str:
    ton_amount = max(amount_usd / max(ton_price_usd, 0.1), 0.001)
    amount_nano = int(ton_amount * 1_000_000_000)
    return (
        f"https://app.tonkeeper.com/transfer/{wallet}"
        f"?amount={amount_nano}&text={quote_plus(comment)}"
    )


@router.message(CommandStart())
async def cmd_start(message: Message, db: AsyncSession):
    if not message.from_user:
        return
    try:
        user = await _get_user_by_tg(db, message.from_user.id)
        if not user:
            referral_code = str(uuid.uuid4())[:8]
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
                referred_by=referred_by,
            )
            db.add(user)
            await db.commit()

        await render_screen(message, db, "main_menu", keyboard=get_main_menu())
    except Exception as e:
        logger.error("Error in cmd_start: %s", e)
        await message.answer("Произошла ошибка. Попробуйте позже.")


@router.callback_query(F.data == "menu")
async def open_menu(callback: CallbackQuery, db: AsyncSession):
    await render_screen(callback, db, "main_menu", keyboard=get_main_menu())
    await callback.answer()


@router.callback_query((F.data == "connect") | (F.data == "buy_subscription"))
async def open_connect(callback: CallbackQuery, db: AsyncSession):
    await render_screen(callback, db, "connect_menu", keyboard=get_subscription_plans())
    await callback.answer()


@router.callback_query(F.data == "profile")
async def open_profile(callback: CallbackQuery, db: AsyncSession):
    user = await _get_user_by_tg(db, callback.from_user.id)
    if not user:
        await callback.answer("Пожалуйста, используйте /start", show_alert=True)
        return
    await _show_profile(callback, db, user)
    await callback.answer()


@router.callback_query(F.data == "ref")
async def open_ref(callback: CallbackQuery, db: AsyncSession):
    user = await _get_user_by_tg(db, callback.from_user.id)
    if not user:
        await callback.answer("Пожалуйста, используйте /start", show_alert=True)
        return
    count_stmt = select(User).where(User.referred_by == user.id)
    count_result = await db.execute(count_stmt)
    count = len(count_result.scalars().all())
    if callback.bot:
        bot_info = await callback.bot.get_me()
        ref_link = f"https://t.me/{bot_info.username}?start={user.referral_code}"
    else:
        ref_link = user.referral_code
    await render_screen(callback, db, "referral", keyboard=get_main_menu(), count=count, ref_link=ref_link)
    await callback.answer()


@router.callback_query(F.data == "info")
async def open_info(callback: CallbackQuery, db: AsyncSession):
    await render_screen(callback, db, "info", keyboard=get_main_menu())
    await callback.answer()


@router.callback_query(F.data == "support")
async def open_support(callback: CallbackQuery, db: AsyncSession):
    await render_screen(callback, db, "support", keyboard=get_main_menu())
    await callback.answer()


@router.callback_query(F.data.startswith("plan_"))
async def process_plan_selection(callback: CallbackQuery, db: AsyncSession):
    if not callback.data:
        return
    plan_id = callback.data.split("_")[1]
    try:
        user = await _get_user_by_tg(db, callback.from_user.id)
        if not user:
            await callback.answer("Пожалуйста, используйте /start", show_alert=True)
            return

        if plan_id == "trial":
            stmt = select(Subscription).where(Subscription.user_id == user.id, Subscription.plan == "trial")
            res = await db.execute(stmt)
            if res.scalar_one_or_none():
                await callback.answer("Пробный период уже использован", show_alert=True)
                return

            now = datetime.now()
            end_date = now + timedelta(days=3)
            sub = Subscription(
                user_id=user.id,
                plan="trial",
                traffic_limit_gb=10,
                start_date=now,
                end_date=end_date,
                status=SubscriptionStatus.ACTIVE,
            )
            db.add(sub)
            await db.flush()

            subscription_link = await asyncio.to_thread(vpn_service.create_user_and_get_link, user.telegram_id, 10, 3)
            key_uuid = None
            is_active = False
            error_message = None
            if subscription_link:
                key_uuid = subscription_link.rstrip("/").split("/")[-1]
                config = subscription_link
                is_active = True
            else:
                key_uuid = str(uuid.uuid4())
                config = generate_mock_config(user.telegram_id, key_uuid)
                error_message = "RemnaWave link creation failed"

            db.add(
                VPNKey(
                    user_id=user.id,
                    subscription_id=sub.id,
                    uuid=key_uuid,
                    config=config,
                    expire_at=end_date,
                    is_active=is_active,
                    error_message=error_message,
                )
            )
            await db.commit()
            await _show_profile(callback, db, user)
            await callback.answer("Пробный период активирован")
            return

        from backend.core.config import settings
        plan = settings.PLANS.get(plan_id)
        if not plan:
            await callback.answer("Тариф не найден", show_alert=True)
            return
        if not settings.TON_WALLET_ADDRESS:
            ton_url = "https://t.me/tonkeeper"
        else:
            ton_url = _build_tonkeeper_url(
                settings.TON_WALLET_ADDRESS,
                float(plan["price"]),
                float(settings.TON_PRICE_USD),
                f"{user.id}:{plan_id}:{plan['gb']}",
            )
        await render_screen(
            callback,
            db,
            "payment",
            keyboard=get_payment_methods(plan_id, ton_url),
            plan_label=plan["label"],
        )
        await callback.answer()
    except Exception as e:
        logger.error("Error in process_plan_selection: %s", e)
        await callback.answer("Ошибка при выборе плана", show_alert=True)


@router.callback_query(F.data.startswith("pay_crypto_"))
async def process_pay_crypto(callback: CallbackQuery, db: AsyncSession):
    if not callback.data:
        return
    plan_id = callback.data.split("_")[2]
    try:
        user = await _get_user_by_tg(db, callback.from_user.id)
        if not user:
            await callback.answer("Пожалуйста, используйте /start", show_alert=True)
            return

        from backend.core.config import settings
        plan = settings.PLANS.get(plan_id)
        if not plan:
            await callback.answer("Тариф не найден", show_alert=True)
            return
        price = float(plan["price"])
        traffic_gb = int(plan["gb"])

        invoice = await cryptobot_service.create_invoice(
            amount=price,
            payload=f"{user.id}:{plan_id}:{traffic_gb}",
        )
        if not invoice:
            await callback.answer("Не удалось создать счет CryptoBot", show_alert=True)
            return

        db.add(
            Payment(
                user_id=user.id,
                amount=price,
                provider="cryptobot",
                status=PaymentStatus.PENDING,
                external_id=str(invoice["invoice_id"]),
            )
        )
        await db.commit()
        await render_screen(
            callback,
            db,
            "payment",
            keyboard=get_payment_keyboard(invoice["pay_url"], plan_id),
            plan_label=plan["label"],
        )
        await callback.answer()
    except Exception as e:
        logger.error("Error in process_pay_crypto: %s", e)
        await callback.answer("Ошибка при создании счета", show_alert=True)


@router.callback_query(F.data.startswith("pay_stars_"))
async def process_pay_stars(callback: CallbackQuery, db: AsyncSession):
    if not callback.data:
        return
    plan_id = callback.data.split("_")[2]
    try:
        user = await _get_user_by_tg(db, callback.from_user.id)
        if not user:
            await callback.answer("Пожалуйста, используйте /start", show_alert=True)
            return
        from backend.core.config import settings
        plan = settings.PLANS.get(plan_id)
        if not plan:
            await callback.answer("Тариф не найден", show_alert=True)
            return
        stars_amount = int(float(plan["price"]) * settings.STARS_CONVERSION_RATE)
        traffic_gb = int(plan["gb"])
        if isinstance(callback.message, Message):
            await callback.message.answer_invoice(
                title=f"VPN подписка {plan_id} дней",
                description=f"{plan_id} дней / {traffic_gb} GB",
                payload=f"{user.id}:{plan_id}:{traffic_gb}",
                provider_token="",
                currency="XTR",
                prices=[LabeledPrice(label="VPN", amount=stars_amount)],
            )
        await callback.answer("Инвойс Stars отправлен")
    except Exception as e:
        logger.error("Error in process_pay_stars: %s", e)
        await callback.answer("Ошибка при создании счета Stars", show_alert=True)


@router.callback_query(F.data.startswith("check_ton_"))
async def process_check_ton(callback: CallbackQuery, db: AsyncSession):
    if not callback.data:
        return
    plan_id = callback.data.split("_")[2]
    user = await _get_user_by_tg(db, callback.from_user.id)
    if not user:
        await callback.answer("Пожалуйста, используйте /start", show_alert=True)
        return
    ext_id = f"ton:{user.id}:{plan_id}:{int(time.time())}"
    db.add(
        Payment(
            user_id=user.id,
            amount=0.0,
            provider="tonconnect",
            status=PaymentStatus.PENDING,
            external_id=ext_id,
        )
    )
    await db.commit()
    await callback.answer("Заявка TON создана. Напишите в поддержку для подтверждения.", show_alert=True)


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
    if not parsed:
        return
    user_id, plan_days, traffic_gb = parsed
    from backend.core.config import settings
    amount_usd = amount_stars / settings.STARS_CONVERSION_RATE
    await process_successful_payment(
        db,
        user_id,
        plan_days,
        amount_usd,
        external_id,
        traffic_gb=traffic_gb,
        provider="stars",
    )
    await message.answer("✅ Оплата Stars прошла успешно, подписка активирована.")


@router.callback_query(F.data == "check_payment")
async def process_check_payment(callback: CallbackQuery):
    await callback.answer("Проверка идет автоматически. Обычно до 1-2 минут.", show_alert=True)


@router.callback_query(F.data == "get_vpn_key")
async def process_get_vpn_key(callback: CallbackQuery, db: AsyncSession):
    try:
        user = await _get_user_by_tg(db, callback.from_user.id)
        if not user:
            await callback.answer("Пожалуйста, используйте /start", show_alert=True)
            return

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
        if not sub:
            await callback.answer("Нет активной подписки", show_alert=True)
            return

        await callback.answer("Генерирую ключ...")
        remaining_days = max(1, (sub.end_date - now).days)
        traffic_gb = sub.traffic_limit_gb or 30
        subscription_link = await asyncio.to_thread(
            vpn_service.create_user_and_get_link,
            user.telegram_id,
            traffic_gb,
            remaining_days,
        )
        key_uuid = None
        is_active = False
        error_message = None
        if subscription_link:
            key_uuid = subscription_link.rstrip("/").split("/")[-1]
            config = subscription_link
            is_active = True
        else:
            key_uuid = str(uuid.uuid4())
            config = generate_mock_config(user.telegram_id, key_uuid)
            error_message = "RemnaWave link creation failed"

        vpn_stmt = select(VPNKey).where(VPNKey.user_id == user.id).order_by(VPNKey.expire_at.desc()).limit(1)
        vpn_res = await db.execute(vpn_stmt)
        existing_vpn = vpn_res.scalar_one_or_none()
        if existing_vpn:
            existing_vpn.uuid = key_uuid
            existing_vpn.config = config
            existing_vpn.is_active = is_active
            existing_vpn.error_message = error_message
            existing_vpn.expire_at = sub.end_date
            existing_vpn.subscription_id = sub.id
        else:
            db.add(
                VPNKey(
                    user_id=user.id,
                    subscription_id=sub.id,
                    uuid=key_uuid,
                    config=config,
                    expire_at=sub.end_date,
                    is_active=is_active,
                    error_message=error_message,
                )
            )
        await db.commit()
        await _show_profile(callback, db, user)
    except Exception as e:
        logger.error("Error in process_get_vpn_key: %s", e)
        await callback.answer("Ошибка при получении ключа", show_alert=True)
