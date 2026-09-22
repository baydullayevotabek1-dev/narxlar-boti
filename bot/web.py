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
from .database import list_stores, set_discount, replace_products, stats
from .parser import parse_excel
from .search import search_models
from .store_detect import detect_store
from .url_download import download_url

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
    rows = list_stores()
    return web.json_response(rows)


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

    # Format results with Ezviz two-discount handling
    formatted = {}
    for q, results in found.items():
        out = []
        for r in results:
            store = r["store"]
            price = r["price"]
            if store.lower() == "ezviz":
                out.append({
                    "store": store,
                    "price": price,
                    "discount_label": f"-20% / -15%",
                    "final": round(price * 0.80, 2),
                    "final2": round(price * (1 - EZVIZ_SECONDARY_DISCOUNT / 100), 2),
                    "description": r.get("description", ""),
                    "special": "ezviz",
                })
            elif store.lower() == "mus":
                out.append({
                    "store": store,
                    "price": price,
                    "discount_label": "—",
                    "final": price,
                    "description": r.get("description", ""),
                    "special": "mus",
                })
            else:
                out.append({
                    "store": store,
                    "price": price,
                    "discount_label": f"-{r['discount']:.0f}%",
                    "final": r["final"],
                    "description": r.get("description", ""),
                    "special": None,
                })
        formatted[q] = out

    return web.json_response({"found": formatted, "not_found": not_found})


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
    app.router.add_get("/health", health)
