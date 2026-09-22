import asyncio
import logging
import os
from aiohttp import web

from .config import PORT
from .database import init_db
from . import web as web_panel

ENABLE_TELEGRAM_BOT = os.getenv("ENABLE_TELEGRAM_BOT", "0") == "1"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
log = logging.getLogger("bot")


async def start_web_server():
    """aiohttp: web panel + health endpoint on same port."""
    app = web.Application(client_max_size=500 * 1024 * 1024)  # 500 MB uploads
    web_panel.register_routes(app)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    log.info(f"Web panel ishga tushdi: 0.0.0.0:{PORT}")


async def main():
    init_db()
    log.info("Baza tayyor")

    await start_web_server()

    if ENABLE_TELEGRAM_BOT:
        from aiogram import Bot, Dispatcher
        from aiogram.client.default import DefaultBotProperties
        from aiogram.enums import ParseMode
        from aiogram.fsm.storage.memory import MemoryStorage
        from .config import BOT_TOKEN
        from .handlers import user, admin
        bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        dp = Dispatcher(storage=MemoryStorage())
        dp.include_router(admin.router)
        dp.include_router(user.router)
        log.info("Telegram bot ishga tushdi (polling)")
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    else:
        log.info("Telegram bot o'chirilgan (faqat sayt ishlaydi)")
        # Keep event loop alive
        while True:
            await asyncio.sleep(3600)


if __name__ == "__main__":
    asyncio.run(main())
