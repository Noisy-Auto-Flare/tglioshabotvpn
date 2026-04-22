import logging
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)

async def run_migrations(engine: AsyncEngine):
    """
    Manual migrations for SQLite to avoid using Alembic for small changes.
    Adds missing columns if they don't exist.
    """
    async with engine.begin() as conn:
        # Check if subscription_id exists in vpn_keys
        # SQLite: PRAGMA table_info(table_name) returns column info
        result = await conn.execute(text("PRAGMA table_info(vpn_keys)"))
        columns = [row[1] for row in result.fetchall()]
        
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
                # SQLite: default 1 (True)
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

        # Add any other missing columns here if needed in the future
