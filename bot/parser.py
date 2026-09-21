import pandas as pd
import re

MODEL_COLS = ["model", "модель", "модел", "nomi", "nom", "название", "наименование",
              "артикул", "artikul", "code", "kod", "товар", "product", "mahsulot"]
PRICE_COLS = ["price", "narx", "цена", "стоимость", "usd", "$", "sum", "so'm", "som",
              "дилер", "diller", "diler"]
DESC_COLS = ["opisanie", "описание", "xususiyat", "xarakteristika", "характеристика",
             "description", "desc", "izoh", "note", "примечание"]
# Additional price columns for MUS (filial, hamkor)
EXTRA_PRICE_COLS = ["filial", "филиал", "hamkor", "партнер", "партнёр", "partner",
                    "оптом", "opt", "розниц", "roznits", "vip", "diller", "дилер"]


def _norm_col(c: str) -> str:
    return re.sub(r"\s+", " ", str(c).strip().lower())


def _match(col: str, candidates: list[str]) -> bool:
    n = _norm_col(col)
    return any(cand in n for cand in candidates)


def _parse_price(v) -> float | None:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    s = str(v).strip()
    if not s:
        return None
    # keep digits, dot, comma, minus
    s = re.sub(r"[^\d,.\-]", "", s)
    s = s.replace(" ", "")
    if s.count(",") and s.count("."):
        # both — assume comma thousands
        s = s.replace(",", "")
    else:
        s = s.replace(",", ".")
    try:
        v = float(s)
        return v if v > 0 else None
    except ValueError:
        return None


def parse_excel(file_bytes: bytes) -> list[dict]:
    """Parse Excel and return list of {model, price, description}."""
    import io
    items = []
    xls = pd.ExcelFile(io.BytesIO(file_bytes))
    for sheet in xls.sheet_names:
        try:
            df = pd.read_excel(xls, sheet_name=sheet, header=None, dtype=str)
        except Exception:
            continue
        if df.empty:
            continue
        # try to find header row within first 10 rows
        header_row = None
        for i in range(min(10, len(df))):
            row_vals = [_norm_col(v) for v in df.iloc[i].fillna("").tolist()]
            has_model = any(_match(v, MODEL_COLS) for v in row_vals)
            has_price = any(_match(v, PRICE_COLS) for v in row_vals)
            if has_model and has_price:
                header_row = i
                break
        if header_row is None:
            continue
        header = df.iloc[header_row].fillna("").tolist()
        body = df.iloc[header_row + 1:].reset_index(drop=True)
        body.columns = list(range(len(header)))

        # find column indices
        model_idx = price_idx = desc_idx = None
        extra_price_cols: list[tuple[int, str]] = []  # (col_idx, label)
        for j, h in enumerate(header):
            h_str = str(h).strip()
            if model_idx is None and _match(h_str, MODEL_COLS):
                model_idx = j
            elif price_idx is None and _match(h_str, PRICE_COLS):
                price_idx = j
            elif desc_idx is None and _match(h_str, DESC_COLS):
                desc_idx = j
            elif _match(h_str, EXTRA_PRICE_COLS):
                extra_price_cols.append((j, h_str))
        if model_idx is None or price_idx is None:
            continue

        for _, row in body.iterrows():
            try:
                model = row[model_idx]
            except (KeyError, IndexError):
                continue
            if pd.isna(model) or not str(model).strip():
                continue
            price = _parse_price(row[price_idx] if price_idx < len(row) else None)
            if price is None:
                continue
            desc_parts = []
            if desc_idx is not None and desc_idx < len(row):
                d = row[desc_idx]
                if not pd.isna(d):
                    desc_parts.append(str(d).strip())
            # extra prices → append to description
            for eidx, label in extra_price_cols:
                if eidx >= len(row):
                    continue
                ep = _parse_price(row[eidx])
                if ep is not None:
                    desc_parts.append(f"{label}: {ep}")
            items.append({
                "model": str(model).strip(),
                "price": price,
                "description": " | ".join(desc_parts)[:300],
            })
    return items
