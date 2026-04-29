import json
import logging
from aiohttp import web
from backend.services.payment_service import PaymentService
from db.session import AsyncSessionLocal
from backend.core.config import settings

logger = logging.getLogger(__name__)

# Секретный токен из настроек
INTERNAL_SECRET = settings.INTERNAL_WEBHOOK_SECRET

async def handle_platega_webhook(request: web.Request):
    # 1. Проверяем авторизацию
    token = request.headers.get("X-Internal-Token")
    if not token or token != INTERNAL_SECRET:
        logger.warning("Unauthorized internal webhook attempt")
        return web.json_response({"error": "unauthorized"}, status=401)

    # 2. Читаем тело
    try:
        data = await request.json()
    except json.JSONDecodeError:
        return web.json_response({"error": "invalid json"}, status=400)

    external_id = data.get("external_id")
    status = data.get("status")
    provider = data.get("provider", "unknown")

    if not external_id or not status:
        return web.json_response({"error": "missing fields"}, status=400)

    logger.info(f"Internal webhook from {provider}: {external_id} -> {status}")

    # 3. Выполняем бизнес-логику бота
    async with AsyncSessionLocal() as db:
        payment_service = PaymentService(db)

        try:
            if status == "CONFIRMED":
                success = await payment_service.process_success(external_id)
                if success:
                    logger.info(f"Subscription activated for {external_id}")
                    return web.json_response({"result": "success"})
                else:
                    return web.json_response({"result": "already_processed"}, status=200)

            elif status in ("CANCELED", "CHARGEBACKED"):
                await payment_service.fail_payment(external_id)
                return web.json_response({"result": "failed"})

            else:
                logger.warning(f"Unknown status: {status}")
                return web.json_response({"result": "unknown_status"}, status=400)

        except Exception as e:
            logger.exception(f"Error processing {external_id}: {e}")
            return web.json_response({"error": "internal_error"}, status=500)

async def run_internal_server():
    app = web.Application()
    app.router.add_post("/internal/platega-webhook", handle_platega_webhook)
    
    host = settings.INTERNAL_HOST
    port = settings.INTERNAL_PORT
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    
    logger.info(f"Starting internal webhook server on {host}:{port}")
    await site.start()

if __name__ == "__main__":
    # Для запуска как отдельного процесса
    logging.basicConfig(level=logging.INFO)
    app = web.Application()
    app.router.add_post("/internal/platega-webhook", handle_platega_webhook)
    web.run_app(app, host=settings.INTERNAL_HOST, port=settings.INTERNAL_PORT)
