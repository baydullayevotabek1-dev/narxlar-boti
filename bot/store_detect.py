"""Detect store name from Excel filename."""

# Order matters: check more specific keywords first
STORE_KEYWORDS = [
    ("SystemService", ["system service", "systemservice", "vip system", "system-service"]),
    ("Darian",        ["darian"]),
    ("Ezviz",         ["ezviz"]),
    ("Hilok",         ["hilook", "hilok", "hikvision"]),  # Hikvision price → Hilok per TZ
    ("KSS",           ["kss"]),
    ("MUS",           ["mus prays", "mus_prays", "mus price", "mus"]),
]


def detect_store(filename: str) -> str | None:
    name = filename.lower()
    for store, keywords in STORE_KEYWORDS:
        for kw in keywords:
            if kw in name:
                return store
    return None
