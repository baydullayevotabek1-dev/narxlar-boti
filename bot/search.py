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

        # exact norm match — ALL stores that have the model exactly
        if qn in norm_map:
            for p in norm_map[qn]:
                if p["store"] in seen_stores:
                    continue
                matches.append(p)
                seen_stores.add(p["store"])

        # fuzzy match — find variants in stores that don't have exact match
        fuzz_results = process.extract(
            qn, norm_keys, scorer=fuzz.WRatio, limit=30, score_cutoff=FUZZY_THRESHOLD
        )
        for norm_key, score, _ in fuzz_results:
            for p in norm_map[norm_key]:
                if p["store"] in seen_stores:
                    continue
                matches.append(p)
                seen_stores.add(p["store"])

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
                })
            found[q_clean] = result_list
        else:
            not_found.append(q_clean)

    return found, not_found
