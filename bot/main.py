import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiohttp import web

from .config import BOT_TOKEN, PORT
from .database import init_db
from .handlers import user, admin
from . import web as web_panel

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

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(admin.router)
    dp.include_router(user.router)

    await start_web_server()

    log.info("Bot ishga tushdi (polling)")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
