"""Web panel — managers log in with common password, search prices, upload Excel."""
import asyncio
import hashlib
import hmac
import json
import logging
import time
from pathlib import Path

from aiohttp import web

from .config import SITE_PASSWORD, ADMIN_PASSWORD, SESSION_SECRET, EZVIZ_SECONDARY_DISCOUNT
from .database import (
    list_stores, set_discount, replace_products, stats, add_store, delete_store,
    log_search, suggest_models, stats_top_models, stats_cheapest_stores, stats_totals,
)
from .parser import parse_excel
from .search import search_models
from .store_detect import detect_store
from .url_download import download_url
from .gemini import describe_model

log = logging.getLogger(__name__)

SESSION_COOKIE = "narxlar_session"
SESSION_TTL = 7 * 24 * 3600  # 7 days

TEMPLATES_DIR = Path(__file__).parent / "templates"


def _sign(data: str) -> str:
    return hmac.new(SESSION_SECRET.encode(), data.encode(), hashlib.sha256).hexdigest()[:32]


def _make_session(role: str) -> str:
    """role: 'user' or 'admin'"""
    ts = str(int(time.time()))
    payload = f"{ts}.{role}"
    return f"{payload}.{_sign(payload)}"


def _session_role(token: str) -> str | None:
    """Return 'user', 'admin', or None if invalid/expired."""
    if not token or token.count(".") != 2:
        return None
    ts, role, sig = token.split(".", 2)
    if _sign(f"{ts}.{role}") != sig:
        return None
    if role not in ("user", "admin"):
        return None
    try:
        if time.time() - int(ts) > SESSION_TTL:
            return None
    except ValueError:
        return None
    return role


def _current_role(request: web.Request) -> str | None:
    return _session_role(request.cookies.get(SESSION_COOKIE, ""))


def _is_logged_in(request: web.Request) -> bool:
    return _current_role(request) is not None


def _is_admin(request: web.Request) -> bool:
    return _current_role(request) == "admin"


def _render(name: str, **ctx) -> str:
    tpl = (TEMPLATES_DIR / name).read_text(encoding="utf-8")
    for k, v in ctx.items():
        tpl = tpl.replace("{{" + k + "}}", str(v))
    return tpl


async def page_login(request: web.Request):
    if _is_logged_in(request):
        raise web.HTTPFound("/panel")
    err = request.query.get("err", "")
    err_html = '<div class="err">Parol xato</div>' if err else ""
    html = _render("login.html", ERROR=err_html)
    return web.Response(text=html, content_type="text/html")


async def api_login(request: web.Request):
    data = await request.post()
    password = (data.get("password") or "").strip()
    if password == ADMIN_PASSWORD:
        role = "admin"
    elif password == SITE_PASSWORD:
        role = "user"
    else:
        raise web.HTTPFound("/?err=1")
    resp = web.HTTPFound("/panel")
    resp.set_cookie(SESSION_COOKIE, _make_session(role), max_age=SESSION_TTL, httponly=True, samesite="Lax")
    raise resp


async def api_logout(request: web.Request):
    resp = web.HTTPFound("/")
    resp.del_cookie(SESSION_COOKIE)
    raise resp


async def page_panel(request: web.Request):
    role = _current_role(request)
    if not role:
        raise web.HTTPFound("/")
    role_html = (
        '<span class="role-admin">🛠 Admin</span>' if role == "admin"
        else '<span class="role-user">👤 Menejer</span>'
    )
    is_admin_json = "true" if role == "admin" else "false"
    html = _render("panel.html", ROLE_BADGE=role_html, IS_ADMIN=is_admin_json)
    return web.Response(text=html, content_type="text/html")


def _require_auth(request: web.Request):
    if not _is_logged_in(request):
        raise web.HTTPUnauthorized(text="Login kerak")


def _require_admin(request: web.Request):
    if not _is_admin(request):
        raise web.HTTPForbidden(text="Faqat admin uchun")


