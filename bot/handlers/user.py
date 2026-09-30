import asyncio
from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message

from ..search import search_models
from ..config import MAX_MODELS_PER_REQUEST, EZVIZ_SECONDARY_DISCOUNT

router = Router()

WELCOME = (
    "👋 <b>Salom!</b>\n\n"
    "Men — <b>Narxlar Boti</b>man. Menga tovar model nomini yuboring, "
    "men barcha do'konlarning narxlarini skidka bilan hisoblab beraman.\n\n"
    "📝 <b>Qanday ishlatish:</b>\n"
    "• Bitta model: <code>DS-7608NI-Q1</code>\n"
    "• Bir nechta (max 50 ta): har qatorda yoki vergul bilan\n\n"
    "<code>DS-7608NI-Q1\nDS-2CD2043G2-I\nHilook IPC-B620H</code>\n\n"
    "ℹ️ Yordam uchun /help"
)

HELP = (
    "<b>📖 Yordam</b>\n\n"
    "1. Model nomini yuboring (bitta yoki bir nechta)\n"
    "2. Bir vaqtda 50 tagacha model qabul qilinadi\n"
    "3. Modellarni <b>yangi qatordan</b> yoki <b>vergul bilan</b> ajrating\n\n"
    "<b>Buyruqlar:</b>\n"
    "/start — Boshlash\n"
    "/help — Yordam\n"
)


def split_models(text: str) -> list[str]:
    from ..search import split_query
    return split_query(text)


@router.message(CommandStart())
async def cmd_start(m: Message):
    await m.answer(WELCOME)


@router.message(Command("help"))
async def cmd_help(m: Message):
    await m.answer(HELP)


@router.message(Command("myid"))
async def cmd_myid(m: Message):
    await m.answer(
        f"🆔 <b>Sizning ma'lumotlaringiz:</b>\n\n"
        f"User ID: <code>{m.from_user.id}</code>\n"
        f"Username: @{m.from_user.username or '—'}\n"
        f"Ism: {m.from_user.full_name}"
    )


@router.message(F.text & ~F.text.startswith("/"))
async def handle_search(m: Message):
    queries = split_models(m.text)
    if not queries:
        await m.answer("❌ Model nomi topilmadi.")
        return

    if len(queries) > MAX_MODELS_PER_REQUEST:
        await m.answer(
            f"⚠️ Bir so'rovda maksimal <b>{MAX_MODELS_PER_REQUEST}</b> ta model. "
            f"Siz {len(queries)} ta yubordingiz."
        )
        return

    status = await m.answer(f"🔎 Qidirilmoqda... ({len(queries)} ta model)")

    found, suggestions, not_found = await asyncio.to_thread(search_models, queries)

    if not found and not suggestions:
        await status.edit_text(
            "😕 Hech qanday model topilmadi.\n\n"
            "❌ <b>Topilmagan:</b>\n" + "\n".join(f"• {q}" for q in not_found)
        )
        return

    await status.delete()

    for query, fam in found.items():
        lines = [f"🔍 <b>{query}</b>"]
        for g in fam["groups"]:
            tag = "ASOSIY" if g["is_base"] else "qo'shimchali"
            asked = "  ← siz so'ragan" if g["is_asked"] else ""
            lines.append(f"\n<b>{g['model']}</b> <i>({tag})</i>{asked}")
            for r in g["rows"]:
                if r["store"].lower() == "ezviz":
                    p2 = round(r["price"] * (1 - EZVIZ_SECONDARY_DISCOUNT / 100), 2)
                    lines.append(f"  {r['store']}: {r['final']:.2f} $ / {p2:.2f} $")
                elif r["store"].lower() == "mus":
                    lines.append(f"  {r['store']}: {r['price']:.2f} $")
                else:
                    lines.append(f"  {r['store']}: {r['price']:.2f} → <b>{r['final']:.2f} $</b> (-{r['discount']:.0f}%)")
        text = "\n".join(lines)
        if len(text) > 3800:
            text = text[:3800] + "\n..."
        await m.answer(text)

    for query, names in suggestions.items():
        header = (
            f"🔗 <b>{query}</b> — o'xshash boshqa modellar (narxi boshqacha):"
            if query in found
            else f"🤔 <b>{query}</b> — aniq topilmadi.\nShulardan birini nazarda tutdingizmi?"
        )
        await m.answer(header + "\n\n" + "\n".join(f"• <code>{n}</code>" for n in names))

    if not_found:
        await m.answer(
            "❌ <b>Topilmagan modellar:</b>\n" + "\n".join(f"• {q}" for q in not_found)
        )
