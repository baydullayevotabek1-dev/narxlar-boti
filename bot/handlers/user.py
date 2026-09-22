import re
import asyncio
from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message

from ..search import search_models
from ..gemini import describe_model
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
    # split by newlines, commas, semicolons
    parts = re.split(r"[\n,;]+", text)
    out = []
    seen = set()
    for p in parts:
        p = p.strip()
        if not p:
            continue
        key = p.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


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

    # Render each found model as a separate message (or grouped)
    for query, results in found.items():
        header = f"🔍 <b>{query}</b>\n"
        blocks = [header]
        # AI description (once per query)
        first_desc = results[0].get("description") or ""
        ai_desc = ""
        if not first_desc or len(first_desc) < 5:
            try:
                ai_desc = await describe_model(query, first_desc)
            except Exception:
                ai_desc = ""

        # sort by final price ascending
        results.sort(key=lambda r: r["final"])

        for r in results:
            store = r['store']
            price = r['price']
            desc = r.get("description") or ""

            if store.lower() == "mus":
                # MUS: skidka yo'q, faqat narxlar
                block = (
                    f"\n📦 <b>MUS</b>\n"
                    f"  Narx: <b>{price:.2f} $</b> (skidka yo'q)"
                )
                if desc:
                    block += f"\n  ℹ️ {desc[:200]}"
            elif store.lower() == "ezviz":
                # Ezviz: -20% VA -15% ikkalasi alohida
                d1 = r['discount']  # 20
                d2 = EZVIZ_SECONDARY_DISCOUNT  # 15
                p1 = round(price * (1 - d1/100), 2)
                p2 = round(price * (1 - d2/100), 2)
                block = (
                    f"\n📦 <b>Ezviz</b> (Hilok)\n"
                    f"  Diler narxi: <b>{price:.2f} $</b>\n"
                    f"  Variant 1 (-{d1:.0f}%): <b>{p1:.2f} $</b>\n"
                    f"  Variant 2 (-{d2:.0f}%): <b>{p2:.2f} $</b>"
                )
                if desc:
                    block += f"\n  ℹ️ {desc[:120]}"
            else:
                block = (
                    f"\n📦 <b>{store}</b>\n"
                    f"  Asl narx: <b>{price:.2f} $</b>\n"
                    f"  Skidka: <b>-{r['discount']:.0f}%</b>\n"
                    f"  Siz uchun: <b>{r['final']:.2f} $</b>"
                )
                if desc:
                    block += f"\n  ℹ️ {desc[:120]}"
            blocks.append(block)

        if ai_desc:
            blocks.append(f"\n🤖 <i>{ai_desc}</i>")

        text = "".join(blocks)
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
