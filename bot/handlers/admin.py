import asyncio
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from ..config import ADMIN_IDS
from ..database import list_stores, set_discount, replace_products, stats
from ..parser import parse_excel
from ..store_detect import detect_store
from ..url_download import download_url

router = Router()

TG_FILE_LIMIT = 20 * 1024 * 1024  # 20 MB Bot API limit


class UpdateStore(StatesGroup):
    waiting_file = State()


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


@router.message(Command("admin"))
async def cmd_admin(m: Message):
    if not is_admin(m.from_user.id):
        await m.answer("⛔ Bu buyruq faqat admin uchun.")
        return
    await m.answer(
        "<b>🛠 Admin panel</b>\n\n"
        "<b>Excel yuklash — 2 xil usul:</b>\n"
        "1️⃣ <b>Avtomatik:</b> shunchaki Excel faylni yuboring — bot fayl nomidan do'konni aniqlaydi\n"
        "   Bir vaqtda bir nechta fayl yuborsangiz ham bo'ladi\n"
        "2️⃣ <b>Qo'lda:</b> /update DoкonNomi + fayl\n"
        "3️⃣ <b>URL orqali (20 MB dan katta fayllar uchun):</b>\n"
        "   /upload_url DoкonNomi &lt;URL&gt;\n"
        "   (Google Drive, Dropbox va boshqa to'g'ridan-to'g'ri havolalar)\n\n"
        "<b>Boshqa buyruqlar:</b>\n"
        "/set_discount DoкonNomi 25 — skidkani o'zgartirish\n"
        "/list_stores — do'konlar va mahsulotlar soni\n"
        "/stats — statistika\n"
        "/cancel — bekor qilish\n\n"
        "⚠️ Telegram Bot API 20 MB dan katta faylni qabul qilmaydi."
    )


@router.message(Command("list_stores"))
async def cmd_list(m: Message):
    if not is_admin(m.from_user.id):
        return
    rows = list_stores()
    if not rows:
        await m.answer("Do'konlar yo'q.")
        return
    text = "<b>🏬 Do'konlar:</b>\n\n"
    for r in rows:
        text += f"• <b>{r['name']}</b> — skidka {r['discount']:.0f}%, mahsulot: <b>{r['cnt']}</b>\n"
    await m.answer(text)


@router.message(Command("stats"))
async def cmd_stats(m: Message):
    if not is_admin(m.from_user.id):
        return
    total, by_store = stats()
    text = f"<b>📊 Statistika</b>\n\nJami mahsulotlar: <b>{total}</b>\n\n"
    for r in by_store:
        text += f"• {r['store']}: <b>{r['n']}</b>\n"
    await m.answer(text)


@router.message(Command("set_discount"))
async def cmd_set_discount(m: Message):
    if not is_admin(m.from_user.id):
        return
    parts = m.text.split()
    if len(parts) < 3:
        await m.answer("Format: <code>/set_discount DoкonNomi 25</code>")
        return
    store = parts[1]
    try:
        disc = float(parts[2].rstrip("%"))
    except ValueError:
        await m.answer("Skidka raqam bo'lishi kerak.")
        return
    set_discount(store, disc)
    await m.answer(f"✅ <b>{store}</b> uchun skidka <b>{disc:.0f}%</b> ga o'rnatildi.")


@router.message(Command("update"))
async def cmd_update(m: Message, state: FSMContext):
    if not is_admin(m.from_user.id):
        return
    parts = m.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await m.answer(
            "Format: <code>/update DoкonNomi</code> — keyin Excel faylni yuboring.\n\n"
            "Yoki shunchaki Excel faylni yuboring — bot fayl nomidan avtomatik aniqlaydi."
        )
        return
    store = parts[1].strip()
    await state.set_state(UpdateStore.waiting_file)
    await state.update_data(store=store)
    await m.answer(
        f"📎 <b>{store}</b> uchun Excel faylni yuboring (.xlsx).\n"
        f"Bekor qilish: /cancel"
    )


@router.message(Command("upload_url"))
async def cmd_upload_url(m: Message):
    if not is_admin(m.from_user.id):
        return
    parts = m.text.split(maxsplit=2)
    if len(parts) < 3:
        await m.answer(
            "Format: <code>/upload_url DoкonNomi https://drive.google.com/...</code>\n\n"
            "Google Drive'da faylni oching → 'Ulashish' → 'Havolaga ega har kim ko'ra oladi' → havolani nusxa oling."
        )
        return
    store = parts[1].strip()
    url = parts[2].strip()

    status = await m.answer(f"⏳ <b>{store}</b> uchun URL'dan yuklanmoqda...")

    try:
        raw, filename = await download_url(url)
    except Exception as e:
        await status.edit_text(f"❌ URL yuklashda xato: {e}")
        return

    size_mb = len(raw) / 1024 / 1024
    await status.edit_text(f"✅ Yuklandi: <b>{filename}</b> ({size_mb:.1f} MB)\n⏳ Excel o'qilmoqda...")

    try:
        items = await asyncio.to_thread(parse_excel, raw)
    except Exception as e:
        await status.edit_text(f"❌ Excel o'qishda xato: {e}")
        return

    if not items:
        await status.edit_text(
            f"❌ Excel'dan mahsulot topilmadi.\n"
            "Ustunlarda 'Model'/'Nomi' va 'Narx'/'Price'/'Цена' bo'lishi kerak."
        )
        return

    replace_products(store, items)
    await status.edit_text(
        f"✅ <b>{store}</b> ({filename}, {size_mb:.1f} MB)\n"
        f"📦 Yuklandi: <b>{len(items)}</b> mahsulot"
    )


