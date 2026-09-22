from rapidfuzz import fuzz, process
from .database import all_products, normalize
from .config import FUZZY_THRESHOLD


def search_models(queries: list[str]) -> tuple[dict, list[str]]:
    """
    Returns (found, not_found).
    found: {query: [{store, model, price, discount, final, description}, ...]}
    """
    products = all_products()
    if not products:
        return {}, list(queries)

    # index: model_norm -> list of product dicts
    norm_map: dict[str, list[dict]] = {}
    for p in products:
        norm_map.setdefault(p["model_norm"], []).append(p)
    norm_keys = list(norm_map.keys())

    found: dict[str, list[dict]] = {}
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
        #    query "DS-7608NI-Q1" -> "DS-7608NI-Q1(STD)(C)". Same product, different packaging.
        #    Sorted so the shortest suffix (closest variant) wins per store.
        variants = sorted(
            (k for k in norm_keys if k != qn and k.startswith(qn)),
            key=len,
        )
        for key in variants:
            take(key, "variant")

        # 3) fuzzy match — only for stores still unmatched, and only above a
        #    stricter bar, because a near-miss here means a DIFFERENT product.
        fuzz_results = process.extract(
            qn, norm_keys, scorer=fuzz.WRatio, limit=30, score_cutoff=FUZZY_THRESHOLD
        )
        for norm_key, score, _ in fuzz_results:
            take(norm_key, "fuzzy")

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
                    "match_kind": p.get("match_kind", "exact"),
                })
            found[q_clean] = result_list
        else:
            not_found.append(q_clean)

    return found, not_found
