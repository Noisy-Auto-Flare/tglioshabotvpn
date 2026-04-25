import asyncio
import logging
import uuid as uuid_lib
from datetime import datetime, timedelta
from time import perf_counter
from typing import Optional, Tuple

from aiogram import Bot
from db.session import AsyncSessionLocal
from backend.models.models import User, Subscription, VPNKey, SubscriptionStatus, Payment, PaymentStatus
from backend.services.vpn import vpn_service
from backend.services.payment_service import PaymentService
from backend.services.payments.cryptobot import cryptobot_service
from backend.core.config import settings
from sqlalchemy import select

logger = logging.getLogger(__name__)
PLAN_TRAFFIC_GB = {30: 30, 90: 90, 180: 180, 360: 360}

def generate_mock_config(user_id: int, uuid: str) -> str:
    """Generates a mock VLESS config as a fallback."""
    # This is a template for VLESS, adjust as needed for your server
    # vless://UUID@your-server:443?type=tcp&security=tls&sni=your-sni&fp=chrome&path=%2F&encryption=none#user_ID
    return f"vless://{uuid}@your-vpn-server.com:443?type=tcp&security=tls&sni=google.com&fp=chrome&path=%2F&encryption=none#user_{user_id}"

def parse_payment_payload(payload: str) -> Optional[Tuple[int, int, Optional[int]]]:
    """
    Supports old and new payload formats:
    - old: user_id:plan_days
    - new: user_id:plan_days:traffic_gb
    """
    parts = payload.split(":")
    if len(parts) < 2:
        return None
    try:
        user_id = int(parts[0])
        plan_days = int(parts[1])
        traffic_gb = int(parts[2]) if len(parts) > 2 else None
        return user_id, plan_days, traffic_gb
    except (TypeError, ValueError):
        return None

async def _notify_admins(text: str) -> None:
    if not settings.ADMIN_IDS:
        return
    try:
        async with Bot(token=settings.BOT_TOKEN) as bot:
            for admin_id in settings.ADMIN_IDS:
                try:
                    await bot.send_message(admin_id, text)
                except Exception as send_err:
                    logger.error("Failed to notify admin %s: %s", admin_id, send_err)
    except Exception as e:
        logger.error("Failed to initialize bot for admin notification: %s", e)

async def _send_subscription_message(telegram_id: int, link: str, plan_days: int, traffic_gb: int) -> None:
    text = (
        "✅ Оплата подтверждена! Подписка активирована.\n\n"
        f"🔗 Ссылка для подключения:\n{link}\n\n"
        f"📦 Лимит трафика: {traffic_gb} GB\n"
        f"📅 Срок действия: {plan_days} дней\n\n"
        "Инструкция: откройте ссылку в VPN-клиенте и импортируйте конфигурацию."
    )
    try:
        async with Bot(token=settings.BOT_TOKEN) as bot:
            await bot.send_message(telegram_id, text, disable_web_page_preview=True)
    except Exception as e:
        logger.error("Failed to send subscription link to user %s: %s", telegram_id, e)

