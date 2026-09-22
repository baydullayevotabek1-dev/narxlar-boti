import re

from rapidfuzz import fuzz, process
from .database import all_products, normalize
from .config import FUZZY_THRESHOLD

# A suffix that is nothing but parenthesised tags — "(D)", "(STD)(C)", "(O-STD)" —
# marks the same product in different packaging, so its price answers the query.
# Anything else ("/VPRO", "/8P", "-P") is a different SKU at a different price.
_PACKAGING_SUFFIX = re.compile(r"^(\s*\([^)]*\))+\s*$")


def _raw_suffix(model: str, qn: str) -> str | None:
    """
    Walk `model` consuming its alphanumerics against normalized query `qn`.
    Returns the leftover raw tail, "" for an exact match, or None if it diverges.
    """
    i = 0
    for pos, ch in enumerate(model):
        if i == len(qn):
            return model[pos:]
        if ch.isalnum():
            if ch.lower() != qn[i]:
                return None
            i += 1
    return "" if i == len(qn) else None


def _is_packaging_variant(model: str, qn: str) -> bool:
    suffix = _raw_suffix(model, qn)
    return bool(suffix) and bool(_PACKAGING_SUFFIX.match(suffix))


def _dedupe(names: list[str]) -> list[str]:
    seen = set()
    out = []
    for n in names:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out


def search_models(queries: list[str]) -> tuple[dict, dict, list[str]]:
    """
    Returns (found, suggestions, not_found).

    found:       {query: [{store, model, price, discount, final, description, match_kind}]}
                 Only confident matches — the exact model or a variant of it
                 (same code plus a packaging suffix). Prices here are safe to quote.
    suggestions: {query: [model_name, ...]} — close but different products.
                 Shown as "did you mean?" instead of prices, so a near-miss can
                 never be mistaken for the real answer.
    not_found:   queries with nothing resembling a match.
    """
    products = all_products()
    if not products:
        return {}, {}, list(queries)

    # index: model_norm -> list of product dicts
    norm_map: dict[str, list[dict]] = {}
    for p in products:
        norm_map.setdefault(p["model_norm"], []).append(p)
    norm_keys = list(norm_map.keys())

    found: dict[str, list[dict]] = {}
    suggestions: dict[str, list[str]] = {}
    not_found: list[str] = []

    for q in queries:
        q_clean = q.strip()
        if not q_clean:
            continue
        qn = normalize(q_clean)
        matches: list[dict] = []
        seen_stores = set()

        def take(norm_key: str, kind: str):
            for p in norm_map.get(norm_key, []):
                if p["store"] in seen_stores:
                    continue
                matches.append({**p, "match_kind": kind})
                seen_stores.add(p["store"])

        # 1) exact normalized match — ALL stores that have the model exactly
        if qn in norm_map:
            take(qn, "exact")

        # 2) same code plus a suffix. Two kinds, both priced but labelled apart:
        #    "(D)", "(STD)(C)"  -> packaging only, same product
        #    "/VPRO", "/8P", "-P" -> a different spec at a different price, so the
        #    row must say so rather than read as the plain model's price.
        #    Packaging first, shortest suffix first, so the closest match wins the store.
        prefixed = sorted((k for k in norm_keys if k != qn and k.startswith(qn)), key=len)
        packaging = [k for k in prefixed if any(_is_packaging_variant(p["model"], qn) for p in norm_map[k])]
        other = [k for k in prefixed if k not in packaging]
        for key in packaging:
            take(key, "variant")
        for key in other:
            take(key, "other")

        # Family members that lost their store to a closer match — worth a chip.
        near_misses = [p["model"] for k in other for p in norm_map[k]]

        if matches:
            result_list = []
            for p in matches:
                disc = float(p["discount"])
                final = round(p["price"] * (1 - disc / 100), 2)
                result_list.append({
                    "store": p["store"],
                    "model": p["model"],
                    "price": p["price"],
                    "discount": disc,
                    "final": final,
                    "description": p.get("description", "") or "",
                    "match_kind": p["match_kind"],
                })
            found[q_clean] = result_list
            shown = {p["model"] for p in matches}
            extra = [n for n in _dedupe(near_misses) if n not in shown]
            if extra:
                suggestions[q_clean] = extra[:8]
            continue

        # 3) no confident match — offer close model names to pick from instead
        #    of quoting the price of a product the user did not ask for.
        close = process.extract(
            qn, norm_keys, scorer=fuzz.WRatio, limit=20, score_cutoff=FUZZY_THRESHOLD
        )
        names: list[str] = list(near_misses)
        for norm_key, _score, _ in close:
            names.extend(p["model"] for p in norm_map[norm_key])
            if len(names) >= 8:
                break

        names = _dedupe(names)
        if names:
            suggestions[q_clean] = names[:8]
        else:
            not_found.append(q_clean)

    return found, suggestions, not_found