async def api_stores(request: web.Request):
    _require_auth(request)
    import datetime
    rows = list_stores()
    for r in rows:
        ts = r.get("updated_at") or 0
        if ts:
            dt = datetime.datetime.fromtimestamp(ts)
            r["updated_str"] = dt.strftime("%d.%m.%Y %H:%M")
        else:
            r["updated_str"] = ""
    return web.json_response(rows)


async def api_add_store(request: web.Request):
    _require_admin(request)
    data = await request.json()
    name = (data.get("name") or "").strip()
    try:
        discount = float(data.get("discount", 0))
    except (TypeError, ValueError):
        return web.json_response({"error": "Skidka raqam bo'lishi kerak"}, status=400)
    if not name or len(name) > 50:
        return web.json_response({"error": "Do'kon nomi noto'g'ri"}, status=400)
    if discount < 0 or discount > 99:
        return web.json_response({"error": "Skidka 0-99 oralig'ida"}, status=400)
    ok = add_store(name, discount)
    if not ok:
        return web.json_response({"error": f"'{name}' allaqachon mavjud"}, status=400)
    return web.json_response({"ok": True, "store": name, "discount": discount})


async def api_delete_store(request: web.Request):
    _require_admin(request)
    data = await request.json()
    name = (data.get("name") or "").strip()
    if not name:
        return web.json_response({"error": "Nomi kerak"}, status=400)
    delete_store(name)
    return web.json_response({"ok": True})


async def api_search(request: web.Request):
    _require_auth(request)
    data = await request.json()
    query = (data.get("query") or "").strip()
    if not query:
        return web.json_response({"found": {}, "not_found": []})
    import re
    parts = re.split(r"[\n,;]+", query)
    queries = []
    seen = set()
    for p in parts:
        p = p.strip()
        if p and p.lower() not in seen:
            seen.add(p.lower())
            queries.append(p)
    if len(queries) > 60:
        return web.json_response({"error": "Max 60 ta model"})
    found, not_found = await asyncio.to_thread(search_models, queries)

    # Log each query with cheapest store
    for q in queries:
        results = found.get(q, [])
        cheapest = ""
        if results:
            min_r = min(results, key=lambda r: r["final"])
            cheapest = min_r["store"]
        await asyncio.to_thread(log_search, q, len(results), cheapest)

    # Format results with Ezviz two-discount handling + AI descriptions
    formatted = {}
    ai_descriptions = {}
    ai_tasks = []
    for q, results in found.items():
        # kick off AI description in parallel (uses cache if available)
        existing_desc = results[0].get("description", "") if results else ""
        ai_tasks.append((q, asyncio.create_task(describe_model(q, existing_desc))))

    for q, task in ai_tasks:
        try:
            ai_descriptions[q] = await task
        except Exception:
            ai_descriptions[q] = ""

    for q, results in found.items():
        out = []
        # Compute cheapest final price for badge
        min_final = min((r["final"] for r in results), default=None)
        for r in results:
            store = r["store"]
            price = r["price"]
            is_best = min_final is not None and abs(r["final"] - min_final) < 0.01
            common = {
                "store": store,
                "price": price,
                "description": r.get("description", ""),
                "is_best": is_best,
                "matched_model": r.get("model", ""),
                "match_kind": r.get("match_kind", "exact"),
            }
            if store.lower() == "ezviz":
                out.append({
                    **common,
                    "discount_label": "-20% / -15%",
                    "final": round(price * 0.80, 2),
                    "final2": round(price * (1 - EZVIZ_SECONDARY_DISCOUNT / 100), 2),
                    "special": "ezviz",
                })
            elif store.lower() == "mus":
                out.append({
                    **common,
                    "discount_label": "—",
                    "final": price,
                    "special": "mus",
                })
            else:
                out.append({
                    **common,
                    "discount_label": f"-{r['discount']:.0f}%",
                    "final": r["final"],
                    "special": None,
                })
        formatted[q] = out

    return web.json_response({"found": formatted, "ai": ai_descriptions, "not_found": not_found})