async def process_successful_payment(
    session,
    user_id: int,
    plan_days: int,
    amount: float,
    external_id: str,
    traffic_gb: Optional[int] = None,
    provider: str = "cryptobot",
):
    """Core logic for processing a successful payment, used by both webhook and polling."""
    # Idempotency check
    stmt = select(Payment).where(Payment.external_id == external_id)
    result = await session.execute(stmt)
    if result.scalar_one_or_none():
        return False

    # 1. Record payment
    payment = Payment(
        user_id=user_id,
        amount=amount,
        currency="RUB",
        provider=provider,
        status=PaymentStatus.SUCCESS,
        external_id=external_id,
        payload=str(plan_days)
    )
    session.add(payment)
    
    # 2. Update/Create subscription
    now = datetime.now()
    end_date = now + timedelta(days=plan_days)
    
    effective_traffic_gb = traffic_gb if traffic_gb is not None else PLAN_TRAFFIC_GB.get(plan_days, 30)
    sub = Subscription(
        user_id=user_id,
        plan=str(plan_days),
        traffic_limit_gb=effective_traffic_gb,
        start_date=now,
        end_date=end_date,
        status=SubscriptionStatus.ACTIVE
    )
    session.add(sub)
    await session.flush() # Get subscription ID
    
    # 3. Provision VPN (Always create record)
    # Get user telegram_id for RemnaWave
    user_stmt = select(User).where(User.id == user_id)
    user_res = await session.execute(user_stmt)
    user = user_res.scalar_one_or_none()
    
    if not user:
        logger.error(f"User {user_id} not found during payment processing")
        return False

    # 3.1 Delete old active keys for this user to avoid "orphaned" users in RemnaWave
    try:
        old_keys_stmt = select(VPNKey).where(VPNKey.user_id == user_id, VPNKey.is_active == True)
        old_keys_res = await session.execute(old_keys_stmt)
        old_keys = old_keys_res.scalars().all()
        for old_key in old_keys:
            if old_key.uuid:
                logger.info(f"Deleting old RemnaWave user before new provisioning: {old_key.uuid}")
                await asyncio.to_thread(vpn_service.delete_user, old_key.uuid)
                old_key.is_active = False
                old_key.error_message = "Replaced by new subscription"
    except Exception as e:
        logger.error(f"Error cleaning up old keys for user {user_id}: {e}")

    started_at = perf_counter()
    vpn_data = await asyncio.to_thread(
        vpn_service.create_user_and_get_link,
        user.telegram_id,
        effective_traffic_gb,
        plan_days
    )
    duration_ms = int((perf_counter() - started_at) * 1000)
    logger.info(
        "RemnaWave create_user_and_get_link finished for user=%s in %sms success=%s",
        user.telegram_id,
        duration_ms,
        bool(vpn_data)
    )
    
    config = None
    is_active = False
    uuid = None
    error_message = None

    if vpn_data:
        config = vpn_data["link"]
        uuid = vpn_data["uuid"]
        is_active = True
    else:
        error_message = "RemnaWave link creation failed"
        logger.error("VPN provisioning failed for user %s: %s", user_id, error_message)
        await _notify_admins(
            f"⚠️ Ошибка создания VPN-подписки для пользователя {user.telegram_id} (user_id={user.id}). "
            f"Платеж {external_id}. Проверьте REMNAWAVE_COOKIE/API."
        )

    # Fallback: if no config was generated by API, create a mock one but keep is_active=False
    if not config:
        fallback_uuid = str(uuid_lib.uuid4())
        uuid = uuid or fallback_uuid
        config = generate_mock_config(user.telegram_id, uuid)
        # Note: is_active remains False, but user will see SOMETHING (with a warning in profile)
        # We will keep trying to fix this in the background task

    new_vpn = VPNKey(
        user_id=user_id,
        subscription_id=sub.id,
        uuid=uuid,
        config=config,
        expire_at=end_date,
        is_active=is_active,
        error_message=error_message
    )
    session.add(new_vpn)
    
    await session.commit()
    logger.info(f"Successfully processed payment {external_id} for user {user_id}. VPN Active: {is_active}")

    if is_active:
        await _send_subscription_message(user.telegram_id, config, plan_days, effective_traffic_gb)
    else:
        try:
            async with Bot(token=settings.BOT_TOKEN) as bot:
                await bot.send_message(
                    user.telegram_id,
                    "❌ Оплата получена, но создать VPN-ссылку не удалось. Администратор уведомлен, скоро исправим."
                )
        except Exception as send_err:
            logger.error("Failed to send failure message to user %s: %s", user.telegram_id, send_err)

    return True

async def check_expirations():
    """Background task to check for expired subscriptions."""
    while True:
        try:
            async with AsyncSessionLocal() as session:
                now = datetime.now()
                stmt = select(Subscription).where(
                    Subscription.end_date < now,
                    Subscription.status == SubscriptionStatus.ACTIVE
                )
                result = await session.execute(stmt)
                expired_subs = result.scalars().all()

                for sub in expired_subs:
                    logger.info(f"Subscription {sub.id} expired for user {sub.user_id}")
                    sub.status = SubscriptionStatus.EXPIRED
                    
                    vpn_stmt = select(VPNKey).where(VPNKey.user_id == sub.user_id).order_by(VPNKey.expire_at.desc()).limit(1)
                    vpn_res = await session.execute(vpn_stmt)
                    vpn_key = vpn_res.scalar_one_or_none()
                    
                    if vpn_key and vpn_key.uuid:
                        await vpn_service.disable_vpn_user(vpn_key.uuid)
                
                await session.commit()
        except Exception as e:
            logger.error(f"Error in expiration checker: {e}")
        await asyncio.sleep(300)

