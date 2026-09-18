"""Read-only adapter for Futu OpenD. No trading/unlock APIs are used."""
from datetime import date, datetime, timedelta, time, timezone
try:
    from zoneinfo import ZoneInfo
    US_EASTERN = ZoneInfo("America/New_York")
except ImportError:  # Python 3.7 fallback; production venv includes pytz.
    try:
        import pytz
        US_EASTERN = pytz.timezone("America/New_York")
    except ImportError:
        US_EASTERN = timezone(timedelta(hours=-4))
import math
import os
from pathlib import Path
import socket


class FutuUnavailable(RuntimeError): pass


def _records(frame):
    return frame.to_dict("records")


class FutuAdapter:
    def __init__(self, host="127.0.0.1", port=11111, broker="FUTUINC", account_id=None, market="US"):
        # Futu SDK writes a log during import.  For a packaged program this
        # must be a per-user writable directory, never the installation folder.
        runtime_base = Path(os.environ.get("OPTION_LEDGER_DATA_DIR", Path(__file__).resolve().parents[1] / "data"))
        runtime_dir = runtime_base / "runtime"
        runtime_dir.mkdir(parents=True, exist_ok=True)
        os.environ["appdata"] = str(runtime_dir)
        try:
            import futu
        except ImportError:
            try:
                import moomoo as futu
            except ImportError as exc:
                raise FutuUnavailable("缺少 futu-api/moomoo-api Python 包，请先安装 requirements.txt") from exc
        self.futu = futu; self.host = host; self.port = int(port); self.account_id = str(account_id).strip() if account_id else ""
        self.market_name = str(market or "US").upper(); self.market = getattr(futu.TrdMarket, self.market_name, futu.TrdMarket.US)
        self.broker = getattr(futu.SecurityFirm, broker, futu.SecurityFirm.FUTUINC)

    def _trade_ctx(self):
        try:
            with socket.create_connection((self.host, self.port), timeout=2):
                pass
        except OSError as exc:
            raise FutuUnavailable(f"无法连接 OpenD {self.host}:{self.port}，请确认 OpenD 已启动且 API 端口正确") from exc
        return self.futu.OpenSecTradeContext(filter_trdmarket=self.market, host=self.host, port=self.port, security_firm=self.broker)

    def fetch(self, since, until=None):
        until = until or date.today(); start = datetime.fromisoformat(str(since)).date(); all_fills=[]; orders={}
        ctx = self._trade_ctx()
        try:
            ret, accounts = ctx.get_acc_list()
            if ret != self.futu.RET_OK: raise FutuUnavailable(str(accounts))
            accounts = accounts[(accounts["trd_env"].astype(str) == "REAL") & accounts["trdmarket_auth"].astype(str).str.contains(self.market_name, na=False)] if "trdmarket_auth" in accounts else accounts
            if accounts.empty: raise FutuUnavailable(f"未找到具有 {self.market_name} 权限的实盘账户")
            if self.account_id:
                def matches_account(row):
                    identifiers = (row.get("acc_id"), row.get("uni_card_num"), row.get("card_num"))
                    return any(str(value) == self.account_id or str(value).endswith(self.account_id) for value in identifiers if value is not None)
                matches = accounts[accounts.apply(matches_account, axis=1)]
                if len(matches) != 1:
                    raise FutuUnavailable("找不到指定的实盘账户；请填写 OpenD 交易账户 ID、统一账号或其尾号")
                self.account_id = int(matches.iloc[0]["acc_id"])
            elif len(accounts) == 1:
                self.account_id = int(accounts.iloc[0]["acc_id"])
            else:
                tails = "、".join(f"尾号 {str(value)[-4:]}" for value in accounts["acc_id"].tolist())
                raise FutuUnavailable(f"检测到多个具有 {self.market_name} 权限的实盘账户（{tails}），为防止统计错账户，请在连接设置填写账户尾号")
            cursor=start
            while cursor <= until:
                end=min(cursor+timedelta(days=89),until)
                kwargs={"start":f"{cursor.isoformat()} 00:00:00","end":f"{end.isoformat()} 23:59:59","trd_env":self.futu.TrdEnv.REAL,"acc_id":self.account_id}
                ret, data=ctx.history_deal_list_query(deal_market=self.market, **kwargs)
                if ret != self.futu.RET_OK: raise FutuUnavailable(str(data))
                all_fills.extend(_records(data))
                ret, order_data=ctx.history_order_list_query(order_market=self.market, **kwargs)
                if ret == self.futu.RET_OK:
                    for row in _records(order_data): orders[str(row["order_id"])]=row
                cursor=end+timedelta(days=1)
            from backend.ledger import parse_option_code
            option_fills=[f for f in all_fills if str(f.get("code", "")).startswith("US.") and parse_option_code(f.get("code"))]
            order_ids=list({str(f.get("order_id")) for f in option_fills if f.get("order_id")})
            fees={}
            for i in range(0,len(order_ids),200):
                ret, fee_data=ctx.order_fee_query(order_ids[i:i+200],acc_id=self.account_id)
                if ret == self.futu.RET_OK:
                    fees.update({str(r["order_id"]):float(r.get("fee_amount",0)) for r in _records(fee_data)})
            order_qty={oid:sum(float(f.get("qty",0)) for f in option_fills if str(f.get("order_id"))==oid) for oid in order_ids}
            for fill in option_fills:
                oid=str(fill.get("order_id","")); fill["fee"]=fees.get(oid,0)*float(fill.get("qty",0))/order_qty.get(oid,1)
            return option_fills, self.account_id
        finally: ctx.close()

    def fetch_marks(self, codes):
        if not codes: return {}
        try:
            with socket.create_connection((self.host, self.port), timeout=2):
                pass
        except OSError:
            return {}
        ctx=self.futu.OpenQuoteContext(host=self.host,port=self.port)
        try:
            ret,data=ctx.get_option_quote(list(codes))
            if ret != self.futu.RET_OK: return {}
            marks={}
            for row in _records(data): marks[str(row["code"])]=float(row.get("mark_price") or row.get("mid_price") or row.get("price") or 0)
            return marks
        finally: ctx.close()

    @staticmethod
    def _number(value):
        try:
            value = float(value)
            return value if math.isfinite(value) else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _us_regular_session(now=None):
        now = now or datetime.now(US_EASTERN)
        return now.weekday() < 5 and time(9, 30) <= now.time().replace(tzinfo=None) < time(16, 0)

    def fetch_option_risk(self, codes):
        """Fetch IV and a price basis for each option; never sends trading requests."""
        from backend.ledger import parse_option_code
        codes = list(codes)
        parsed = {code: parse_option_code(code) for code in codes}
        underlyings = sorted({f"US.{info['symbol']}" for info in parsed.values() if info})
        if not underlyings:
            return []
        ctx = self.futu.OpenQuoteContext(host=self.host, port=self.port)
        try:
            # Market snapshot includes option_implied_volatility for individual
            # US option contracts and supports batch queries, unlike the separate
            # volatility endpoint which may reject contracts on some OpenD builds.
            ret, snapshot = ctx.get_market_snapshot(underlyings + codes)
            if ret != self.futu.RET_OK:
                return []
            intraday = self._us_regular_session()
            prices = {}
            snapshot_rows = {str(row.get("code")): row for row in _records(snapshot)}
            for row in snapshot_rows.values():
                last = self._number(row.get("last_price"))
                previous = self._number(row.get("prev_close_price"))
                selected = last if intraday and last and last > 0 else previous
                if selected and selected > 0:
                    prices[str(row.get("code"))] = (selected, "盘中实时价" if intraday and last and last > 0 else "前收盘价")
            result = []
            for code, info in parsed.items():
                if not info:
                    continue
                spot = prices.get(f"US.{info['symbol']}")
                if not spot:
                    continue
                option_row = snapshot_rows.get(code, {})
                iv = self._number(option_row.get("option_implied_volatility"))
                if iv is None:
                    iv = self._number(option_row.get("implied_volatility"))
                if iv is not None:
                    iv = iv / 100 if iv > 1 else iv
                result.append({"code":code, "underlying_price":spot[0], "implied_volatility":iv,
                               "exercise_probability":None, "price_basis":spot[1]})
            return result
        finally:
            ctx.close()

    def fetch_stock_holdings(self, account_id=None):
        """Return the current US stock positions only; option positions are handled by the ledger."""
        account_id = int(account_id or self.account_id)
        from backend.ledger import parse_option_code
        ctx = self._trade_ctx()
        try:
            ret, data = ctx.position_list_query(trd_env=self.futu.TrdEnv.REAL, acc_id=account_id)
            if ret != self.futu.RET_OK:
                raise FutuUnavailable(str(data))
            holdings = []
            for row in _records(data):
                code = str(row.get("code", ""))
                quantity = float(row.get("qty", 0) or 0)
                if not code.startswith("US.") or quantity <= 0 or parse_option_code(code):
                    continue
                holdings.append({"code":code,"symbol":code.split(".",1)[1],"stock_name":str(row.get("stock_name", "")),"quantity":quantity,"market_value":float(row.get("market_val", 0) or 0)})
            return holdings
        finally:
            ctx.close()
