from datetime import date, datetime, time, timezone, timedelta
try:
    from zoneinfo import ZoneInfo
    US_EASTERN = ZoneInfo("America/New_York")
except ImportError:  # Python 3.7 fallback; production venv includes pytz.
    try:
        import pytz
        US_EASTERN = pytz.timezone("America/New_York")
    except ImportError:
        US_EASTERN = timezone(timedelta(hours=-4))
from math import erf, log, sqrt
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import os
from pathlib import Path
import sys
import threading
import traceback
import webbrowser

ROOT = Path(__file__).resolve().parents[1]
# A frozen executable keeps program files read-only and stores each user's
# database in their Windows profile.  Development keeps the existing project
# database so local work is unaffected.
FROZEN = bool(getattr(sys, "frozen", False))
RESOURCE_ROOT = Path(getattr(sys, "_MEIPASS", ROOT))
DATA_ROOT = (Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Option Premium Ledger") if FROZEN else ROOT / "data"
DATA_ROOT.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("OPTION_LEDGER_DATA_DIR", str(DATA_ROOT))
# PyInstaller's resource directory differs between one-folder, one-file and
# some Windows launchers. Prefer any location that actually contains the app.
# sys.argv[0] is particularly reliable for the onedir executable used here.
_argv_directory = Path(sys.argv[0]).resolve().parent
_ui_candidates = [
    Path.cwd() / "ui",
    _argv_directory / "ui",
    RESOURCE_ROOT / "ui",
    Path(sys.executable).resolve().parent / "ui",
    ROOT / "dist" / "client",
    ROOT / "ui",
]
STATIC_ROOT = next((path for path in _ui_candidates if (path / "index.html").is_file()), _ui_candidates[0])
STARTUP_LOG = DATA_ROOT / "startup-error.log"
BOOT_LOG = DATA_ROOT / "startup-state.log"

def _boot_state(stage):
    if FROZEN:
        BOOT_LOG.write_text(stage, encoding="utf-8")

_boot_state("paths-ready")
sys.path.insert(0, str(Path(__file__).parent))
try:
    from .futu_adapter import FutuAdapter, FutuUnavailable
    from .ledger import build_ledger, dashboard_from_ledger
    from .storage import Store
except ImportError:  # Direct development command: python backend/server.py
    from futu_adapter import FutuAdapter, FutuUnavailable
    from ledger import build_ledger, dashboard_from_ledger
    from storage import Store

_boot_state("modules-ready")
STORE = Store(DATA_ROOT / "ledger.sqlite3")
_boot_state("store-ready")


def _normal_cdf(value):
    return (1 + erf(value / sqrt(2))) / 2


def breach_probability(position, risk, today=None, now=None):
    """Risk-neutral probability of expiring ITM, using the selected Futu spot and IV."""
    risk = risk or {}
    spot = risk.get("underlying_price")
    iv = risk.get("implied_volatility")
    fallback = risk.get("exercise_probability")
    try:
        spot, iv = float(spot), float(iv)
    except (TypeError, ValueError):
        return (float(fallback), "富途行权概率") if fallback is not None else (None, "富途未返回 IV 或标的价格")
    if spot <= 0 or iv <= 0:
        return (float(fallback), "富途行权概率") if fallback is not None else (None, "富途未返回有效 IV 或标的价格")
    today = today or date.today()
    now = now or datetime.now(US_EASTERN)
    expiry = datetime.fromisoformat(position["expiry"]).date()
    days = (expiry - today).days
    if days <= 0:
        if now.weekday() < 5 and time(9, 30) <= now.time().replace(tzinfo=None) < time(16, 0):
            remaining = max((16 - (now.hour + now.minute / 60)) / 6.5, 0) / 365
        else:
            remaining = 0
    else:
        remaining = days / 365
    strike = float(position["strike"])
    if remaining <= 0:
        breached = spot > strike if position["option_type"] == "Call" else spot < strike
        return (100.0 if breached else 0.0, risk.get("price_basis", "前收盘价"))
    d2 = (log(spot / strike) - 0.5 * iv * iv * remaining) / (iv * sqrt(remaining))
    probability = _normal_cdf(d2) if position["option_type"] == "Call" else 1 - _normal_cdf(d2)
    return (round(probability * 100, 1), f"{risk.get('price_basis', '标的价格')} · IV {iv * 100:.1f}%")


def current_dashboard(connected=False, account_id=None, broker="FUTUINC", market="US"):
    fills, marks = STORE.rows()
    saved = STORE.meta()
    broker = broker if connected else saved.get("broker", broker)
    market = market if connected else saved.get("market", market)
    account_id = account_id if connected else saved.get("account_tail")
    connected = connected or saved.get("connection_verified") == "true"
    firm_label = "富途 HK" if broker == "FUTUSECURITIES" else "Moomoo US"
    meta = {"account_label":f"{firm_label} · {market} · 实盘只读","account_mask":f"•• {str(account_id)[-4:]}" if account_id else "••••","synced_at":datetime.now().strftime("%Y-%m-%d %H:%M:%S") if connected else "—","source":"富途 OpenD" if connected else "本地缓存（账户待验证）","opend_status":"已连接" if connected else "未验证"}
    dashboard = dashboard_from_ledger(build_ledger(fills, marks), meta)
    risk_by_code = STORE.option_risk()
    for position in dashboard["positions"]:
        probability, note = breach_probability(position, risk_by_code.get(position["code"]))
        position["breach_probability"] = probability
        position["breach_note"] = note
    calls = {}
    puts = {}
    for position in dashboard["positions"]:
        target = calls if position["option_type"] == "Call" else puts
        target[position["symbol"]] = target.get(position["symbol"], 0) + position["quantity"]
    stock_rows=[]
    for holding in STORE.holdings():
        symbol=holding["symbol"]; call_count=calls.get(symbol,0); put_count=puts.get(symbol,0)
        share_capacity = int(float(holding["quantity"]) // 100)
        if call_count and call_count <= share_capacity: status = "已卖 Covered Call"
        elif call_count: status = "Call 覆盖待核对"
        elif put_count: status = "已卖 Sell Put"
        else: status = "尚未操作"
        if call_count and put_count: status += " + Sell Put"
        stock_rows.append({**holding,"covered_calls":call_count,"sell_puts":put_count,"share_capacity":share_capacity,"status":status})
    dashboard["stock_holdings"] = stock_rows
    dashboard["holdings_updated_at"] = stock_rows[0]["updated_at"] if stock_rows else None
    return dashboard


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print("[api]", fmt % args)

    def reply(self, status, payload):
        data=json.dumps(payload,ensure_ascii=False,default=str).encode("utf-8")
        self.send_response(status); self.send_header("Content-Type","application/json; charset=utf-8"); self.send_header("Content-Length",str(len(data))); self.send_header("Cache-Control","no-store"); self.end_headers(); self.wfile.write(data)

    def static_file(self, request_path):
        """Serve the bundled React build.  API and UI share one local origin."""
        relative = request_path.split("?", 1)[0].lstrip("/") or "index.html"
        candidate = (STATIC_ROOT / relative).resolve()
        try:
            candidate.relative_to(STATIC_ROOT.resolve())
        except ValueError:
            return self.reply(403, {"error": "forbidden"})
        # React routes (or a direct opening of /) fall back to the app shell.
        if not candidate.is_file():
            candidate = STATIC_ROOT / "index.html"
        if not candidate.is_file():
            return self.reply(503, {"error": "界面资源未找到，请重新安装应用。"})
        data = candidate.read_bytes()
        content_type = mimetypes.guess_type(str(candidate))[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store" if candidate.name == "index.html" else "public, max-age=86400")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path.startswith("/api/health"):
            return self.reply(200,{"ok":True,"service":"option-premium-ledger","ui_ready":(STATIC_ROOT / "index.html").is_file(),"ui_root":str(STATIC_ROOT),"runtime_argv":str(sys.argv[0]),"runtime_executable":str(sys.executable)})
        if self.path.startswith("/api/dashboard"):
            return self.reply(200, current_dashboard())
        return self.static_file(self.path)

    def do_POST(self):
        length=int(self.headers.get("Content-Length",0)); body=json.loads(self.rfile.read(length) or b"{}")
        if self.path.startswith("/api/sync"):
            try:
                broker=body.get("broker","FUTUINC"); market=body.get("market","US")
                adapter=FutuAdapter(host=body.get("host","127.0.0.1"),port=body.get("port",11111),broker=broker,account_id=body.get("accountId"),market=market)
                fills,account_id=adapter.fetch(body.get("since","2025-01-01"),date.today())
                inserted=STORE.upsert_fills(fills)
                all_fills, cached_marks = STORE.rows()
                active_codes = {position["code"] for position in build_ledger(all_fills, cached_marks)["positions"]}
                marks=adapter.fetch_marks(active_codes); STORE.set_marks(marks)
                # IV/exercise probability APIs are rate-limited. Only current short contracts
                # affect the dashboard, so never request every historical contract here.
                STORE.set_option_risk(adapter.fetch_option_risk(active_codes))
                STORE.replace_holdings(adapter.fetch_stock_holdings(account_id))
                STORE.set_meta({"connection_verified":"true","broker":broker,"market":market,"account_tail":str(account_id)[-4:]})
                return self.reply(200,{"inserted":inserted,"fees_updated":sum(bool(f.get("fee")) for f in fills),"dashboard":current_dashboard(True,account_id,broker,market)})
            except (FutuUnavailable,ValueError,OSError) as exc: return self.reply(503,{"error":str(exc)})
            except Exception as exc: return self.reply(500,{"error":f"同步失败：{exc}"})
        return self.reply(404,{"error":"not found"})


# PyInstaller may load the entry script under its file module name rather than
# ``__main__``.  Frozen builds must still execute the local service.
def main():
    try:
        _boot_state("binding-server")
        server = None
        for port in range(8765, 8786):
            try:
                server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
                break
            except OSError as exc:
                if getattr(exc, "winerror", None) != 10048:
                    raise
        if server is None:
            raise OSError("本地端口 8765–8785 均被占用，请关闭旧版账本后重试。")
        _boot_state("server-ready")
        local_url = f"http://127.0.0.1:{server.server_port}/"
        print(f"Option Premium Ledger: {local_url}")
        if FROZEN:
            # Some Windows browser handlers block synchronously.  The server
            # must start first so the user can always reach the local page.
            threading.Thread(target=webbrowser.open, args=(local_url,), daemon=True).start()
        server.serve_forever()
    except Exception:
        STARTUP_LOG.write_text(traceback.format_exc(), encoding="utf-8")
        raise


if __name__ == "__main__":
    main()
