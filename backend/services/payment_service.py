import logging
from typing import Optional
from datetime import datetime, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.models import User, Payment, PaymentStatus, Subscription, SubscriptionStatus, VPNKey
from backend.core.config import settings
from backend.services.vpn import vpn_service

logger = logging.getLogger(__name__)

class PaymentService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_payment(self, user_id: int, tariff_id: str, provider: str, amount: float, currency: str = "RUB", external_id: Optional[str] = None) -> Payment:
        payment = Payment(
            user_id=user_id,
            amount=amount,
            currency=currency,
            provider=provider,
            status=PaymentStatus.PENDING,
            external_id=external_id,
            payload=tariff_id
        )
        self.db.add(payment)
        await self.db.commit()
        await self.db.refresh(payment)
        return payment

    async def process_success(self, external_id: str) -> Optional[dict]:
        stmt = select(Payment).where(Payment.external_id == external_id)
        result = await self.db.execute(stmt)
        payment = result.scalar_one_or_none()

        if not payment:
            logger.error(f"Payment with external_id {external_id} not found")
            return None

        if payment.status == PaymentStatus.SUCCESS:
            logger.info(f"Payment {external_id} already processed")
            return None

        # Update payment status
        payment.status = PaymentStatus.SUCCESS
        
        # Get user
        user_stmt = select(User).where(User.id == payment.user_id)
        user_result = await self.db.execute(user_stmt)
        user = user_result.scalar_one()

        # Handle Balance Deposit
        if payment.payload and payment.payload.startswith("dep_"):
            amount_to_add = payment.amount
            user.balance += amount_to_add
            await self.db.commit()
            logger.info(f"Balance deposit of {amount_to_add} RUB processed for user {user.telegram_id}")
            return {
                "user_id": user.telegram_id,
                "type": "deposit",
                "amount": amount_to_add
            }

        # Activate subscription (existing logic)
        plan_id = payment.payload or "30" # Fallback to 30 days
        plan_days = int(plan_id)
        plan_config = settings.PLANS.get(plan_id, {"gb": 300})
        traffic_gb = plan_config.get("gb", 300)

        now = datetime.now()
        end_date = now + timedelta(days=plan_days)

        subscription = Subscription(
            user_id=user.id,
            plan=payment.payload,
            traffic_limit_gb=traffic_gb,
            start_date=now,
            end_date=end_date,
            status=SubscriptionStatus.ACTIVE
        )
        self.db.add(subscription)
        await self.db.flush()

        # Create VPN Key
        try:
            import asyncio
            vpn_data = await asyncio.to_thread(
                vpn_service.create_user_and_get_link,
                user.telegram_id,
                traffic_gb,
                plan_days,
                sub_id=subscription.id
            )
            
            if vpn_data:
                vpn_key = VPNKey(
                    user_id=user.id,
                    subscription_id=subscription.id,
                    uuid=vpn_data["uuid"],
                    config=vpn_data["link"],
                    expire_at=end_date,
                    is_active=True
                )
            else:
                vpn_key = VPNKey(
                    user_id=user.id,
                    subscription_id=subscription.id,
                    config="Creation failed",
                    expire_at=end_date,
                    is_active=False,
                    error_message="RemnaWave API error"
                )
            self.db.add(vpn_key)
        except Exception as e:
            logger.error(f"Failed to create VPN key for user {user.telegram_id}: {e}")

        await self.db.commit()
        logger.info(f"Payment {external_id} processed successfully for user {user.telegram_id}")
        return {
            "user_id": user.telegram_id,
            "type": "subscription",
            "plan_label": plan_config.get("label", f"{plan_days} дней")
        }

    async def fail_payment(self, external_id: str):
        stmt = select(Payment).where(Payment.external_id == external_id)
        result = await self.db.execute(stmt)
        payment = result.scalar_one_or_none()
        if payment and payment.status == PaymentStatus.PENDING:
            payment.status = PaymentStatus.FAILED
            await self.db.commit()

    async def get_payment_status(self, external_id: str) -> Optional[PaymentStatus]:
        stmt = select(Payment).where(Payment.external_id == external_id)
        result = await self.db.execute(stmt)
        payment = result.scalar_one_or_none()
        return payment.status if payment else None
