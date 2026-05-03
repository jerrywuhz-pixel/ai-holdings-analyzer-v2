import unittest
from pathlib import Path


class SellPutGatewayTests(unittest.TestCase):
    def test_sellput_cron_route_is_registered(self):
        gateway_source = Path("openclaw/gateway_app.py").read_text()

        self.assertIn('@app.post("/api/cron/sellput-score")', gateway_source)
        self.assertIn("HermesSellPutService", gateway_source)
        self.assertIn("evaluate_open_with_futu", gateway_source)


if __name__ == "__main__":
    unittest.main()
