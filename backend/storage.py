import json, sqlite3
from pathlib import Path


class Store:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.path = str(path)
        with self.connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS fills(
              deal_id TEXT PRIMARY KEY, order_id TEXT, code TEXT NOT NULL, trd_side TEXT NOT NULL,
              qty REAL NOT NULL, price REAL NOT NULL, create_time TEXT NOT NULL, fee REAL DEFAULT 0,
              raw_json TEXT NOT NULL, synced_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS marks(code TEXT PRIMARY KEY, mark_price REAL, updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE IF NOT EXISTS option_risk(
              code TEXT PRIMARY KEY, underlying_price REAL, implied_volatility REAL,
              exercise_probability REAL, price_basis TEXT, updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE IF NOT EXISTS stock_holdings(
              code TEXT PRIMARY KEY, symbol TEXT NOT NULL, stock_name TEXT, quantity REAL NOT NULL,
              market_value REAL, updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            """)

    def connect(self):
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        return db

    def upsert_fills(self, fills):
        inserted = 0
        with self.connect() as db:
            for f in fills:
                exists = db.execute("SELECT 1 FROM fills WHERE deal_id=?", (str(f.get("deal_id")),)).fetchone() is not None
                db.execute("""INSERT INTO fills(deal_id,order_id,code,trd_side,qty,price,create_time,fee,raw_json)
                VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(deal_id) DO UPDATE SET fee=excluded.fee,raw_json=excluded.raw_json""",
                (str(f.get("deal_id")),str(f.get("order_id","")),f.get("code"),str(f.get("trd_side")),float(f.get("qty",0)),float(f.get("price",0)),str(f.get("create_time")),float(f.get("fee",0)),json.dumps(f,ensure_ascii=False,default=str)))
                inserted += not exists
        return inserted

    def set_marks(self, marks):
        with self.connect() as db:
            db.executemany("INSERT INTO marks(code,mark_price) VALUES(?,?) ON CONFLICT(code) DO UPDATE SET mark_price=excluded.mark_price,updated_at=CURRENT_TIMESTAMP", marks.items())

    def set_option_risk(self, rows):
        if not rows:
            return
        with self.connect() as db:
            db.executemany("""INSERT INTO option_risk(code,underlying_price,implied_volatility,exercise_probability,price_basis)
              VALUES(:code,:underlying_price,:implied_volatility,:exercise_probability,:price_basis)
              ON CONFLICT(code) DO UPDATE SET underlying_price=excluded.underlying_price,
              implied_volatility=excluded.implied_volatility, exercise_probability=excluded.exercise_probability,
              price_basis=excluded.price_basis, updated_at=CURRENT_TIMESTAMP""", rows)

    def option_risk(self):
        with self.connect() as db:
            return {row["code"]: dict(row) for row in db.execute("SELECT code,underlying_price,implied_volatility,exercise_probability,price_basis,updated_at FROM option_risk")}

    def set_meta(self, values):
        with self.connect() as db:
            db.executemany("INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", values.items())

    def meta(self):
        with self.connect() as db:
            return {row["key"]: row["value"] for row in db.execute("SELECT key,value FROM meta")}

    def replace_holdings(self, holdings):
        with self.connect() as db:
            db.execute("DELETE FROM stock_holdings")
            db.executemany("INSERT INTO stock_holdings(code,symbol,stock_name,quantity,market_value) VALUES(?,?,?,?,?)", [(h["code"],h["symbol"],h.get("stock_name",""),h["quantity"],h.get("market_value")) for h in holdings])

    def holdings(self):
        with self.connect() as db:
            return [dict(row) for row in db.execute("SELECT code,symbol,stock_name,quantity,market_value,updated_at FROM stock_holdings ORDER BY symbol")]

    def rows(self):
        with self.connect() as db:
            fills=[dict(r) for r in db.execute("SELECT deal_id,order_id,code,trd_side,qty,price,create_time,fee FROM fills WHERE code LIKE 'US.%' ORDER BY create_time")]
            marks={r["code"]:r["mark_price"] for r in db.execute("SELECT code,mark_price FROM marks")}
        return fills, marks
