import asyncio
import logging
import sys
import os
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Add current directory to path so we can import our modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from db.session import AsyncSessionLocal
from backend.models.models import User, Subscription, VPNKey, SubscriptionStatus
from backend.services.vpn import vpn_service

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("sync_users")

async def sync_users():
    logger.info("Starting synchronization with RemnaWave...")
    
    # Get all users from RemnaWave
    rw_users = vpn_service.list_users()
    logger.info(f"Found {len(rw_users)} users in RemnaWave")
    
    async with AsyncSessionLocal() as db:
        for rw_user in rw_users:
            try:
                username = rw_user.get("username")
                # Try to get telegram ID from telegramId field or from username
                tg_id = rw_user.get("telegramId")
                
                if not tg_id and username and username.startswith("user_"):
                    # user_12345678 or user_12345678_sub_1
                    parts = username.split("_")
                    if len(parts) >= 2 and parts[1].isdigit():
                        tg_id = int(parts[1])
                
                if not tg_id:
                    logger.warning(f"Could not determine Telegram ID for user {username}, skipping")
                    continue
                
                # Check if user exists in our DB
                stmt = select(User).where(User.telegram_id == tg_id)
                res = await db.execute(stmt)
                db_user = res.scalar_one_or_none()
                
                if not db_user:
                    logger.info(f"Creating new user {tg_id} from RW")
                    db_user = User(
                        telegram_id=tg_id,
                        referral_code=f"ref_{tg_id}" # Default referral code
                    )
                    db.add(db_user)
                    await db.flush()
                
                # Check if they have an active VPN key in our DB
                uuid = rw_user.get("uuid")
                stmt = select(VPNKey).where(VPNKey.uuid == uuid)
                res = await db.execute(stmt)
                db_key = res.scalar_one_or_none()
                
                if not db_key:
                    logger.info(f"Syncing VPN key for user {tg_id} (UUID: {uuid})")
                    
                    expire_at_str = rw_user.get("expireAt")
                    expire_at = None
                    if expire_at_str:
                        # 2024-04-27T19:32:17Z
                        try:
                            expire_at = datetime.strptime(expire_at_str, "%Y-%m-%dT%H:%M:%SZ")
                        except ValueError:
                            try:
                                expire_at = datetime.fromisoformat(expire_at_str.replace('Z', '+00:00'))
                            except:
                                pass
                    
                    if not expire_at:
                        expire_at = datetime.now() # Fallback
                    
                    # Create a subscription record for them
                    sub = Subscription(
                        user_id=db_user.id,
                        plan="sync",
                        traffic_limit_gb=int(rw_user.get("trafficLimitBytes", 0) / 1024**3),
                        start_date=datetime.now(),
                        end_date=expire_at,
                        status=SubscriptionStatus.ACTIVE if rw_user.get("status") == "ACTIVE" else SubscriptionStatus.EXPIRED
                    )
                    db.add(sub)
                    await db.flush()
                    
                    # Create VPN key record
                    db_key = VPNKey(
                        user_id=db_user.id,
                        subscription_id=sub.id,
                        uuid=uuid,
                        config=rw_user.get("subscriptionUrl") or f"Manual sync for {username}",
                        expire_at=expire_at,
                        is_active=rw_user.get("status") == "ACTIVE"
                    )
                    db.add(db_key)
                
                await db.commit()
                
            except Exception as e:
                logger.error(f"Error syncing user {rw_user.get('username')}: {e}")
                await db.rollback()

    logger.info("Synchronization completed.")

if __name__ == "__main__":
    asyncio.run(sync_users())
