import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, Request, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from db.session import get_db, AsyncSessionLocal, engine
from db.base import Base
from db.migrations import run_migrations
import backend.models.models # Import models to register them with Base
from backend.services.init_db import init_screens
from backend.services.payments import cryptobot_service
from backend.services.tasks import (
    check_expirations,
    payment_polling,
    process_successful_payment,
    vpn_retry_task,
    parse_payment_payload,
)
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
    
    # Run manual migrations for SQLite
    await run_migrations(engine)
    
    # Initialize default screens
    async with AsyncSessionLocal() as db:
        await init_screens(db)
    
    logger.info("Database tables and schema initialized.")

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
    
    if not signature or not cryptobot_service.verify_webhook(body.decode(), signature):
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
            parsed = parse_payment_payload(payload)
            if not parsed:
                logger.error(f"Invalid payload in webhook: {payload}")
                return {"ok": True}
            user_id, plan_days, traffic_gb = parsed
            await process_successful_payment(
                db,
                user_id,
                plan_days,
                amount,
                external_id,
                traffic_gb=traffic_gb
            )
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
    from sqlalchemy import select
    from backend.models.models import User, Subscription, VPNKey
    from backend.services.vpn import vpn_service

    # Find internal user ID if telegram ID is provided
    user_stmt = select(User).where((User.id == user_id) | (User.telegram_id == user_id))
    user_res = await db.execute(user_stmt)
    user = user_res.scalar_one_or_none()
    
    if not user:
        return {"error": "User not found"}
        
    # Get sub and key
    sub_stmt = select(Subscription).where(Subscription.user_id == user.id).order_by(Subscription.end_date.desc())
    sub_res = await db.execute(sub_stmt)
    subs = sub_res.scalars().all()
    
    key_stmt = select(VPNKey).where(VPNKey.user_id == user.id).order_by(VPNKey.expire_at.desc())
    key_res = await db.execute(key_stmt)
    keys = key_res.scalars().all()
    
    return {
        "user": {
            "id": user.id,
            "telegram_id": user.telegram_id,
            "balance": user.balance
        },
        "subscriptions": [
            {"id": s.id, "plan": s.plan, "status": s.status, "end_date": s.end_date} 
            for s in subs
        ],
        "vpn_keys": [
            {
                "id": k.id, 
                "is_active": k.is_active, 
                "error": k.error_message, 
                "expire_at": k.expire_at,
                "uuid": k.uuid
            } 
            for k in keys
        ]
    }

@app.get("/debug/remnawave")
async def debug_remnawave():
    """Debug endpoint to test RemnaWave panel connectivity."""
    from backend.services.vpn import vpn_service
    return await vpn_service.debug_remnawave()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
