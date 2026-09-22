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

        # 2) packaging variant — "DS-7608NI-Q1" -> "DS-7608NI-Q1(STD)(C)".
        #    Prefix-only is not enough: "DS-7608NXI-K2/VPRO" also starts with
        #    "DS-7608NXI-K2" but is a pricier product, so it stays a suggestion.
        prefixed = sorted((k for k in norm_keys if k != qn and k.startswith(qn)), key=len)
        near_misses: list[str] = []
        for key in prefixed:
            if any(_is_packaging_variant(p["model"], qn) for p in norm_map[key]):
                take(key, "variant")
            else:
                near_misses.extend(p["model"] for p in norm_map[key])

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
            # Related SKUs like "/VPRO" are still worth surfacing, just not priced
            # as if they were the answer.
            if near_misses:
                suggestions[q_clean] = _dedupe(near_misses)[:8]
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
