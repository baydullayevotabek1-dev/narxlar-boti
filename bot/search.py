import re

from rapidfuzz import fuzz, process
from .database import all_products, normalize
from .config import FUZZY_THRESHOLD

# Split model lists on newlines and semicolons, and on commas — except a comma
# sitting between two digits, which is a decimal point in a lens size ("2,8MM").
_SPLIT = re.compile(r"[\n;]+|(?<!\d),|,(?!\d)")

MAX_VARIANTS = 30


def split_query(text: str) -> list[str]:
    out, seen = [], set()
    for part in _SPLIT.split(text):
        part = (part or "").strip()
        if part and part.lower() not in seen:
            seen.add(part.lower())
            out.append(part)
    return out


def _price_row(p: dict) -> dict:
    disc = float(p["discount"])
    return {
        "store": p["store"],
        "price": p["price"],
        "discount": disc,
        "final": round(p["price"] * (1 - disc / 100), 2),
        "description": p.get("description", "") or "",
        "is_override": bool(p.get("is_override")),
        "file_price": p.get("file_price"),
    }


def search_models(queries: list[str]) -> tuple[dict, dict, list[str]]:
    """
    Returns (found, suggestions, not_found).

    found maps each query to its whole product family:
        {query: {"base": "DS-2CD1043G2-I",
                 "truncated": False,
                 "groups": [{"model", "is_base", "is_asked", "rows": [...]}]}}

    The family is every stored model sharing the base code, so a manager who
    types one spelling still sees the plain model and every suffixed variant
    ("2,8MM", "(STD)", "/VPRO") side by side, each with its own prices.

    suggestions: {query: [model_name, ...]} when nothing in the family matched.
    not_found:   queries with nothing resembling a match.
    """
    products = all_products()
    if not products:
        return {}, {}, list(queries)

    norm_map: dict[str, list[dict]] = {}
    for p in products:
        norm_map.setdefault(p["model_norm"], []).append(p)
    norm_keys = list(norm_map.keys())

    found: dict[str, dict] = {}
    suggestions: dict[str, list[str]] = {}
    not_found: list[str] = []

    for q in queries:
        q_clean = q.strip()
        if not q_clean:
            continue
        qn = normalize(q_clean)

        # The base is the shortest stored model the query builds on — searching
        # "DS-2CD1043G2-I 2,8MM" must still surface plain "DS-2CD1043G2-I".
        prefixes = [k for k in norm_keys if qn.startswith(k)]
        base_norm = min(prefixes, key=len) if prefixes else qn

        # Base first, then what the manager actually typed, then the rest.
        family = sorted(
            (k for k in norm_keys if k.startswith(base_norm)),
            key=lambda k: (k != base_norm, k != qn, len(k), k),
        )

        if not family:
            close = process.extract(
                qn, norm_keys, scorer=fuzz.WRatio, limit=20, score_cutoff=FUZZY_THRESHOLD
            )
            names: list[str] = []
            for norm_key, _score, _ in close:
                for p in norm_map[norm_key]:
                    if p["model"] not in names:
                        names.append(p["model"])
                if len(names) >= 8:
                    break
            if names:
                suggestions[q_clean] = names[:8]
            else:
                not_found.append(q_clean)
            continue

        groups = []
        for key in family[:MAX_VARIANTS]:
            prods = norm_map[key]
            rows, seen_stores = [], set()
            for p in prods:
                if p["store"] in seen_stores:
                    continue
                seen_stores.add(p["store"])
                rows.append(_price_row(p))
            rows.sort(key=lambda r: r["final"])
            groups.append({
                "model": prods[0]["model"],
                "is_base": key == base_norm,
                "is_asked": key == qn,
                "rows": rows,
            })

        found[q_clean] = {
            "base": norm_map[base_norm][0]["model"] if base_norm in norm_map else q_clean,
            "truncated": len(family) > MAX_VARIANTS,
            "groups": groups,
        }

    return found, suggestions, not_found
