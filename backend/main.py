import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, Request, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from db.session import get_db, AsyncSessionLocal
from backend.services.payments import cryptobot_service
from backend.services.tasks import check_expirations, payment_polling, process_successful_payment

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start background tasks
    tasks = []
    tasks.append(asyncio.create_task(check_expirations()))
    
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
