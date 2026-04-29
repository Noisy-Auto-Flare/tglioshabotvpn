import asyncio
import logging
import httpx
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, Request, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from db.session import get_db, AsyncSessionLocal, engine
from db.base import Base
from db.migrations import run_migrations
import backend.models.models # Import models to register them with Base
from backend.services.init_db import init_screens
from backend.services.payment_service import PaymentService
from backend.services.payments.cryptobot import cryptobot_service
from backend.services.payments.cryptomus import cryptomus_service
from backend.services.payments.platega import platega_service

# ... (other code)

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
    
    # Sync global subscription settings with RemnaWave
    from backend.services.vpn import vpn_service
    await asyncio.to_thread(vpn_service.sync_subscription_settings)
    
    logger.info("Database tables, schema, and RemnaWave settings initialized.")

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
        
        # Если бот находится на другом сервере, пересылаем по HTTP
        if settings.INTERNAL_WEBHOOK_URL:
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    resp = await client.post(
                    settings.INTERNAL_WEBHOOK_URL,
                    json={
                        "external_id": external_id, 
                        "status": "CONFIRMED",
                        "provider": "cryptobot"
                    },
                    headers={"X-Internal-Token": settings.INTERNAL_WEBHOOK_SECRET}
                )
                    resp.raise_for_status()
                    logger.info(f"Forwarded CryptoBot webhook to bot: {resp.status_code}")
                    return {"ok": True, "forwarded": True}
            except Exception as e:
                logger.error(f"Failed to forward CryptoBot webhook: {e}")
                raise HTTPException(status_code=500, detail="Failed to forward to bot")

        # Локальная обработка
        payment_service = PaymentService(db)
        success = await payment_service.process_success(external_id)
        return {"ok": success}
    
    return {"ok": True}

@app.post("/api/v1/payments/cryptomus/webhook")
async def cryptomus_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    data = await request.json()
    if not cryptomus_service.verify_webhook(data):
        raise HTTPException(status_code=400, detail="Invalid signature")
    
    status = data.get("status")
    external_id = data.get("uuid") # Cryptomus uuid for the transaction
    
    if status in ["paid", "paid_over"]:
        # Если бот находится на другом сервере, пересылаем по HTTP
        if settings.INTERNAL_WEBHOOK_URL:
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    resp = await client.post(
                    settings.INTERNAL_WEBHOOK_URL,
                    json={
                        "external_id": str(external_id), 
                        "status": "CONFIRMED",
                        "provider": "cryptomus"
                    },
                    headers={"X-Internal-Token": settings.INTERNAL_WEBHOOK_SECRET}
                )
                    resp.raise_for_status()
                    logger.info(f"Forwarded Cryptomus webhook to bot: {resp.status_code}")
                    return {"ok": True, "forwarded": True}
            except Exception as e:
                logger.error(f"Failed to forward Cryptomus webhook: {e}")
                raise HTTPException(status_code=500, detail="Failed to forward to bot")

        # Локальная обработка
        payment_service = PaymentService(db)
        await payment_service.process_success(str(external_id))
    
    return {"ok": True}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

@app.post("/api/v1/payments/platega/webhook")
async def platega_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    data = await request.json()
    headers = dict(request.headers)
    
    if not platega_service.verify_webhook(data, headers):
        logger.warning(f"Invalid Platega webhook headers: {headers}")
        raise HTTPException(status_code=400, detail="Invalid signature/headers")
    
    status = data.get("status")
    order_id = data.get("payload") # We stored order_id in the payload field
    
    if not order_id or not status:
        logger.error(f"Missing payload/status in Platega webhook: {data}")
        return {"ok": False, "error": "missing fields"}

    # Если бот находится на другом сервере, пересылаем вебхук по HTTP
    if settings.INTERNAL_WEBHOOK_URL:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    settings.INTERNAL_WEBHOOK_URL,
                    json={
                        "external_id": order_id, 
                        "status": status,
                        "provider": "platega"
                    },
                    headers={"X-Internal-Token": settings.INTERNAL_WEBHOOK_SECRET}
                )
                resp.raise_for_status()
                logger.info(f"Forwarded Platega webhook to bot: {resp.status_code}")
                return {"ok": True, "forwarded": True}
        except Exception as e:
            logger.error(f"Failed to forward webhook to bot: {e}")
            raise HTTPException(status_code=500, detail="Failed to forward to bot")
    
    # Если на этом же сервере, обрабатываем локально
    if status == "CONFIRMED":
        payment_service = PaymentService(db)
        await payment_service.process_success(str(order_id))
        logger.info(f"Platega payment confirmed locally for order {order_id}")
    elif status == "CANCELED":
        logger.info(f"Platega payment canceled for order {order_id}")
    
    return {"ok": True}

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
