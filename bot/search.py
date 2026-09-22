from rapidfuzz import fuzz, process
from .database import all_products, normalize
from .config import FUZZY_THRESHOLD


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

        # 2) variant match — stored model is the query plus a suffix, e.g.
        #    query "DS-7608NI-Q1" -> "DS-7608NI-Q1(STD)(C)". Same product,
        #    different packaging. Shortest suffix first = closest variant.
        for key in sorted((k for k in norm_keys if k != qn and k.startswith(qn)), key=len):
            take(key, "variant")

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
            continue

        # 3) no confident match — offer close model names to pick from instead
        #    of quoting the price of a product the user did not ask for.
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

    return found, suggestions, not_found
