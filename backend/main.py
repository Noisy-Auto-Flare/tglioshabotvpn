import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, Request, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from db.session import get_db, AsyncSessionLocal, engine
from db.base import Base
import backend.models.models # Import models to register them with Base
from backend.services.payments import cryptobot_service
from backend.services.tasks import check_expirations, payment_polling, process_successful_payment, vpn_retry_task
from backend.models.models import VPNKey, User, Subscription

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize database tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables initialized.")

    # Start background tasks
    tasks = []
    tasks.append(asyncio.create_task(check_expirations()))
    tasks.append(asyncio.create_task(vpn_retry_task()))
    
    if not settings.USE_WEBHOOK:
        logger.info("Webhooks disabled. Starting payment polling task...")
        tasks.append(asyncio.create_task(payment_polling()))
    else:
        logger.info("Webhooks enabled.")
        
    yield
    
    # Stop background tasks
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)

app = FastAPI(
    title="VPN Bot Backend", 
    lifespan=lifespan,
    debug=settings.DEBUG
)

@app.post("/api/v1/payments/cryptobot/webhook")
async def cryptobot_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    if not settings.USE_WEBHOOK:
        raise HTTPException(status_code=404, detail="Webhooks are disabled")
        
    body = await request.body()
    signature = request.headers.get("Crypto-Pay-API-Signature")
    
    if not cryptobot_service.verify_webhook(body.decode(), signature):
        logger.warning("Invalid CryptoBot webhook signature received")
        raise HTTPException(status_code=400, detail="Invalid signature")
    
    data = await request.json()
    if data.get("update_type") == "invoice_paid":
        invoice = data.get("payload")
        external_id = str(invoice.get("invoice_id"))
        amount = float(invoice.get("amount"))
        payload = invoice.get("payload", "")
        
        if ":" not in payload:
            logger.error(f"Invalid payload in webhook: {payload}")
            return {"ok": True}
        
        try:
            user_id, plan_days = map(int, payload.split(":"))
            await process_successful_payment(db, user_id, plan_days, amount, external_id)
        except Exception as e:
            logger.error(f"Failed to process webhook payment: {e}")
            raise HTTPException(status_code=500, detail="Internal processing error")
    
    return {"ok": True}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

@app.get("/debug/vpn/{user_id}")
async def debug_vpn(user_id: int, db: AsyncSession = Depends(get_db)):
    """Debug endpoint to check VPN status for a user."""
    # Find internal user ID if telegram ID is provided
    user_stmt = select(User).where((User.id == user_id) | (User.telegram_id == user_id))
    user_res = await db.execute(user_stmt)
    user = user_res.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Get all VPN keys for user
    vpn_stmt = select(VPNKey).where(VPNKey.user_id == user.id).order_by(VPNKey.expire_at.desc())
    vpn_res = await db.execute(vpn_stmt)
    vpn_keys = vpn_res.scalars().all()
    
    # Get all subscriptions for user
    sub_stmt = select(Subscription).where(Subscription.user_id == user.id).order_by(Subscription.end_date.desc())
    sub_res = await db.execute(sub_stmt)
    subs = sub_res.scalars().all()
    
    return {
        "user": {
            "id": user.id,
            "telegram_id": user.telegram_id,
            "balance": user.balance
        },
        "subscriptions": [
            {
                "id": s.id,
                "plan": s.plan,
                "status": s.status,
                "end_date": s.end_date
            } for s in subs
        ],
        "vpn_keys": [
            {
                "id": v.id,
                "subscription_id": v.subscription_id,
                "uuid": v.uuid,
                "is_active": v.is_active,
                "expire_at": v.expire_at,
                "error_message": v.error_message,
                "config_preview": v.config[:50] + "..." if v.config else None
            } for v in vpn_keys
        ]
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