async def api_upload(request: web.Request):
    _require_admin(request)
    reader = await request.multipart()
    store = None
    filename = ""
    file_bytes = bytearray()

    async for field in reader:
        if field.name == "store":
            store = (await field.text()).strip()
        elif field.name == "file":
            filename = field.filename or "upload.xlsx"
            while True:
                chunk = await field.read_chunk(65536)
                if not chunk:
                    break
                file_bytes.extend(chunk)
                if len(file_bytes) > 500 * 1024 * 1024:
                    return web.json_response({"error": "Fayl 500 MB dan katta"}, status=400)

    if not store or not file_bytes:
        return web.json_response({"error": "store va fayl kerak"}, status=400)

    if not filename.lower().endswith((".xlsx", ".xls", ".xlsm")):
        return web.json_response({"error": "Faqat Excel fayl"}, status=400)

    try:
        items = await asyncio.to_thread(parse_excel, bytes(file_bytes))
    except Exception as e:
        return web.json_response({"error": f"Excel o'qishda xato: {e}"}, status=400)

    if not items:
        return web.json_response({"error": "Mahsulot topilmadi. Ustunlarda Model va Narx bo'lishi kerak."}, status=400)

    replace_products(store, items)
    return web.json_response({
        "ok": True, "store": store, "filename": filename,
        "count": len(items), "size_mb": round(len(file_bytes) / 1024 / 1024, 2)
    })


async def api_upload_url(request: web.Request):
    _require_admin(request)
    data = await request.json()
    store = (data.get("store") or "").strip()
    url = (data.get("url") or "").strip()
    if not store or not url:
        return web.json_response({"error": "store va url kerak"}, status=400)

    try:
        raw, filename = await download_url(url)
    except Exception as e:
        return web.json_response({"error": f"URL yuklashda xato: {e}"}, status=400)

    try:
        items = await asyncio.to_thread(parse_excel, raw)
    except Exception as e:
        return web.json_response({"error": f"Excel o'qishda xato: {e}"}, status=400)

    if not items:
        return web.json_response({"error": "Mahsulot topilmadi"}, status=400)

    replace_products(store, items)
    return web.json_response({
        "ok": True, "store": store, "filename": filename,
        "count": len(items), "size_mb": round(len(raw) / 1024 / 1024, 2)
    })


async def api_set_discount(request: web.Request):
    _require_admin(request)
    data = await request.json()
    store = (data.get("store") or "").strip()
    try:
        discount = float(data.get("discount", 0))
    except (TypeError, ValueError):
        return web.json_response({"error": "discount raqam bo'lishi kerak"}, status=400)
    set_discount(store, discount)
    return web.json_response({"ok": True})


async def api_suggest(request: web.Request):
    _require_auth(request)
    q = request.query.get("q", "").strip()
    suggestions = await asyncio.to_thread(suggest_models, q, 10)
    return web.json_response(suggestions)


async def api_stats(request: web.Request):
    _require_admin(request)
    totals = stats_totals()
    top = stats_top_models(20)
    cheapest = stats_cheapest_stores()
    total_products, by_store = stats()
    return web.json_response({
        "searches": totals,
        "top_models": top,
        "cheapest_stores": cheapest,
        "total_products": total_products,
        "products_by_store": by_store,
    })


async def page_stats(request: web.Request):
    if not _is_admin(request):
        raise web.HTTPFound("/panel")
    html = _render("stats.html")
    return web.Response(text=html, content_type="text/html")


async def health(request):
    return web.Response(text="OK")


def register_routes(app: web.Application):
    app.router.add_get("/", page_login)
    app.router.add_post("/login", api_login)
    app.router.add_get("/logout", api_logout)
    app.router.add_get("/panel", page_panel)
    app.router.add_get("/api/stores", api_stores)
    app.router.add_post("/api/search", api_search)
    app.router.add_post("/api/upload", api_upload)
    app.router.add_post("/api/upload_url", api_upload_url)
    app.router.add_post("/api/set_discount", api_set_discount)
    app.router.add_post("/api/add_store", api_add_store)
    app.router.add_post("/api/delete_store", api_delete_store)
    app.router.add_get("/api/suggest", api_suggest)
    app.router.add_get("/api/stats", api_stats)
    app.router.add_get("/stats", page_stats)
    app.router.add_get("/health", health)
