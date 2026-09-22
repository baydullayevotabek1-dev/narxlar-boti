import sqlite3
import os
from contextlib import contextmanager
from .config import DB_PATH, DEFAULT_STORES


def init_db():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    with get_conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS stores (
                name TEXT PRIMARY KEY,
                discount REAL NOT NULL DEFAULT 0,
                updated_at INTEGER DEFAULT 0
            )
        """)
        # Migration: add updated_at if missing (existing DBs)
        cols = [r[1] for r in c.execute("PRAGMA table_info(stores)").fetchall()]
        if "updated_at" not in cols:
            c.execute("ALTER TABLE stores ADD COLUMN updated_at INTEGER DEFAULT 0")
        c.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                store TEXT NOT NULL,
                model TEXT NOT NULL,
                model_norm TEXT NOT NULL,
                price REAL NOT NULL,
                description TEXT DEFAULT '',
                FOREIGN KEY(store) REFERENCES stores(name) ON DELETE CASCADE
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_products_store ON products(store)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_products_norm ON products(model_norm)")
        c.execute("""
            CREATE TABLE IF NOT EXISTS ai_cache (
                model_norm TEXT PRIMARY KEY,
                description TEXT NOT NULL,
                created_at INTEGER NOT NULL
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS search_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                query TEXT NOT NULL,
                query_norm TEXT NOT NULL,
                found INTEGER NOT NULL DEFAULT 0,
                cheapest_store TEXT DEFAULT '',
                created_at INTEGER NOT NULL
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_log_norm ON search_log(query_norm)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_log_created ON search_log(created_at)")
        for name, disc in DEFAULT_STORES.items():
            c.execute(
                "INSERT OR IGNORE INTO stores(name, discount) VALUES(?, ?)",
                (name, disc),
            )


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def normalize(s: str) -> str:
    return "".join(ch.lower() for ch in str(s) if ch.isalnum())


def list_stores():
    with get_conn() as c:
        rows = c.execute(
            "SELECT s.name, s.discount, s.updated_at, "
            "(SELECT COUNT(*) FROM products p WHERE p.store=s.name) AS cnt "
            "FROM stores s ORDER BY s.name"
        ).fetchall()
        return [dict(r) for r in rows]


def get_store(name: str):
    with get_conn() as c:
        r = c.execute("SELECT * FROM stores WHERE lower(name)=lower(?)", (name,)).fetchone()
        return dict(r) if r else None


def set_discount(name: str, discount: float) -> bool:
    with get_conn() as c:
        cur = c.execute(
            "UPDATE stores SET discount=? WHERE lower(name)=lower(?)",
            (discount, name),
        )
        if cur.rowcount == 0:
            c.execute("INSERT INTO stores(name, discount) VALUES(?, ?)", (name, discount))
        return True


def replace_products(store: str, items: list[dict]):
    """items: [{model, price, description}]"""
    import time
    now = int(time.time())
    with get_conn() as c:
        # Reuse existing store row (case-insensitive) so its discount is never reset
        existing = c.execute(
            "SELECT name FROM stores WHERE lower(name)=lower(?)", (store,)
        ).fetchone()
        if existing:
            store = existing["name"]
        else:
            c.execute("INSERT INTO stores(name, discount) VALUES(?, 0)", (store,))
        c.execute("DELETE FROM products WHERE lower(store)=lower(?)", (store,))
        c.executemany(
            "INSERT INTO products(store, model, model_norm, price, description) VALUES(?,?,?,?,?)",
            [
                (
                    store,
                    it["model"],
                    normalize(it["model"]),
                    float(it["price"]),
                    it.get("description", "") or "",
                )
                for it in items
            ],
        )
        c.execute("UPDATE stores SET updated_at=? WHERE lower(name)=lower(?)", (now, store))


def add_store(name: str, discount: float) -> bool:
    """Add a new store. Returns False if already exists."""
    with get_conn() as c:
        try:
            c.execute("INSERT INTO stores(name, discount, updated_at) VALUES(?, ?, 0)", (name, discount))
            return True
        except sqlite3.IntegrityError:
            return False


def delete_store(name: str):
    with get_conn() as c:
        c.execute("DELETE FROM stores WHERE lower(name)=lower(?)", (name,))
        c.execute("DELETE FROM products WHERE lower(store)=lower(?)", (name,))


def all_products():
    with get_conn() as c:
        rows = c.execute(
            "SELECT p.*, s.discount FROM products p JOIN stores s ON lower(s.name)=lower(p.store)"
        ).fetchall()
        return [dict(r) for r in rows]


def stats():
    with get_conn() as c:
        total = c.execute("SELECT COUNT(*) AS n FROM products").fetchone()["n"]
        by_store = c.execute(
            "SELECT store, COUNT(*) AS n FROM products GROUP BY store"
        ).fetchall()
        return total, [dict(r) for r in by_store]


def cache_ai(model_norm: str, desc: str):
    import time
    with get_conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO ai_cache(model_norm, description, created_at) VALUES(?,?,?)",
            (model_norm, desc, int(time.time())),
        )


def get_ai_cache(model_norm: str) -> str | None:
    with get_conn() as c:
        r = c.execute("SELECT description FROM ai_cache WHERE model_norm=?", (model_norm,)).fetchone()
        return r["description"] if r else None


def log_search(query: str, found: int, cheapest_store: str = ""):
    import time
    with get_conn() as c:
        c.execute(
            "INSERT INTO search_log(query, query_norm, found, cheapest_store, created_at) VALUES(?,?,?,?,?)",
            (query, normalize(query), found, cheapest_store, int(time.time())),
        )


def suggest_models(prefix: str, limit: int = 10) -> list[str]:
    """Autocomplete: return top N distinct model names matching prefix."""
    prefix_norm = normalize(prefix)
    if len(prefix_norm) < 2:
        return []
    with get_conn() as c:
        rows = c.execute(
            "SELECT DISTINCT model FROM products WHERE model_norm LIKE ? ORDER BY model LIMIT ?",
            (prefix_norm + "%", limit),
        ).fetchall()
        return [r["model"] for r in rows]


def stats_top_models(limit: int = 20) -> list[dict]:
    with get_conn() as c:
        rows = c.execute(
            "SELECT query, COUNT(*) AS n, SUM(found) AS total_found "
            "FROM search_log GROUP BY query_norm ORDER BY n DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def stats_cheapest_stores() -> list[dict]:
    with get_conn() as c:
        rows = c.execute(
            "SELECT cheapest_store, COUNT(*) AS n FROM search_log "
            "WHERE cheapest_store != '' GROUP BY cheapest_store ORDER BY n DESC"
        ).fetchall()
        return [dict(r) for r in rows]


def stats_totals() -> dict:
    with get_conn() as c:
        r = c.execute("SELECT COUNT(*) AS total, SUM(found) AS found FROM search_log").fetchone()
        return {"total": r["total"] or 0, "found": r["found"] or 0}
