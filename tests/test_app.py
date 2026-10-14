import json
import tempfile
import unittest
from pathlib import Path

from app import create_app


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


class JournalApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temp_dir.name)
        self.app = create_app(self.data_dir)
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    def tearDown(self):
        self.temp_dir.cleanup()

    def make_general(self, name):
        response = self.client.post("/api/generals", json={"name": name})
        self.assertEqual(response.status_code, 201, response.get_json())
        return response.get_json()

    def make_trade(self, general_id, **values):
        return self.client.post(
            f"/api/generals/{general_id}/trades", json=trade_payload(**values)
        )

    def test_separate_generals_keep_independent_records_and_persist_on_restart(self):
        first = self.make_general("My $20 Challenge")
        second = self.make_general("Funded Account")
        first_trade = self.make_trade(first["id"]).get_json()
        self.make_trade(second["id"], side="SELL")
        self.make_trade(first["id"], date="2026-10-14", pair="EURUSD")

        first_rows = self.client.get(f"/api/generals/{first['id']}/trades").get_json()
        second_rows = self.client.get(f"/api/generals/{second['id']}/trades").get_json()
        self.assertEqual(len(first_rows), 2)
        self.assertEqual(len(second_rows), 1)
        self.assertEqual([row["trade_number"] for row in first_rows], [1, 2])
        self.assertEqual(first_rows[0]["id"], first_trade["id"])

        restarted = create_app(self.data_dir).test_client()
        state = restarted.get("/api/state").get_json()
        self.assertEqual(len(state["generals"]), 2)
        self.assertEqual(len([row for row in state["trades"] if row["general_id"] == first["id"]]), 2)

    def test_trade_edit_preserves_identity_and_date_until_changed(self):
        general = self.make_general("Account")
        created = self.make_trade(general["id"]).get_json()
        response = self.client.put(
            f"/api/generals/{general['id']}/trades/{created['id']}",
            json=trade_payload(pair="GBPUSD", exit=2310),
        )
        self.assertEqual(response.status_code, 200)
        edited = response.get_json()
        self.assertEqual(edited["id"], created["id"])
        self.assertEqual(edited["date"], created["date"])
        self.assertEqual(edited["pair"], "GBPUSD")
        self.assertEqual(
            len(self.client.get(f"/api/generals/{general['id']}/trades").get_json()), 1
        )

    def test_deleting_trade_preserves_other_trades_and_renumbers(self):
        general = self.make_general("Account")
        first = self.make_trade(general["id"]).get_json()
        second = self.make_trade(general["id"], pair="EURUSD").get_json()
        response = self.client.delete(
            f"/api/generals/{general['id']}/trades/{first['id']}"
        )
        self.assertEqual(response.status_code, 200)
        remaining = self.client.get(f"/api/generals/{general['id']}/trades").get_json()
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0]["id"], second["id"])
        self.assertEqual(remaining[0]["trade_number"], 1)

    def test_rename_keeps_trades_linked_and_delete_general_removes_its_trades(self):
        first = self.make_general("Personal Account")
        second = self.make_general("Other Account")
        first_trade = self.make_trade(first["id"]).get_json()
        second_trade = self.make_trade(second["id"], side="SELL").get_json()
        renamed = self.client.patch(
            f"/api/generals/{first['id']}", json={"name": "Renamed Account"}
        )
        self.assertEqual(renamed.status_code, 200)
        self.assertEqual(
            self.client.get(f"/api/generals/{first['id']}/trades").get_json()[0]["id"],
            first_trade["id"],
        )
        self.assertEqual(self.client.delete(f"/api/generals/{first['id']}").status_code, 200)
        state = self.client.get("/api/state").get_json()
        self.assertEqual([item["id"] for item in state["generals"]], [second["id"]])
        self.assertEqual([item["id"] for item in state["trades"]], [second_trade["id"]])

    def test_names_are_required_and_unique_ignoring_case_and_spaces(self):
        self.assertEqual(self.client.post("/api/generals", json={"name": "  "}).status_code, 400)
        self.make_general("Funded Account")
        duplicate = self.client.post("/api/generals", json={"name": " funded account "})
        self.assertEqual(duplicate.status_code, 409)

    def test_required_and_numeric_validation(self):
        general = self.make_general("Account")
        cases = [
            (trade_payload(date=""), "Date is required."),
            (trade_payload(lot=-0.1), "Lot cannot be negative."),
            (trade_payload(entry="NaN"), "Entry must be a valid number."),
            (trade_payload(exit="not-a-number"), "Exit must be a valid number."),
            (trade_payload(capital_after_target=None), "Capital after target is required."),
            ({}, "Date is required."),
        ]
        for payload, expected in cases:
            with self.subTest(expected=expected):
                response = self.client.post(
                    f"/api/generals/{general['id']}/trades", json=payload
                )
                self.assertEqual(response.status_code, 400)
                self.assertIn(expected, response.get_json()["error"])
        self.assertEqual(self.client.get("/api/state").get_json()["trades"], [])

    def test_empty_files_are_treated_as_empty_and_corrupt_files_are_reported(self):
        (self.data_dir / "generals.json").write_text("", encoding="utf-8")
        self.assertEqual(self.client.get("/api/state").status_code, 200)
        (self.data_dir / "generals.json").write_text("{invalid", encoding="utf-8")
        response = self.client.get("/api/state")
        self.assertEqual(response.status_code, 500)
        self.assertIn("Could not read generals.json", response.get_json()["error"])
        self.assertEqual(
            (self.data_dir / "generals.json").read_text(encoding="utf-8"), "{invalid"
        )

    def test_json_data_files_are_created_separately(self):
        self.assertTrue((self.data_dir / "generals.json").exists())
        self.assertTrue((self.data_dir / "trades.json").exists())
        self.assertIsInstance(json.loads((self.data_dir / "generals.json").read_text()), list)
        self.assertIsInstance(json.loads((self.data_dir / "trades.json").read_text()), list)

    def test_landing_page_has_every_control_required_by_the_frontend(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        for element_id in (
            "add-general-button",
            "general-form",
            "general-name",
            "general-starting-capital",
            "general-error",
            "general-save-button",
            "edit-general-button",
            "trade-pnl",
            "meter-profit-arc",
            "meter-loss-arc",
            "rules-list",
        ):
            with self.subTest(element_id=element_id):
                self.assertIn(f'id="{element_id}"', html)
        self.assertTrue(self.app.config["TEMPLATES_AUTO_RELOAD"])

    def test_starting_capital_and_pnl_are_saved_without_changing_record_ids(self):
        general = self.make_general("Capital Account")
        self.assertNotIn("starting_capital", general)
        original = self.make_trade(general["id"], pnl=25.5).get_json()

        updated = self.client.patch(
            f"/api/generals/{general['id']}",
            json={"name": "Capital Account Renamed", "starting_capital": 500},
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.get_json()["id"], general["id"])
        self.assertEqual(updated.get_json()["starting_capital"], 500)
        self.assertEqual(updated.get_json()["name"], "Capital Account Renamed")

        edited = self.client.put(
            f"/api/generals/{general['id']}/trades/{original['id']}",
            json=trade_payload(pnl=-10.25),
        )
        self.assertEqual(edited.status_code, 200)
        self.assertEqual(edited.get_json()["id"], original["id"])
        self.assertEqual(edited.get_json()["pnl"], -10.25)

        zero_trade = self.make_trade(general["id"], pnl=0).get_json()
        unrecorded_trade = self.make_trade(general["id"]).get_json()
        self.assertEqual(zero_trade["pnl"], 0)
        self.assertIsNone(unrecorded_trade["pnl"])
        rows = self.client.get(f"/api/generals/{general['id']}/trades").get_json()
        self.assertEqual([row["id"] for row in rows], [original["id"], zero_trade["id"], unrecorded_trade["id"]])

    def test_legacy_records_without_new_fields_load_without_mutation(self):
        legacy_general = {
            "id": "legacy-general-id",
            "name": "Legacy Account",
            "created_at": "2025-01-01T00:00:00+00:00",
        }
        legacy_trade = {
            "id": "legacy-trade-id",
            "general_id": legacy_general["id"],
            "trade_number": 1,
            "date": "2025-01-01",
            "pair": "XAUUSD",
            "side": "BUY",
            "lot": 0.01,
            "entry": 2000,
            "exit": 2001,
            "capital_after_target": 20,
            "emotion": "Calm",
        }
        (self.data_dir / "generals.json").write_text(
            json.dumps([legacy_general]), encoding="utf-8"
        )
        (self.data_dir / "trades.json").write_text(
            json.dumps([legacy_trade]), encoding="utf-8"
        )
        client = create_app(self.data_dir).test_client()
        state = client.get("/api/state").get_json()
        self.assertEqual(state["generals"], [legacy_general])
        self.assertEqual(state["trades"], [legacy_trade])
        self.assertNotIn("starting_capital", state["generals"][0])
        self.assertNotIn("pnl", state["trades"][0])

    def test_pnl_and_starting_capital_validate_numeric_values(self):
        general = self.make_general("Validation Account")
        self.assertEqual(
            self.client.post(
                "/api/generals", json={"name": "Invalid Capital", "starting_capital": -1}
            ).status_code,
            400,
        )
        for invalid_pnl in ("NaN", "Infinity", "not-a-number", True):
            with self.subTest(pnl=invalid_pnl):
                response = self.make_trade(general["id"], pnl=invalid_pnl)
                self.assertEqual(response.status_code, 400)
                self.assertIn("P&L ($)", response.get_json()["error"])


if __name__ == "__main__":
    unittest.main()
