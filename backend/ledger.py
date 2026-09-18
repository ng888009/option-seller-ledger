"""FIFO ledger for short option fills. Pure functions, no Futu dependency."""
from collections import defaultdict, deque
from datetime import date, datetime
import re

# Futu normally pads the strike to 6--8 digits, but some long-dated contracts
# are returned as e.g. ``US.CRCL270115C90000`` (a five-digit 90.00 strike).
# Accept that form as well so option positions never leak into the stock table.
OPTION_RE = re.compile(r"^(?:US\.)?([A-Z.\-]{1,10})(\d{6})([CP])(\d{5,8})$")


def parse_option_code(code):
    """Parse Futu/OCC-style US option code, e.g. US.TSLA260918P00410000."""
    compact = str(code or "").replace(" ", "").upper()
    match = OPTION_RE.match(compact)
    if not match:
        return None
    symbol, yymmdd, kind, strike_raw = match.groups()
    expiry = datetime.strptime(yymmdd, "%y%m%d").date().isoformat()
    return {"symbol": symbol, "expiry": expiry, "option_type": "Call" if kind == "C" else "Put", "strike": int(strike_raw) / 1000.0, "multiplier": 100}


def _number(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def build_ledger(fills, marks=None, today=None):
    """Match SELL_SHORT fills against BUY_BACK fills using FIFO per option contract."""
    marks = marks or {}
    today = today or date.today()
    grouped = defaultdict(list)
    ignored = []
    for raw in fills:
        info = parse_option_code(raw.get("code")) or raw.get("contract")
        if not info:
            ignored.append({"fill": raw, "reason": "不是可识别的美股期权合约"})
            continue
        fill = dict(raw)
        fill.update(info)
        fill["qty"] = _number(fill.get("qty"))
        fill["price"] = _number(fill.get("price"))
        fill["fee"] = _number(fill.get("fee"))
        fill["multiplier"] = _number(fill.get("multiplier"), 100)
        fill["time"] = str(fill.get("create_time") or fill.get("time") or "")
        fill["side"] = str(fill.get("trd_side") or fill.get("side") or "").upper()
        grouped[fill["code"]].append(fill)

    open_positions, closed, reconciliation = [], [], []
    for code, contract_fills in grouped.items():
        shorts = deque()
        for fill in sorted(contract_fills, key=lambda x: (x["time"], str(x.get("deal_id", "")))):
            if fill["side"] == "SELL_SHORT":
                shorts.append({**fill, "remaining": fill["qty"], "fee_remaining": fill["fee"]})
                continue
            if fill["side"] != "BUY_BACK":
                continue
            buy_remaining = fill["qty"]
            buy_fee_per_qty = fill["fee"] / fill["qty"] if fill["qty"] else 0
            while buy_remaining > 1e-9 and shorts:
                sell = shorts[0]
                matched = min(buy_remaining, sell["remaining"])
                sell_fee = sell["fee_remaining"] * matched / sell["remaining"] if sell["remaining"] else 0
                buy_fee = buy_fee_per_qty * matched
                gross = (sell["price"] - fill["price"]) * sell["multiplier"] * matched
                closed.append({
                    "id": f'{sell.get("deal_id", "sell")}-{fill.get("deal_id", "buy")}',
                    "code": code, "side": f'Sell {sell["option_type"]}', "symbol": sell["symbol"],
                    "expiry": sell["expiry"], "option_type": sell["option_type"], "strike": sell["strike"],
                    "quantity": matched, "opened": sell["time"][:10], "closed": fill["time"][:10],
                    "premium": round(sell["price"] * sell["multiplier"] * matched, 2),
                    "buyback": round(fill["price"] * sell["multiplier"] * matched, 2),
                    "fees": round(sell_fee + buy_fee, 2), "gross_pnl": round(gross, 2),
                    "pnl": round(gross - sell_fee - buy_fee, 2),
                })
                sell["remaining"] -= matched
                sell["fee_remaining"] -= sell_fee
                buy_remaining -= matched
                if sell["remaining"] <= 1e-9:
                    shorts.popleft()
            if buy_remaining > 1e-9:
                reconciliation.append({"fill": fill, "quantity": buy_remaining, "reason": "买回成交找不到此前卖空开仓"})

        for sell in shorts:
            mark = _number(marks.get(code), sell.get("mark_price", 0))
            quantity = sell["remaining"]
            premium = sell["price"] * sell["multiplier"] * quantity
            buyback = mark * sell["multiplier"] * quantity
            opened = datetime.fromisoformat(sell["time"][:10]).date() if sell["time"] else today
            expiry = datetime.fromisoformat(sell["expiry"]).date()
            if expiry < today:
                gross = premium
                closed.append({
                    "id": f'{sell.get("deal_id", "sell")}-expiry', "code": code,
                    "side": f'Sell {sell["option_type"]}', "symbol": sell["symbol"],
                    "expiry": sell["expiry"], "option_type": sell["option_type"], "strike": sell["strike"],
                    "quantity": quantity, "opened": opened.isoformat(), "closed": expiry.isoformat(),
                    "premium": round(premium, 2), "buyback": 0.0,
                    "fees": round(sell["fee_remaining"], 2), "gross_pnl": round(gross, 2),
                    "pnl": round(gross - sell["fee_remaining"], 2), "close_reason": "到期结转",
                })
                continue
            unrealized = premium - buyback - sell["fee_remaining"] if mark else None
            open_positions.append({
                "id": sell.get("deal_id") or code, "code": code, "side": f'Sell {sell["option_type"]}',
                "symbol": sell["symbol"], "expiry": sell["expiry"], "option_type": sell["option_type"],
                "strike": sell["strike"], "opened": opened.isoformat(), "days_open": max((today-opened).days, 0),
                "quantity": quantity, "dte": (expiry-today).days, "premium": round(premium, 2),
                "mark": mark, "unrealized": round(unrealized, 2) if unrealized is not None else None,
                "return_rate": round(unrealized/premium*100, 1) if unrealized is not None and premium else None,
                "status": "临近到期" if 0 <= (expiry-today).days <= 7 else ("浮亏" if unrealized is not None and unrealized < 0 else "持有中"),
            })
    return {"positions": open_positions, "closed": closed, "reconciliation": reconciliation, "ignored": ignored}


def dashboard_from_ledger(ledger, metadata=None):
    positions, closed = ledger["positions"], ledger["closed"]
    symbols = sorted({row["symbol"] for row in positions + closed})
    symbol_rows = []
    for symbol in symbols:
        cp = [r for r in closed if r["symbol"] == symbol]
        op = [r for r in positions if r["symbol"] == symbol]
        realized = sum(r["pnl"] for r in cp)
        known_unrealized = sum(r["unrealized"] for r in op if r["unrealized"] is not None)
        symbol_rows.append({"symbol": symbol, "closed": len(cp), "realized": round(realized,2), "open": len(op), "buyback": round(sum((r["mark"] or 0)*100*r["quantity"] for r in op),2), "unrealized": round(known_unrealized,2), "premium": round(sum(r["premium"] for r in op),2), "win_rate": round(sum(r["pnl"]>0 for r in cp)/len(cp)*100,1) if cp else 0})
    realized_gross = sum(r["gross_pnl"] for r in closed)
    realized_net = sum(r["pnl"] for r in closed)
    known_unrealized = sum(r["unrealized"] for r in positions if r["unrealized"] is not None)
    buckets = defaultdict(float)
    for row in positions: buckets[row["expiry"][:7]] += row["premium"]
    return {
        "meta": metadata or {"account_label":"FUTU · US · 实盘只读","account_mask":"••••","synced_at":"—","source":"本地数据库","opend_status":"未连接"},
        "metrics": {"realized_gross":round(realized_gross,2),"realized_net":round(realized_net,2),"period_cashflow":round(sum(r["premium"]-r["buyback"]-r["fees"] for r in closed)+sum(r["premium"] for r in positions),2),"closed_cycles":len(closed),"win_rate":round(sum(r["pnl"]>0 for r in closed)/len(closed)*100,1) if closed else 0,"unrealized":round(known_unrealized,2),"premium_open":round(sum(r["premium"] for r in positions),2)},
        "expiry_buckets":[{"label":k,"amount":round(v,2)} for k,v in sorted(buckets.items())[:5]],
        "alerts":{"expiring":sum(0<=r["dte"]<=7 for r in positions),"losing":sum(r["unrealized"] is not None and r["unrealized"]<0 for r in positions),"reconciliation":len(ledger["reconciliation"])},
        "symbols":symbol_rows,"positions":positions,"closed":sorted(closed,key=lambda r:r["closed"],reverse=True),
    }
