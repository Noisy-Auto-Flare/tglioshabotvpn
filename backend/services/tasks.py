import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any

from db.session import AsyncSessionLocal
from backend.models.models import User, Subscription, VPNKey, SubscriptionStatus, Payment, PaymentStatus
from backend.services.vpn import vpn_service
from backend.services.payments import cryptobot_service
from sqlalchemy import select

logger = logging.getLogger(__name__)

async def process_successful_payment(session, user_id: int, plan_days: int, amount: float, external_id: str):
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
        provider="cryptobot",
        status=PaymentStatus.COMPLETED,
        external_id=external_id
    )
    session.add(payment)
    
    # 2. Update/Create subscription
    now = datetime.now()
    end_date = now + timedelta(days=plan_days)
    
    sub = Subscription(
        user_id=user_id,
        plan=str(plan_days),
        start_date=now,
        end_date=end_date,
        status=SubscriptionStatus.ACTIVE
    )
    session.add(sub)
    
    # 3. Provision/Re-activate VPN
    vpn_stmt = select(VPNKey).where(VPNKey.user_id == user_id)
    vpn_res = await session.execute(vpn_stmt)
    vpn_key = vpn_res.scalar_one_or_none()
    
    if not vpn_key:
        vpn_data = await vpn_service.create_vpn_user(user_id, expire_at=int(end_date.timestamp()))
        if vpn_data:
            config = await vpn_service.get_vpn_config(vpn_data["uuid"])
            new_vpn = VPNKey(
                user_id=user_id,
                uuid=vpn_data["uuid"],
                config=config or "Config generation in progress...",
                expire_at=end_date
            )
            session.add(new_vpn)
    else:
        await vpn_service.create_vpn_user(user_id, expire_at=int(end_date.timestamp()))
        vpn_key.expire_at = end_date
    
    await session.commit()
    logger.info(f"Successfully processed payment {external_id} for user {user_id}")
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
                    
                    vpn_stmt = select(VPNKey).where(VPNKey.user_id == sub.user_id)
                    vpn_res = await session.execute(vpn_stmt)
                    vpn_key = vpn_res.scalar_one_or_none()
                    
                    if vpn_key:
                        await vpn_service.disable_vpn_user(vpn_key.uuid)
                
                await session.commit()
        except Exception as e:
            logger.error(f"Error in expiration checker: {e}")
        await asyncio.sleep(300)

async def payment_polling():
    """Background task to poll CryptoBot for pending payments."""
    while True:
        try:
            async with AsyncSessionLocal() as session:
                # Find pending payments
                stmt = select(Payment).where(Payment.status == PaymentStatus.PENDING)
                result = await session.execute(stmt)
                pending_payments = result.scalars().all()
                
                if not pending_payments:
                    await asyncio.sleep(30)
                    continue
                
                external_ids = [p.external_id for p in pending_payments]
                invoices = await cryptobot_service.get_invoices(external_ids)
                
                for invoice in invoices:
                    if invoice.get("status") == "paid":
                        payload = invoice.get("payload", "")
                        if ":" in payload:
                            user_id, plan_days = map(int, payload.split(":"))
                            await process_successful_payment(
                                session, 
                                user_id, 
                                plan_days, 
                                float(invoice["amount"]), 
                                str(invoice["invoice_id"])
                            )
        except Exception as e:
            logger.error(f"Error in payment polling: {e}")
        await asyncio.sleep(20)
