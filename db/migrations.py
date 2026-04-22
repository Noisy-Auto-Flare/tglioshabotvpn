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
                # SQLite doesn't support ADD COLUMN with FOREIGN KEY directly in ALTER TABLE 
                # but it allows adding the column. We can add it as an Integer.
                # Since foreign_keys=ON is set, it will still enforce it if we declare it correctly.
                await conn.execute(text("ALTER TABLE vpn_keys ADD COLUMN subscription_id INTEGER REFERENCES subscriptions(id)"))
                logger.info("Migration: subscription_id added successfully.")
            except Exception as e:
                logger.error(f"Migration failed for vpn_keys.subscription_id: {e}")

        # Add any other missing columns here if needed in the future
