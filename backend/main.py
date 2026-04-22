import asyncio
import logging
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, Request, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from db.session import get_db, AsyncSessionLocal
from backend.models.models import User, Subscription, VPNKey, SubscriptionStatus, Payment, PaymentStatus
from backend.services.vpn import vpn_service
from backend.services.payments import cryptobot_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def check_expirations():
    """Background task to check for expired subscriptions every 5 minutes."""
    while True:
        try:
            async with AsyncSessionLocal() as session:
                # Find expired subscriptions that are still marked as active
                now = datetime.now(timezone.utc).replace(tzinfo=None)
                stmt = select(Subscription).where(
                    Subscription.end_date < now,
                    Subscription.status == SubscriptionStatus.ACTIVE
                )
                result = await session.execute(stmt)
                expired_subs = result.scalars().all()

                for sub in expired_subs:
                    logger.info(f"Subscription {sub.id} for user {sub.user_id} has expired.")
                    # 1. Update status to expired
                    sub.status = SubscriptionStatus.EXPIRED
                    
                    # 2. Find and disable VPN key for this user
                    vpn_stmt = select(VPNKey).where(VPNKey.user_id == sub.user_id)
                    vpn_res = await session.execute(vpn_stmt)
                    vpn_key = vpn_res.scalar_one_or_none()
                    
                    if vpn_key:
                        success = await vpn_service.disable_vpn_user(vpn_key.uuid)
                        if success:
                            logger.info(f"Disabled VPN key {vpn_key.uuid} for user {sub.user_id}")
                
                await session.commit()
        except Exception as e:
            logger.error(f"Error in expiration checker: {e}")
        
        await asyncio.sleep(300)  # 5 minutes

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start background task
    bg_task = asyncio.create_task(check_expirations())
    yield
    # Stop background task
    bg_task.cancel()
    try:
        await bg_task
    except asyncio.CancelledError:
        pass

app = FastAPI(title="VPN Bot Backend", lifespan=lifespan)

@app.post("/api/v1/payments/cryptobot/webhook")
async def cryptobot_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    body = await request.body()
    signature = request.headers.get("Crypto-Pay-API-Signature")
    
    if not cryptobot_service.verify_webhook(body.decode(), signature):
        raise HTTPException(status_code=400, detail="Invalid signature")
    
    data = await request.json()
    if data.get("update_type") == "invoice_paid":
        invoice = data.get("payload")
        external_id = str(invoice.get("invoice_id"))
        amount = float(invoice.get("amount"))
        user_id_str = invoice.get("payload") # we pass user_id in payload
        
        if not user_id_str:
            return {"ok": True}
        
        user_id = int(user_id_str)
        
        # Idempotency check
        stmt = select(Payment).where(Payment.external_id == external_id)
        result = await db.execute(stmt)
        if result.scalar_one_or_none():
            return {"ok": True}
        
        # 1. Record payment
        payment = Payment(
            user_id=user_id,
            amount=amount,
            provider="cryptobot",
            status=PaymentStatus.COMPLETED,
            external_id=external_id
        )
        db.add(payment)
        
        # 2. Update user balance or activate subscription directly
        # For simplicity, let's say payment was for a specific plan
        # We could store plan_id in payload as well: "user_id:plan_days"
        parts = user_id_str.split(":")
        user_id = int(parts[0])
        plan_days = int(parts[1]) if len(parts) > 1 else 30
        
        # Update user's subscription
        now = datetime.now()
        end_date = now + asyncio.timedelta(days=plan_days)
        
        sub = Subscription(
            user_id=user_id,
            plan=str(plan_days),
            start_date=now,
            end_date=end_date,
            status=SubscriptionStatus.ACTIVE
        )
        db.add(sub)
        
        # 3. Provision/Re-activate VPN
        # Check if user already has a VPN key
        vpn_stmt = select(VPNKey).where(VPNKey.user_id == user_id)
        vpn_res = await db.execute(vpn_stmt)
        vpn_key = vpn_res.scalar_one_or_none()
        
        if not vpn_key:
            # Create new VPN user
            vpn_data = await vpn_service.create_vpn_user(user_id, expire_at=int(end_date.timestamp()))
            if vpn_data:
                config = await vpn_service.get_vpn_config(vpn_data["uuid"])
                new_vpn = VPNKey(
                    user_id=user_id,
                    uuid=vpn_data["uuid"],
                    config=config or "",
                    expire_at=end_date
                )
                db.add(new_vpn)
        else:
            # Re-activate existing key (logic depends on RemnaWave API)
            await vpn_service.create_vpn_user(user_id, expire_at=int(end_date.timestamp()))
            vpn_key.expire_at = end_date
        
        await db.commit()
    
    return {"ok": True}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
