"""
Landing Processor — зеркало базы agr_base.xlsx
Парсит:
 - Столбец G -> Выручка 2025
 - Столбец H -> Чистая прибыль 2025
 - Столбец J -> EBITDA по отчету эмитента (col 10)
 - Столбец X -> Чистый долг (col 24)

Источники берутся из листа "Источники":
 - МСФО -> Выручка, Чистая прибыль
 - Отчет эмитента / Презентация -> EBITDA, Чистый долг

Скриншоты берутся из 03_Отчетность_и_скриншоты/<Компания>/evidence/
Кириллица обрабатывается корректно: пути хранятся в UTF-8, URL кодируются через quote,
 Slug для компании = ticker lower. Для файлов — сохраняем оригинальное имя, но отдаем через Flask endpoint /evidence/<slug>/<filename_encoded>
 Опционально можно создать ascii-зеркало для статики.
"""
import json
import re
import shutil
import urllib.parse
from pathlib import Path
from typing import Dict, List, Optional, Any

import openpyxl

BASE_DIR = Path(__file__).parent
XLSX_PATH = BASE_DIR / "baza_v2" / "01_base" / "agr_base.xlsx"
EVIDENCE_ROOT = BASE_DIR / "baza_v2" / "03_Отчетность_и_скриншоты"
DATA_DIR = BASE_DIR / "data"
OUTPUT_JSON = DATA_DIR / "landing_data.json"

# Транслитерация для slug папок (если решим делать ascii-копию)
CYR_TO_LAT = {
    'а':'a','б':'b','в':'v','г':'g','д':'d','е':'e','ё':'yo','ж':'zh','з':'z','и':'i','й':'y','к':'k','л':'l','м':'m','н':'n','о':'o','п':'p','р':'r','с':'s','т':'t','у':'u','ф':'f','х':'kh','ц':'ts','ч':'ch','ш':'sh','щ':'shch','ъ':'','ы':'y','ь':'','э':'e','ю':'yu','я':'ya',
    'А':'A','Б':'B','В':'V','Г':'G','Д':'D','Е':'E','Ё':'Yo','Ж':'Zh','З':'Z','И':'I','Й':'Y','К':'K','Л':'L','М':'M','Н':'N','О':'O','П':'P','Р':'R','С':'S','Т':'T','У':'U','Ф':'F','Х':'Kh','Ц':'Ts','Ч':'Ch','Ш':'Sh','Щ':'Shch','Э':'E','Ю':'Yu','Я':'Ya',
}
# Доп маппинг для папок с особенностями
FOLDER_ALIAS = {
    # folder_name -> company_display variant
}

def transliterate(text: str) -> str:
    out = ""
    for ch in text:
        if ch in CYR_TO_LAT:
            out += CYR_TO_LAT[ch]
        elif ch.isalnum() or ch in ("-", "_", " "):
            out += ch
        elif ch == " ":
            out += "_"
        else:
            out += "_"
    # sane slug
    out = re.sub(r"__+", "_", out)
    out = re.sub(r"[^a-zA-Z0-9_\-]", "", out)
    return out.lower()

def slugify_company(name: str, ticker: str) -> str:
    # primary slug = ticker lower; fallback transliterated name
    t = ticker.strip().lower() if ticker and ticker not in ("н.д.", "н.п.") else ""
    if t and re.match(r"^[a-z0-9\-]+$", t):
        return t
    return transliterate(name)

def is_missing(value: Any) -> bool:
    if value is None:
        return True
    s = str(value).strip().lower()
    return s in ("н.д.", "нд", "н.п.", "н.п", "н. п.", "н. д.", "-", "—", "", "none", "null")

def parse_numeric(value: Any) -> Optional[float]:
    if is_missing(value):
        return None
    try:
        if isinstance(value, (int, float)):
            return float(value)
        s = str(value).replace("\xa0", " ").replace(",", ".")
        # remove spaces
        s = s.replace(" ", "").replace(" ", "")
        # handle things like "н.д."
        if is_missing(s):
            return None
        return float(s)
    except:
        return None

