"""MOEX ISS market data and valuation multiples.

The cache is deliberately made of ordinary JSON/CSV files: it is both the
processed quote database and a fallback when ISS is temporarily unavailable.
"""
from __future__ import annotations

import csv
import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import requests


LOG = logging.getLogger(__name__)
BASE_DIR = Path(__file__).parent
QUOTES_DIR = BASE_DIR / "baza_v2" / "02_kotirovki"
SUMMARY_FILE = QUOTES_DIR / "quotes_30d.json"
ISS_ROOT = "https://iss.moex.com/iss"
TRADING_DAYS = 30


def _number(value: Any) -> Optional[float]:
    try:
        if value is None or isinstance(value, bool):
            return None
        return float(str(value).replace(" ", "").replace(",", "."))
    except (TypeError, ValueError):
        return None


def _rows(block: Dict[str, Any]) -> List[Dict[str, Any]]:
    columns = block.get("columns", [])
    return [dict(zip(columns, row)) for row in block.get("data", [])]


class MoexQuoteService:
    """Download and cache the last 30 completed trading sessions from ISS."""

    def __init__(self, quotes_dir: Path = QUOTES_DIR, timeout: int = 20):
        self.quotes_dir = Path(quotes_dir)
        self.summary_file = self.quotes_dir / SUMMARY_FILE.name
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "MSFO-Analyst/1.0 (ISS MOEX)"})

    @staticmethod
    def completed_through(today: Optional[date] = None) -> date:
        return (today or date.today()) - timedelta(days=1)

    def _get(self, path: str, **params: Any) -> Dict[str, Any]:
        params.setdefault("iss.meta", "off")
        response = self.session.get(f"{ISS_ROOT}/{path}", params=params, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def security_info(self, ticker: str) -> Dict[str, Any]:
        payload = self._get(f"securities/{ticker}.json")
        description = {r.get("name"): r.get("value") for r in _rows(payload.get("description", {}))}
        boards = [
            r for r in _rows(payload.get("boards", {}))
            if r.get("engine") == "stock" and r.get("market") == "shares"
        ]
        primary = next((r for r in boards if r.get("is_primary") == 1 and r.get("is_traded") == 1), None)
        primary = primary or next((r for r in boards if r.get("is_primary") == 1), None)
        primary = primary or next((r for r in boards if r.get("is_traded") == 1), None)
        if not primary:
            raise ValueError(f"Для {ticker} не найден основной режим торгов акциями")
        issue_size = _number(description.get("ISSUESIZEPLACED")) or _number(description.get("ISSUESIZE"))
        if not issue_size:
            raise ValueError(f"ISS не вернул количество акций для {ticker}")
        return {
            "ticker": ticker,
            "board": primary["boardid"],
            "currency": primary.get("currencyid") or "RUB",
            "issue_size": int(issue_size),
        }

    def history(self, ticker: str, board: str, through: date) -> List[Dict[str, Any]]:
        # 90 calendar days safely covers 30 exchange sessions and long holidays.
        date_from = through - timedelta(days=90)
        payload = self._get(
            f"history/engines/stock/markets/shares/boards/{board}/securities/{ticker}.json",
            **{
                "from": date_from.isoformat(),
                "till": through.isoformat(),
                "iss.only": "history",
                "history.columns": "TRADEDATE,SECID,BOARDID,CLOSE,LEGALCLOSEPRICE,WAPRICE,VOLUME,VALUE,NUMTRADES",
                "limit": 100,
            },
        )
        result = []
        for row in _rows(payload.get("history", {})):
            price = _number(row.get("CLOSE")) or _number(row.get("LEGALCLOSEPRICE")) or _number(row.get("WAPRICE"))
            if not row.get("TRADEDATE") or price is None:
                continue
            result.append({
                "date": row["TRADEDATE"],
                "price": price,
                "volume": _number(row.get("VOLUME")),
                "turnover": _number(row.get("VALUE")),
                "trades": int(_number(row.get("NUMTRADES")) or 0),
            })
        return sorted(result, key=lambda r: r["date"])[-TRADING_DAYS:]

    def usd_rub_history(self, through: date) -> Dict[str, float]:
        """USD/RUB TOM closes used only to align USD financial statements."""
        payload = self._get(
            "history/engines/currency/markets/selt/boards/CETS/securities/USD000UTSTOM.json",
            **{
                "from": (through - timedelta(days=100)).isoformat(),
                "till": through.isoformat(),
                "iss.only": "history",
                "history.columns": "TRADEDATE,CLOSE,WAPRICE",
                "limit": 100,
            },
        )
        rates = {}
        for row in _rows(payload.get("history", {})):
            rate = _number(row.get("CLOSE")) or _number(row.get("WAPRICE"))
            if row.get("TRADEDATE") and rate:
                rates[row["TRADEDATE"]] = rate
        return rates

    def fetch_ticker(self, ticker: str, through: date) -> Dict[str, Any]:
        ticker = ticker.strip().upper()
        info = self.security_info(ticker)
        prices = self.history(ticker, info["board"], through)
        if not prices:
            raise ValueError(f"ISS не вернул историю торгов для {ticker}")
        for row in prices:
            row["shares"] = info["issue_size"]
            row["market_cap_mln"] = row["price"] * info["issue_size"] / 1_000_000
        return {
            **info,
            "through": through.isoformat(),
            "trading_days": len(prices),
            "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "prices": prices,
        }

    def _load_cache(self) -> Dict[str, Dict[str, Any]]:
        if not self.summary_file.exists():
            return {}
        try:
            data = json.loads(self.summary_file.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save_cache(self, data: Dict[str, Dict[str, Any]]) -> None:
        self.quotes_dir.mkdir(parents=True, exist_ok=True)
        temp = self.summary_file.with_suffix(".tmp")
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(self.summary_file)
        for ticker, quote in data.items():
            path = self.quotes_dir / f"{ticker}_30d.csv"
            with path.open("w", encoding="utf-8-sig", newline="") as handle:
                fields = ["date", "price", "shares", "volume", "turnover", "trades", "market_cap_mln"]
                writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(quote.get("prices", []))

    def refresh(self, tickers: Iterable[str], force: bool = False) -> Dict[str, Dict[str, Any]]:
        through = self.completed_through()
        cache = self._load_cache()
        wanted = sorted({str(t).strip().upper() for t in tickers if t})
        pending = [t for t in wanted if force or cache.get(t, {}).get("through") != through.isoformat()]
        if pending:
            with ThreadPoolExecutor(max_workers=min(8, len(pending))) as pool:
                futures = {pool.submit(self.fetch_ticker, ticker, through): ticker for ticker in pending}
                for future in as_completed(futures):
                    ticker = futures[future]
                    try:
                        cache[ticker] = future.result()
                    except Exception as exc:  # retain the last good cache per ticker
                        LOG.warning("MOEX ISS %s: %s", ticker, exc)
                        if ticker not in cache:
                            cache[ticker] = {"ticker": ticker, "error": str(exc), "prices": []}
            self._save_cache(cache)
        return {ticker: cache.get(ticker, {}) for ticker in wanted}


def _ratio(numerator: Optional[float], denominator: Optional[float]) -> Optional[float]:
    if numerator is None or denominator is None or denominator <= 0:
        return None
    return round(numerator / denominator, 2)


def add_multiples(company: Dict[str, Any], quote: Dict[str, Any]) -> Dict[str, Any]:
    """Attach 30 daily market observations and valuation multiples in-place."""
    currency = company.get("currency") or "RUB"
    quote_currency = quote.get("currency") or "RUB"
    fx_rates = quote.get("fx_rates", {})
    profit = _number(company.get("net_profit"))
    ebitda = _number(company.get("ebitda_report"))
    debt = _number(company.get("net_debt"))
    series = []
    for item in quote.get("prices", []):
        market_cap = _number(item.get("market_cap_mln"))
        fx_rate = _number(fx_rates.get(item.get("date"))) if currency == "USD" else None
        comparable_cap = market_cap
        if currency == "USD":
            comparable_cap = market_cap / fx_rate if market_cap is not None and fx_rate else None
        elif currency != quote_currency:
            comparable_cap = None
        enterprise_value = comparable_cap + debt if comparable_cap is not None and debt is not None else None
        series.append({
            **item,
            "market_cap_reporting_mln": round(comparable_cap, 2) if comparable_cap is not None else None,
            "fx_rate": fx_rate,
            "enterprise_value_mln": round(enterprise_value, 2) if enterprise_value is not None else None,
            "pe": _ratio(comparable_cap, profit),
            "ev_ebitda": _ratio(enterprise_value, ebitda),
            "net_debt_ebitda": _ratio(debt, ebitda),
        })
    company["market"] = {
        "source": "MOEX ISS",
        "board": quote.get("board"),
        "currency": quote_currency,
        "through": quote.get("through"),
        "updated_at": quote.get("updated_at"),
        "trading_days": len(series),
        "issue_size": quote.get("issue_size"),
        "reporting_currency": currency,
        "currency_compatible": bool(series) and all(r.get("market_cap_reporting_mln") is not None for r in series),
        "error": quote.get("error") if not series else None,
        "series": series,
        "latest": series[-1] if series else None,
    }
    return company


def enrich_companies(companies: List[Dict[str, Any]], force: bool = False) -> List[Dict[str, Any]]:
    service = MoexQuoteService()
    quotes = service.refresh((c.get("ticker") for c in companies), force=force)
    if any(c.get("currency") == "USD" for c in companies):
        try:
            rates = service.usd_rub_history(service.completed_through())
            # Stock and FX sessions can differ. Carry the last available rate forward.
            for quote in quotes.values():
                available = sorted(rates.items())
                quote["fx_rates"] = {
                    row["date"]: next((rate for day, rate in reversed(available) if day <= row["date"]), None)
                    for row in quote.get("prices", [])
                }
        except Exception as exc:
            LOG.warning("MOEX ISS USD/RUB: %s", exc)
    for company in companies:
        add_multiples(company, quotes.get(str(company.get("ticker", "")).upper(), {}))
    return companies
