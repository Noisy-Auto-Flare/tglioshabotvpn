import asyncio
import logging
import sys
import os

# Add current directory to path to allow imports
sys.path.append(os.getcwd())

from db.session import engine, AsyncSessionLocal
from db.base import Base
import backend.models.models  # Required to register models
from backend.services.init_db import init_screens
from sqlalchemy import text

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def reset_database():
    """
    Completely clears the database by dropping all tables and recreating them.
    Also initializes default data (screens).
    """
    logger.info("Starting database reset...")
    
    try:
        # For SQLite, we might need to disable foreign keys before dropping
        async with engine.begin() as conn:
            logger.info("Disabling foreign keys...")
            await conn.execute(text("PRAGMA foreign_keys = OFF"))
            
            logger.info("Dropping all tables...")
            # We'll drop tables manually to be sure they are gone
            # In SQLite metadata.drop_all works fine but sometimes file locks occur
            await conn.run_sync(Base.metadata.drop_all)
            
            logger.info("Creating all tables...")
            await conn.run_sync(Base.metadata.create_all)
            
            logger.info("Re-enabling foreign keys...")
            await conn.execute(text("PRAGMA foreign_keys = ON"))
        
        # Initialize default screens
        async with AsyncSessionLocal() as db:
            logger.info("Initializing default screens...")
            await init_screens(db)
            await db.commit()
            
        logger.info("Database has been successfully reset.")
    except Exception as e:
        logger.error(f"Failed to reset database: {e}")
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--force":
        asyncio.run(reset_database())
    else:
        confirm = input("Are you sure you want to CLEAR the database? This will delete ALL data. (y/n): ")
        if confirm.lower() == 'y':
            asyncio.run(reset_database())
        else:
            logger.info("Reset cancelled.")
