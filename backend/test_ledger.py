import unittest
from datetime import date, datetime
from backend.ledger import build_ledger, parse_option_code
from backend.server import breach_probability


class LedgerTests(unittest.TestCase):
    def test_parse_contract(self):
        self.assertEqual(parse_option_code("US.TSLA260918P00410000")["strike"],410)
        self.assertEqual(parse_option_code("US.TSLA260918P00410000")["option_type"],"Put")

    def test_fifo_partial_close(self):
        fills=[
          {"deal_id":"s1","order_id":"o1","code":"US.TSLA260918P00410000","trd_side":"SELL_SHORT","qty":2,"price":10,"fee":2,"create_time":"2026-09-01 10:00:00"},
          {"deal_id":"s2","order_id":"o2","code":"US.TSLA260918P00410000","trd_side":"SELL_SHORT","qty":1,"price":8,"fee":1,"create_time":"2026-09-02 10:00:00"},
          {"deal_id":"b1","order_id":"o3","code":"US.TSLA260918P00410000","trd_side":"BUY_BACK","qty":2.5,"price":4,"fee":2.5,"create_time":"2026-09-03 10:00:00"},
        ]
        result=build_ledger(fills,{"US.TSLA260918P00410000":3},date(2026,9,16))
        self.assertEqual(len(result["closed"]),2)
        self.assertEqual(result["positions"][0]["quantity"],.5)
        self.assertAlmostEqual(sum(x["pnl"] for x in result["closed"]),1395.0)

    def test_unmatched_buy_is_reconciliation(self):
        result=build_ledger([{"deal_id":"b","code":"US.NVDA261016C00210000","trd_side":"BUY_BACK","qty":1,"price":1,"create_time":"2026-09-03"}])
        self.assertEqual(len(result["reconciliation"]),1)

    def test_expired_short_is_realized_at_zero(self):
        result=build_ledger([{"deal_id":"s","code":"US.NVDA260101C00210000","trd_side":"SELL_SHORT","qty":1,"price":2,"fee":1,"create_time":"2025-12-20"}],today=date(2026,1,2))
        self.assertEqual(len(result["positions"]),0)
        self.assertEqual(result["closed"][0]["pnl"],199)
        self.assertEqual(result["closed"][0]["close_reason"],"到期结转")

    def test_long_option_round_trip_is_excluded(self):
        fills=[
          {"deal_id":"b","code":"US.MSFT270115C450000","trd_side":"BUY","qty":1,"price":45.5,"create_time":"2026-01-29 10:00:00"},
          {"deal_id":"s","code":"US.MSFT270115C450000","trd_side":"SELL","qty":1,"price":41.43,"create_time":"2026-01-29 11:00:00"},
        ]
        result=build_ledger(fills)
        self.assertEqual(result["positions"],[])
        self.assertEqual(result["closed"],[])

    def test_breach_probability_uses_iv_and_selected_spot(self):
        position={"expiry":"2026-10-16","option_type":"Call","strike":210}
        risk={"underlying_price":200,"implied_volatility":0.4,"price_basis":"前收盘价"}
        probability, note=breach_probability(position,risk,today=date(2026,9,18),now=datetime(2026,9,18,20))
        self.assertGreater(probability,0)
        self.assertLess(probability,100)
        self.assertIn("前收盘价",note)


if __name__ == "__main__": unittest.main()