def format_number(value: Optional[float], currency: str = "RUB") -> str:
    if value is None:
        return "н/д"
    # currency sign
    sign = "₽" if currency == "RUB" else "$" if currency == "USD" else currency
    # keep original unit: база в млн руб / млн USD
    # show compact: if abs >=1_000_000 then трлн, if >=1000 then млрд
    abs_v = abs(value)
    # value already in млн
    # For RUB: 3 767 768 млн = 3.77 трлн
    if abs_v >= 1_000_000:
        v = value / 1_000_000
        return f"{v:,.2f} трлн {sign}".replace(",", " ").replace(".", ",")
    if abs_v >= 1_000:
        v = value / 1_000
        return f"{v:,.1f} млрд {sign}".replace(",", " ").replace(".", ",")
    return f"{value:,.0f} млн {sign}".replace(",", " ")

def format_raw(value: Optional[float], currency: str = "RUB") -> str:
    if value is None:
        return "н/д"
    sign = "₽" if currency == "RUB" else "$" if currency == "USD" else currency
    # raw with spaces: 3 767 768 млн ₽
    # use formatting with spaces
    s = f"{value:,.0f}".replace(",", " ")
    return f"{s} млн {sign}"

# ---------- Evidence handling ----------

def collect_evidence_for_company(folder: Path, slug: str) -> List[Dict]:
    """Собирает скриншоты из evidence папки.
    Возвращает список словарей с ключами: filename, url, category
    category определяется по имени файла.
    """
    ev = folder / "evidence"
    if not ev.exists() or not ev.is_dir():
        return []
    files = []
    for p in sorted(ev.glob("*")):
        if p.is_file() and p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp", ".pdf"):
            name = p.name
            # category infer
            lower = name.lower()
            if "опу" in lower:
                cat = "opu"  # выручка/прибыль
            elif "баланс" in lower:
                cat = "balance"  # долг
            elif "оддс" in lower:
                cat = "cf"
            elif "ебитда" in lower or "ebitda" in lower:
                if "оэ" in lower or "oe" in lower or "эмитента" in lower:
                    cat = "ebitda_oe"
                elif "презентация" in lower:
                    cat = "ebitda_pres"
                else:
                    cat = "ebitda_msfo"
            elif "долг" in lower:
                cat = "debt"
            else:
                cat = "other"
            # URL: /evidence/<slug>/<quoted filename>
            quoted = urllib.parse.quote(name)
            url = f"/evidence/{slug}/{quoted}"
            files.append({
                "filename": name,
                "url": url,
                "abs_path": str(p),  # for server side
                "category": cat,
                "size": p.stat().st_size,
            })
    return files

def map_metric_to_evidence(evidence: List[Dict], metric: str) -> List[Dict]:
    """Отбирает релевантные скриншоты для метрики"""
    if metric == "revenue":
        # ОПУ primary, Баланс secondary
        pri = [e for e in evidence if e["category"] == "opu"]
        if pri:
            return pri
        return [e for e in evidence if "опу" in e["filename"].lower() or "opu" in e["filename"].lower()]
    if metric == "net_profit":
        pri = [e for e in evidence if e["category"] == "opu"]
        return pri
    if metric == "ebitda_issuer":
        # Prefer ОЭ_EBITDA, then Презентация, then МСФО_EBITDA
        oe = [e for e in evidence if e["category"] == "ebitda_oe"]
        if oe:
            return oe
        pres = [e for e in evidence if e["category"] == "ebitda_pres"]
        if pres:
            return pres
        msfo = [e for e in evidence if e["category"] == "ebitda_msfo"]
        if msfo:
            return msfo
        # fallback any ebitda
        return [e for e in evidence if "ebitda" in e["filename"].lower() or "ебитда" in e["filename"].lower()]
    if metric == "net_debt":
        # Prefer files with долг or balance
        debt = [e for e in evidence if e["category"] in ("debt", "ebitda_oe") and ("долг" in e["filename"].lower() or "dolg" in e["filename"].lower() or "баланс" in e["filename"].lower())]
        # actually our naming: ОЭ_EBITDA_или_долг
        for e in evidence:
            if "или_долг" in e["filename"].lower() or "ili_dolg" in e["filename"].lower() or "долг" in e["filename"].lower():
                if e not in debt:
                    debt.append(e)
        if debt:
            return debt
        bal = [e for e in evidence if e["category"] == "balance"]
        if bal:
            return bal
        # fallback oe ebitda (often combined)
        oe = [e for e in evidence if e["category"] == "ebitda_oe"]
        return oe
    return []