@router.message(F.text.regexp(r"^\s*https?://(docs\.google\.com/spreadsheets|drive\.google\.com|.+\.(xlsx|xls))"))
async def handle_url_only(m: Message):
    """Admin sent just a URL — auto-detect store from filename."""
    if not is_admin(m.from_user.id):
        return
    url = m.text.strip()
    status = await m.answer("⏳ URL'dan yuklanmoqda...")

    try:
        raw, filename = await download_url(url)
    except Exception as e:
        await status.edit_text(f"❌ Yuklashda xato: {e}")
        return

    store = detect_store(filename)
    size_mb = len(raw) / 1024 / 1024

    if not store:
        await status.edit_text(
            f"⚠️ Fayl yuklandi: <b>{filename}</b> ({size_mb:.1f} MB)\n"
            f"Lekin do'kon nomini fayl nomidan aniqlab bo'lmadi.\n\n"
            f"Iltimos, do'kon nomi bilan qayta yuboring:\n"
            f"<code>/upload_url DoкonNomi {url}</code>"
        )
        return

    await status.edit_text(f"✅ {filename} ({size_mb:.1f} MB) → <b>{store}</b>\n⏳ O'qilmoqda...")

    try:
        items = await asyncio.to_thread(parse_excel, raw)
    except Exception as e:
        await status.edit_text(f"❌ Excel o'qishda xato: {e}")
        return

    if not items:
        await status.edit_text(
            f"❌ <b>{filename}</b> — mahsulot topilmadi.\n"
            "Ustunlarda 'Model'/'Nomi' va 'Narx'/'Price'/'Цена' bo'lishi kerak."
        )
        return

    replace_products(store, items)
    await status.edit_text(
        f"✅ <b>{store}</b> ({filename}, {size_mb:.1f} MB)\n"
        f"📦 Yuklandi: <b>{len(items)}</b> mahsulot"
    )


@router.message(Command("cancel"))
async def cmd_cancel(m: Message, state: FSMContext):
    if not is_admin(m.from_user.id):
        return
    await state.clear()
    await m.answer("❌ Bekor qilindi.")


async def _process_excel(m: Message, bot: Bot, store: str) -> None:
    doc = m.document
    if not (doc.file_name or "").lower().endswith((".xlsx", ".xls", ".xlsm")):
        await m.reply(f"⚠️ <b>{doc.file_name}</b> — Excel emas.")
        return

    if doc.file_size and doc.file_size > TG_FILE_LIMIT:
        mb = doc.file_size / 1024 / 1024
        await m.reply(
            f"❌ <b>{doc.file_name}</b> — {mb:.1f} MB. "
            f"Telegram Bot API 20 MB dan katta faylni qabul qilmaydi.\n\n"
            f"💡 Yechim: Excel'ni ochib, keraksiz sheet'larni o'chiring yoki 2 ta faylga bo'lib yuboring."
        )
        return

    status = await m.reply(f"⏳ <b>{doc.file_name}</b> → <b>{store}</b>: o'qilmoqda...")

    try:
        file = await bot.get_file(doc.file_id)
        buf = await bot.download_file(file.file_path)
        raw = buf.read()
    except Exception as e:
        await status.edit_text(f"❌ Yuklashda xato: {e}")
        return

    try:
        items = await asyncio.to_thread(parse_excel, raw)
    except Exception as e:
        await status.edit_text(f"❌ Excel o'qishda xato: {e}")
        return

    if not items:
        await status.edit_text(
            f"❌ <b>{doc.file_name}</b> — mahsulot topilmadi.\n"
            "Ustunlarda 'Model'/'Nomi' va 'Narx'/'Price'/'Цена' bo'lishi kerak."
        )
        return

    replace_products(store, items)
    await status.edit_text(
        f"✅ <b>{store}</b> ({doc.file_name})\n"
        f"📦 Yuklandi: <b>{len(items)}</b> mahsulot"
    )


# Manual mode: /update Store → send file
@router.message(UpdateStore.waiting_file, F.document)
async def handle_excel_manual(m: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    store = data.get("store")
    await state.clear()
    await _process_excel(m, bot, store)


@router.message(UpdateStore.waiting_file)
async def handle_not_file(m: Message):
    await m.answer("📎 Iltimos, Excel <b>fayl</b> yuboring yoki /cancel bosing.")


# Auto mode: admin sends any Excel document, we detect store from filename
@router.message(F.document)
async def handle_excel_auto(m: Message, bot: Bot):
    if not is_admin(m.from_user.id):
        return
    doc = m.document
    filename = doc.file_name or ""
    if not filename.lower().endswith((".xlsx", ".xls", ".xlsm")):
        return

    store = detect_store(filename)
    if not store:
        await m.reply(
            f"⚠️ <b>{filename}</b> — do'kon nomini aniqlab bo'lmadi.\n\n"
            "Qo'lda yuklash uchun: <code>/update DoкonNomi</code> keyin faylni yuboring.\n\n"
            "Aniqlanadigan kalitlar: system service, darian, ezviz, hilook/hikvision, kss, mus"
        )
        return

    await _process_excel(m, bot, store)
