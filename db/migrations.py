import logging
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)

async def run_migrations(engine: AsyncEngine):
    """
    Manual migrations for SQLite to avoid using Alembic for small changes.
    Adds missing columns if they don't exist.
    """
    logger.info("Starting manual database migrations...")
    async with engine.begin() as conn:
        # Helper to check columns
        async def get_columns(table_name):
            try:
                result = await conn.execute(text(f"PRAGMA table_info({table_name})"))
                cols = [row[1] for row in result.fetchall()]
                logger.info(f"Columns in {table_name}: {cols}")
                return cols
            except Exception as e:
                logger.error(f"Failed to get columns for {table_name}: {e}")
                return []

        # 1. Check vpn_keys
        columns = await get_columns("vpn_keys")
        if columns:
            if "subscription_id" not in columns:
                logger.info("Migration: Adding subscription_id column to vpn_keys table...")
                try:
                    await conn.execute(text("ALTER TABLE vpn_keys ADD COLUMN subscription_id INTEGER REFERENCES subscriptions(id)"))
                    logger.info("Migration: subscription_id added successfully.")
                except Exception as e:
                    logger.error(f"Migration failed for vpn_keys.subscription_id: {e}")

            if "is_active" not in columns:
                logger.info("Migration: Adding is_active column to vpn_keys table...")
                try:
                    await conn.execute(text("ALTER TABLE vpn_keys ADD COLUMN is_active BOOLEAN DEFAULT 1"))
                    logger.info("Migration: is_active added successfully.")
                except Exception as e:
                    logger.error(f"Migration failed for vpn_keys.is_active: {e}")

            if "error_message" not in columns:
                logger.info("Migration: Adding error_message column to vpn_keys table...")
                try:
                    await conn.execute(text("ALTER TABLE vpn_keys ADD COLUMN error_message TEXT"))
                    logger.info("Migration: error_message added successfully.")
                except Exception as e:
                    logger.error(f"Migration failed for vpn_keys.error_message: {e}")

        # 2. Check subscriptions
        subs_columns = await get_columns("subscriptions")
        if subs_columns:
            if "traffic_limit_gb" not in subs_columns:
                logger.info("Migration: Adding traffic_limit_gb column to subscriptions table...")
                try:
                    await conn.execute(text("ALTER TABLE subscriptions ADD COLUMN traffic_limit_gb INTEGER"))
                    logger.info("Migration: traffic_limit_gb added successfully.")
                except Exception as e:
                    logger.error(f"Migration failed for subscriptions.traffic_limit_gb: {e}")

        # 3. Check payments
        payments_columns = await get_columns("payments")
        if payments_columns:
            # List of columns to check/add for payments table
            needed_payments_columns = [
                ("currency", "TEXT DEFAULT 'RUB'"),
                ("payload", "TEXT"),
                ("created_at", "DATETIME DEFAULT CURRENT_TIMESTAMP"),
                ("updated_at", "DATETIME DEFAULT CURRENT_TIMESTAMP")
            ]
            
            for col_name, col_type in needed_payments_columns:
                if col_name not in payments_columns:
                    logger.info(f"Migration: Adding {col_name} column to payments table...")
                    try:
                        await conn.execute(text(f"ALTER TABLE payments ADD COLUMN {col_name} {col_type}"))
                        logger.info(f"Migration: {col_name} added successfully.")
                    except Exception as e:
                        logger.error(f"Migration failed for payments.{col_name}: {e}")
        else:
            logger.warning("Migration: payments table not found or empty column list. Skipping payments migration.")
