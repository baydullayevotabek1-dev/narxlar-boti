import asyncio
import logging
import google.generativeai as genai
from .config import GEMINI_API_KEY
from .database import get_ai_cache, cache_ai, normalize

log = logging.getLogger(__name__)

_configured = False


def _ensure():
    global _configured
    if not _configured and GEMINI_API_KEY:
        try:
            genai.configure(api_key=GEMINI_API_KEY)
            _configured = True
        except Exception as e:
            log.error(f"Gemini configure error: {e}")


async def describe_model(model_name: str, existing_desc: str = "") -> str:
    """Return short 1-line description of the product model."""
    if existing_desc and len(existing_desc) > 5:
        return existing_desc[:200]

    norm = normalize(model_name)
    cached = get_ai_cache(norm)
    if cached:
        return cached

    if not GEMINI_API_KEY:
        return ""

    _ensure()
    if not _configured:
        return ""

    prompt = (
        f"Mahsulot modeli: {model_name}\n"
        "Bu mahsulotning qisqa (1 qator, 100 belgigacha) texnik xususiyatini o'zbek tilida yoz. "
        "Faqat asosiy parametrlarni ayt (masalan: 8-kanalli NVR, H.265+, 8MP kamera). "
        "Agar mahsulot nomidan aniqlab bo'lmasa, 'Ma\\'lumot yo\\'q' deb yoz. "
        "Faqat tavsifni yoz, boshqa hech narsa yozma."
    )

    def _call():
        try:
            model = genai.GenerativeModel("gemini-flash-latest")
            resp = model.generate_content(prompt)
            return (resp.text or "").strip()
        except Exception as e:
            log.warning(f"Gemini error for '{model_name}': {e}")
            return ""

    try:
        text = await asyncio.wait_for(asyncio.to_thread(_call), timeout=15)
    except asyncio.TimeoutError:
        text = ""

    if text and "ma'lumot yo'q" not in text.lower() and "malumot yoq" not in text.lower():
        text = text.replace("\n", " ").strip()[:200]
        cache_ai(norm, text)
        return text
    return ""