async def payment_polling():
    """Poll for pending payments from providers that don't use webhooks or as a fallback."""
    while True:
        try:
            async with AsyncSessionLocal() as db:
                payment_service = PaymentService(db)
                
                # 1. Poll CryptoBot
                stmt = select(Payment).where(
                    Payment.provider == "cryptobot",
                    Payment.status == PaymentStatus.PENDING
                )
                result = await db.execute(stmt)
                pending_payments = result.scalars().all()
                
                if pending_payments:
                    invoice_ids = ",".join([p.external_id for p in pending_payments if p.external_id])
                    invoices = await cryptobot_service.get_invoices(invoice_ids)
                    
                    if invoices:
                        for invoice in invoices:
                            if invoice["status"] == "paid":
                                await payment_service.process_success(str(invoice["invoice_id"]))
                
                # 2. General check for other providers if needed
                # ...
                
        except Exception as e:
            logger.error(f"Error in payment polling: {e}")
            
        await asyncio.sleep(60) # Poll every 60 seconds

async def vpn_retry_task():
    """Background task to retry failed VPN key creations and provision missing keys for active subs."""
    while True:
        try:
            async with AsyncSessionLocal() as session:
                now = datetime.now()
                
                # 1. Retry failed keys (is_active=False)
                stmt = select(VPNKey).where(
                    VPNKey.is_active == False,
                    VPNKey.expire_at > now
                )
                result = await session.execute(stmt)
                failed_keys = result.scalars().all()
                
                for vpn_key in failed_keys:
                    # Get user telegram_id
                    user_stmt = select(User).where(User.id == vpn_key.user_id)
                    user_res = await session.execute(user_stmt)
                    user = user_res.scalar_one_or_none()
                    if not user: continue

                    logger.info(f"Retrying VPN provisioning for user {user.id}")
                    remaining_days = max(1, (vpn_key.expire_at - now).days)
                    traffic_gb = 30
                    if vpn_key.subscription_id:
                        sub_stmt = select(Subscription).where(Subscription.id == vpn_key.subscription_id)
                        sub_res = await session.execute(sub_stmt)
                        sub = sub_res.scalar_one_or_none()
                        if sub and sub.traffic_limit_gb:
                            traffic_gb = sub.traffic_limit_gb

                    link = await asyncio.to_thread(
                        vpn_service.create_user_and_get_link,
                        user.telegram_id,
                        traffic_gb,
                        remaining_days
                    )
                    if link:
                        vpn_key.uuid = link.rstrip("/").split("/")[-1]
                        vpn_key.config = link
                        vpn_key.is_active = True
                        vpn_key.error_message = None
                        await session.commit()
                        logger.info(f"Successfully fixed VPN key for user {user.id}")
                
                # 2. Find active subscriptions WITHOUT any VPNKey record
                sub_stmt = select(Subscription).where(
                    Subscription.status == SubscriptionStatus.ACTIVE,
                    Subscription.end_date > now
                )
                sub_res = await session.execute(sub_stmt)
                active_subs = sub_res.scalars().all()
                
                for sub in active_subs:
                    # Check if vpn_key exists for this subscription
                    key_stmt = select(VPNKey).where(VPNKey.subscription_id == sub.id)
                    key_res = await session.execute(key_stmt)
                    if not key_res.scalar_one_or_none():
                        # Missing VPNKey record! Let's create it.
                        user_stmt = select(User).where(User.id == sub.user_id)
                        user_res = await session.execute(user_stmt)
                        user = user_res.scalar_one_or_none()
                        if not user: continue
                        
                        logger.info(f"Provisioning missing VPNKey for active subscription {sub.id} (user {user.id})")

                        remaining_days = max(1, (sub.end_date - now).days)
                        traffic_gb = sub.traffic_limit_gb or 30
                        vpn_data = await asyncio.to_thread(
                            vpn_service.create_user_and_get_link,
                            user.telegram_id,
                            traffic_gb,
                            remaining_days
                        )

                        config = generate_mock_config(user.telegram_id, "pending")
                        is_active = False
                        uuid = None
                        error_message = "Initial background provision"

                        if vpn_data:
                            config = vpn_data["link"]
                            uuid = vpn_data["uuid"]
                            is_active = True
                            error_message = None

                        new_vpn = VPNKey(
                            user_id=user.id,
                            subscription_id=sub.id,
                            uuid=uuid,
                            config=config,
                            expire_at=sub.end_date,
                            is_active=is_active,
                            error_message=error_message
                        )
                        session.add(new_vpn)
                        await session.commit()
                        logger.info(f"Created missing VPNKey for sub {sub.id}. Active: {is_active}")

        except Exception as e:
            logger.error(f"Error in VPN retry task: {e}")
            
        await asyncio.sleep(600) # Check every 10 minutes
