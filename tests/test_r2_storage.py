import json
import tempfile
import unittest
from pathlib import Path

from flask import Response

from app import create_app
from scripts.build_assets import build_assets
from storage import R2JsonStore


def trade_payload(**overrides):
    values = {
        "date": "2026-10-14",
        "pair": "XAUUSD",
        "side": "BUY",
        "lot": 0.1,
        "entry": 2300.5,
        "exit": 2305.25,
        "capital_after_target": 125.5,
        "emotion": "Calm",
        "pnl": None,
    }
    values.update(overrides)
    return values


class FakeR2Object:
    def __init__(self, value):
        self.value = value

    def text(self):
        return self.value


class FakeR2Bucket:
    def __init__(self):
        self.objects = {}

    def get(self, key):
        if key not in self.objects:
            return None
        return FakeR2Object(self.objects[key])

    def put(self, key, value):
        self.objects[key] = value


class R2JournalApiTests(unittest.TestCase):
    def setUp(self):
        self.bucket = FakeR2Bucket()
        self.app = create_app(
            storage_factory=lambda: R2JsonStore(self.bucket, lambda result: result),
            initialize_storage=False,
        )
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    def make_general(self, name):
        response = self.client.post("/api/generals", json={"name": name})
        self.assertEqual(response.status_code, 201, response.get_json())
        return response.get_json()

    def make_trade(self, general_id, **values):
        response = self.client.post(
            f"/api/generals/{general_id}/trades",
            json=trade_payload(**values),
        )
        self.assertEqual(response.status_code, 201, response.get_json())
        return response.get_json()

    def test_r2_crud_persistence_and_general_isolation(self):
        self.assertEqual(
            self.client.get("/healthz").get_json(),
            {"status": "ok", "storage": "r2"},
        )
        first = self.make_general("Personal Account")
        second = self.make_general("Funded Account")
        first_trade = self.make_trade(first["id"], pnl=40)
        second_trade = self.make_trade(second["id"], side="SELL", pnl=-12)

        edited = self.client.put(
            f"/api/generals/{first['id']}/trades/{first_trade['id']}",
            json=trade_payload(pair="EURUSD", pnl=55),
        )
        self.assertEqual(edited.status_code, 200)
        self.assertEqual(edited.get_json()["id"], first_trade["id"])
        self.assertEqual(edited.get_json()["pnl"], 55)

        deleted_trade = self.client.delete(
            f"/api/generals/{first['id']}/trades/{first_trade['id']}"
        )
        self.assertEqual(deleted_trade.status_code, 200)
        self.assertEqual(
            self.client.get(f"/api/generals/{first['id']}/trades").get_json(), []
        )
        self.assertEqual(
            self.client.get(f"/api/generals/{second['id']}/trades").get_json(),
            [second_trade],
        )

        deleted_general = self.client.delete(f"/api/generals/{first['id']}")
        self.assertEqual(deleted_general.status_code, 200)

        restarted = create_app(
            storage_factory=lambda: R2JsonStore(
                self.bucket, lambda result: result
            ),
            initialize_storage=False,
        ).test_client()
        state = restarted.get("/api/state").get_json()
        self.assertEqual(state["generals"], [second])
        self.assertEqual(state["trades"], [second_trade])
        self.assertEqual(
            set(self.bucket.objects),
            {"generals.json", "trades.json"},
        )
        self.assertEqual(json.loads(self.bucket.objects["generals.json"]), [second])
        self.assertEqual(json.loads(self.bucket.objects["trades.json"]), [second_trade])

    def test_r2_corrupt_json_fails_without_replacing_the_object(self):
        self.bucket.objects["generals.json"] = "{invalid"
        response = self.client.get("/api/state")
        self.assertEqual(response.status_code, 500)
        self.assertIn("Could not read generals.json from R2", response.get_json()["error"])
        self.assertEqual(self.bucket.objects["generals.json"], "{invalid")


class WorkerAssetTests(unittest.TestCase):
    def test_worker_frontend_routes_use_asset_binding_and_keep_api_routes(self):
        bucket = FakeR2Bucket()
        requested_assets = []

        def fetch_asset(path):
            requested_assets.append(path)
            return Response(path, content_type="text/plain")

        app = create_app(
            storage_factory=lambda: R2JsonStore(bucket, lambda result: result),
            initialize_storage=False,
            asset_fetcher=fetch_asset,
        )
        client = app.test_client()
        self.assertEqual(client.get("/").get_data(as_text=True), "index.html")
        self.assertEqual(
            client.get("/static/style.css").get_data(as_text=True),
            "static/style.css",
        )
        self.assertEqual(client.get("/api/state").status_code, 200)
        self.assertEqual(requested_assets, ["index.html", "static/style.css"])

    def test_built_frontend_contains_existing_scripts_rules_and_styles(self):
        project_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as output:
            build_assets(project_root, output)
            output_dir = Path(output)
            html = (output_dir / "index.html").read_text(encoding="utf-8")
            self.assertIn('href="/static/style.css"', html)
            self.assertIn('src="/static/rules.js"', html)
            self.assertIn('src="/static/script.js"', html)
            self.assertIn('id="rules-dialog"', html)
            self.assertEqual(
                (output_dir / "static" / "script.js").read_bytes(),
                (project_root / "static" / "script.js").read_bytes(),
            )
            self.assertEqual(
                (output_dir / "static" / "rules.js").read_bytes(),
                (project_root / "static" / "rules.js").read_bytes(),
            )


if __name__ == "__main__":
    unittest.main()