# ---------- Main processor ----------

def load_sources_map(wb) -> Dict[str, List[Dict]]:
    """Загружает лист Источники, ключ = тикер (или компания upper для поиска)"""
    ws = wb["Источники"]
    sources_by_ticker: Dict[str, List[Dict]] = {}
    sources_by_company: Dict[str, List[Dict]] = {}
    for r in range(4, ws.max_row + 1):
        comp = ws.cell(row=r, column=1).value
        typ = ws.cell(row=r, column=2).value
        file = ws.cell(row=r, column=3).value
        page = ws.cell(row=r, column=4).value
        what = ws.cell(row=r, column=5).value
        path = ws.cell(row=r, column=6).value
        comment = ws.cell(row=r, column=7).value
        if not comp:
            continue
        entry = {
            "company": str(comp).strip(),
            "type": str(typ).strip() if typ else "",
            "file": str(file).strip() if file else "",
            "page": str(page).strip() if page else "",
            "what": str(what).strip() if what else "",
            "path": str(path).strip() if path else "",
            "comment": str(comment).strip() if comment else "",
        }
        # key variants
        key_company = entry["company"].lower()
        # we'll later map via ticker; need to store both
        sources_by_company.setdefault(key_company, []).append(entry)
    return sources_by_company

def resolve_company_folder(company_name: str, ticker: str) -> Optional[Path]:
    """Находит папку компании в EVIDENCE_ROOT с учетом вариантов написания"""
    # Direct matches
    candidates = [
        company_name,
        company_name.replace(" ", "_"),
        company_name.replace("-", "_"),
        ticker,
    ]
    # specials
    alias_map = {
        "лукойл": "Лукойл",
        "газпром": "Газпром",
        "яндекс": "Яндекс",
        "т-технологии": "Т-Технологии",
        "татнефть": "Татнефть",
        "новатэк": "Новатэк",
        "норникель": "Норникель",
        "озон": "Озон",
        "x5": "КЦ Икс 5",
        "роснефть": "Роснефть",
        "полюс": "Полюс",
        "headhunter": "ХХру",
        "ххру": "ХХру",
        "мтс": "МТС",
        "интер рао": "Интер-Рао",
        "северсталь": "Северсталь",
        "русал": "Русал",
        "нлмк": "НЛМК",
        "фосагро": "Фосагро",
        "ростелеком": "Ростелеком",
        "аэрофлот": "Аэрофлот",
        "ммк": "ММК",
        "эн+ групп": "Эн+",
        "мд медикал": "МД Медикал",
        "лента": "Лента",
        "совкомфлот": "Совкомфлот",
        "банк санкт-петербург": "Банк Санкт Петербург",
        "алроса": "Алроса",
        "циан": "Циан",
        "афк система": "АФК_Система",
    }
    # try alias
    low = company_name.lower()
    if low in alias_map:
        p = EVIDENCE_ROOT / alias_map[low]
        if p.exists():
            return p
    # try ticker alias
    low_t = ticker.lower() if ticker else ""
    if low_t in alias_map:
        p = EVIDENCE_ROOT / alias_map[low_t]
        if p.exists():
            return p

    for cand in candidates:
        if not cand:
            continue
        p = EVIDENCE_ROOT / cand
        if p.exists():
            return p
        # case-insensitive search
        for item in EVIDENCE_ROOT.iterdir():
            if item.is_dir() and item.name.lower() == cand.lower():
                return item
            # underscore vs space
            if item.name.lower().replace("_", " ") == cand.lower().replace("_", " "):
                return item
    # brute force: compare normalized
    norm_target = re.sub(r"[^a-zа-я0-9]", "", low)
    for item in EVIDENCE_ROOT.iterdir():
        if not item.is_dir():
            continue
        norm_item = re.sub(r"[^a-zа-я0-9]", "", item.name.lower())
        if norm_target == norm_item or norm_target in norm_item or norm_item in norm_target:
            return item
    return None

