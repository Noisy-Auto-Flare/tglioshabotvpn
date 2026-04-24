from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.models.models import Screen

class ContentService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_screen(self, key: str) -> Optional[Screen]:
        result = await self.db.execute(select(Screen).where(Screen.key == key))
        return result.scalar_one_or_none()

    async def update_screen(self, key: str, text: Optional[str] = None, image_url: Optional[str] = None) -> Screen:
        screen = await self.get_screen(key)
        if not screen:
            screen = Screen(key=key, text=text or "", image_url=image_url)
            self.db.add(screen)
        else:
            if text is not None:
                screen.text = text
            if image_url is not None:
                screen.image_url = image_url
        
        await self.db.commit()
        await self.db.refresh(screen)
        return screen

    async def get_all_screens(self) -> list[Screen]:
        result = await self.db.execute(select(Screen))
        return list(result.scalars().all())