def build_landing_data(create_ascii_copy: bool = False) -> List[Dict]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    wb = openpyxl.load_workbook(str(XLSX_PATH), data_only=True)
    ws = wb["Сводная база"]
    sources_by_company = load_sources_map(wb)

    companies: List[Dict] = []

    for r in range(6, ws.max_row + 1):
        ticker = ws.cell(row=r, column=3).value  # C
        comp_name = ws.cell(row=r, column=2).value  # B
        if not ticker or not comp_name:
            continue
        comp_name = str(comp_name).strip()
        ticker = str(ticker).strip()
        sector = ws.cell(row=r, column=4).value
        currency = ws.cell(row=r, column=6).value or "RUB"
        currency = str(currency).strip()
        # G=7, H=8, J=10, X=24
        rev_raw = ws.cell(row=r, column=7).value
        profit_raw = ws.cell(row=r, column=8).value
        ebitda_raw = ws.cell(row=r, column=10).value  # J
        debt_raw = ws.cell(row=r, column=24).value  # X

        rev = parse_numeric(rev_raw)
        profit = parse_numeric(profit_raw)
        ebitda = parse_numeric(ebitda_raw)
        debt = parse_numeric(debt_raw)

        slug = slugify_company(comp_name, ticker)

        # folder
        folder = resolve_company_folder(comp_name, ticker)
        evidence = collect_evidence_for_company(folder, slug) if folder else []

        # sources lookup: try by company lower
        key = comp_name.lower()
        src_entries = sources_by_company.get(key, [])
        if not src_entries:
            # try ticker lower alias
            for k, v in sources_by_company.items():
                if k == ticker.lower():
                    src_entries = v
                    break
        # split by type
        msfo_src = next((s for s in src_entries if "мсфо" in s["type"].lower()), None)
        oe_src = next((s for s in src_entries if "эмитента" in s["type"].lower()), None)
        pres_src = next((s for s in src_entries if "презентация" in s["type"].lower()), None)

        # Build source labels per metric
        # Revenue & profit -> МСФО
        def source_label(src, fallback):
            if src:
                page = src["page"]
                typ = src["type"]
                # Normalize typ: МСФО -> Отчет МСФО, Отчет эмитента -> Отчет эмитента
                if "мсфо" in typ.lower():
                    label = f"Отчет МСФО за 2025 год"
                elif "эмитента" in typ.lower():
                    label = f"Отчет эмитента за 2025 год"
                elif "презентация" in typ.lower():
                    label = f"Презентация эмитента за 2025 год"
                else:
                    label = typ
                if page and page != "н.д.":
                    label += f", стр. {page}" if "раздел" not in str(page).lower() else f", {page}"
                return label, src
            return fallback, None

        rev_source_label, rev_src = source_label(msfo_src, "Отчет МСФО за 2025 год")
        profit_source_label, profit_src = source_label(msfo_src, "Отчет МСФО за 2025 год")
        # EBITDA & debt -> Отчет эмитента, if missing fallback to МСФО or Презентация
        ebitda_source_label, ebitda_src = source_label(oe_src, "Отчет эмитента за 2025 год" if oe_src else (pres_src["type"] if pres_src else "н/д"))
        if not oe_src and pres_src:
            ebitda_source_label, ebitda_src = source_label(pres_src, "Презентация за 2025 год")
        debt_source_label, debt_src = source_label(oe_src, "Отчет эмитента за 2025 год")
        if not oe_src and pres_src:
            # debt might not be in pres
            pass

        # If ebitda_src is None but pres exists, use pres
        # Map evidence per metric
        rev_ev = map_metric_to_evidence(evidence, "revenue")
        profit_ev = map_metric_to_evidence(evidence, "net_profit")
        ebitda_ev = map_metric_to_evidence(evidence, "ebitda_issuer")
        debt_ev = map_metric_to_evidence(evidence, "net_debt")

        # Build metrics dicts
        metrics = {
            "revenue": {
                "value_raw": rev,
                "value_display": format_raw(rev, currency) if rev is not None else "н/д",
                "value_compact": format_number(rev, currency) if rev is not None else "н/д",
                "source": rev_source_label,
                "source_file": rev_src["file"] if rev_src else "",
                "source_page": rev_src["page"] if rev_src else "",
                "evidence": [{"filename": e["filename"], "url": e["url"], "category": e["category"]} for e in rev_ev],
            },
            "net_profit": {
                "value_raw": profit,
                "value_display": format_raw(profit, currency) if profit is not None else "н/д",
                "value_compact": format_number(profit, currency) if profit is not None else "н/д",
                "source": profit_source_label,
                "source_file": profit_src["file"] if profit_src else "",
                "source_page": profit_src["page"] if profit_src else "",
                "evidence": [{"filename": e["filename"], "url": e["url"], "category": e["category"]} for e in profit_ev],
            },
            "ebitda": {
                "value_raw": ebitda,
                "value_display": format_raw(ebitda, currency) if ebitda is not None else "н/д",
                "value_compact": format_number(ebitda, currency) if ebitda is not None else "н/д",
                "source": ebitda_source_label,
                "source_file": ebitda_src["file"] if ebitda_src else "",
                "source_page": ebitda_src["page"] if ebitda_src else "",
                "evidence": [{"filename": e["filename"], "url": e["url"], "category": e["category"]} for e in ebitda_ev],
                "note": "EBITDA по отчету эмитента (столбец J)" + ("" if ebitda is not None else " — не раскрыто (н.д.)"),
            },
            "net_debt": {
                "value_raw": debt,
                "value_display": format_raw(debt, currency) if debt is not None else "н/д",
                "value_compact": format_number(debt, currency) if debt is not None else "н/д",
                "source": debt_source_label,
                "source_file": debt_src["file"] if debt_src else "",
                "source_page": debt_src["page"] if debt_src else "",
                "evidence": [{"filename": e["filename"], "url": e["url"], "category": e["category"]} for e in debt_ev],
                "note": "Отрицательное значение — чистая денежная позиция" if debt is not None and debt < 0 else "",
            },
        }

        # Additional info
        # page link for МСФО file (from Источники col 6 path)
        company_entry = {
            "id": r - 5,  # 1-index
            "company": comp_name,
            "ticker": ticker,
            "slug": slug,
            "sector": str(sector).strip() if sector else "",
            "currency": currency,
            "metrics": metrics,
            # flat for sorting convenience on frontend
            "revenue": rev,
            "net_profit": profit,
            "ebitda_report": ebitda,
            "net_debt": debt,
            "revenue_display": metrics["revenue"]["value_display"],
            "revenue_compact": metrics["revenue"]["value_compact"],
            "profit_display": metrics["net_profit"]["value_display"],
            "ebitda_display": metrics["ebitda"]["value_display"],
            "debt_display": metrics["net_debt"]["value_display"],
            "evidence_all": [{"filename": e["filename"], "url": e["url"], "category": e["category"]} for e in evidence],
            "sources": src_entries,
            "folder": str(folder) if folder else None,
            "has_evidence": len(evidence) > 0,
        }
        companies.append(company_entry)

    # optional ascii copy
    if create_ascii_copy:
        create_ascii_evidence_mirror(companies)

    # Enrich the processed database with the last 30 completed MOEX sessions.
    from quote_service import enrich_companies
    enrich_companies(companies)

    # save json
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(companies, f, ensure_ascii=False, indent=2)

    print(f"Saved {len(companies)} companies to {OUTPUT_JSON}")
    for c in companies[:3]:
        print(f" - {c['company']} ({c['ticker']}) slug={c['slug']} folder={c['folder']} evidence={len(c['evidence_all'])}")
    return companies

def create_ascii_evidence_mirror(companies: List[Dict]):
    """Копирует evidence файлы в static/evidence_ascii/<slug>/ с транслитерированными именами
    Нужно для обхода проблем кириллицы на некоторых хостингах. Вызывать опционально.
    """
    dest_root = BASE_DIR / "static" / "evidence_ascii"
    dest_root.mkdir(parents=True, exist_ok=True)
    for comp in companies:
        slug = comp["slug"]
        folder = Path(comp["folder"]) / "evidence" if comp["folder"] else None
        if not folder or not folder.exists():
            continue
        dest = dest_root / slug
        dest.mkdir(parents=True, exist_ok=True)
        for p in folder.glob("*"):
            if p.is_file() and p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
                ascii_name = transliterate(p.stem) + p.suffix.lower()
                # keep mapping?
                shutil.copy2(p, dest / ascii_name)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--ascii", action="store_true", help="создать ascii-копию evidence")
    args = parser.parse_args()
    build_landing_data(create_ascii_copy=args.ascii)
