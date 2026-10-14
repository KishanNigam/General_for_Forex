import json
import math
import os
import tempfile
import threading
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_from_directory

from storage import StoreError


GENERAL_NAME_LIMIT = 80
PAIR_LIMIT = 30
EMOTION_LIMIT = 80
TRADE_FIELDS = (
    "date",
    "pair",
    "side",
    "lot",
    "entry",
    "exit",
    "capital_after_target",
    "emotion",
)


def _read_json(path, default):
    if not path.exists():
        return default
    try:
        content = path.read_text(encoding="utf-8")
        if not content.strip():
            return default
        value = json.loads(content)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise StoreError(f"Could not read {path.name}: {exc}") from exc
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise StoreError(f"{path.name} must contain a JSON array of objects.")
    return value


def _stage_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as temp_file:
            temp_file.write(payload)
            temp_file.flush()
            os.fsync(temp_file.fileno())
    except Exception:
        try:
            Path(temp_name).unlink(missing_ok=True)
        except OSError:
            pass
        raise
    return Path(temp_name)


def _write_json(path, value):
    temp_path = _stage_json(path, value)
    try:
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _write_json_batch(changes):
    staged = {}
    originals = {}
    replaced = []
    try:
        for path, value in changes.items():
            staged[path] = _stage_json(path, value)
            originals[path] = path.read_bytes() if path.exists() else None
        for path, temp_path in staged.items():
            os.replace(temp_path, path)
            replaced.append(path)
    except Exception as exc:
        rollback_errors = []
        for path in reversed(replaced):
            try:
                original = originals[path]
                if original is None:
                    path.unlink(missing_ok=True)
                else:
                    fd, temp_name = tempfile.mkstemp(
                        prefix=f".{path.name}.rollback.", dir=path.parent
                    )
                    with os.fdopen(fd, "wb") as temp_file:
                        temp_file.write(original)
                        temp_file.flush()
                        os.fsync(temp_file.fileno())
                    os.replace(temp_name, path)
            except OSError as rollback_exc:
                rollback_errors.append(str(rollback_exc))
        detail = f"Could not save JSON data: {exc}"
        if rollback_errors:
            detail += f" Rollback also failed: {'; '.join(rollback_errors)}"
        raise StoreError(detail) from exc
    finally:
        for temp_path in staged.values():
            temp_path.unlink(missing_ok=True)


def _error(message, status):
    return jsonify({"error": message}), status


def _clean_text(value, field, limit):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required.")
    cleaned = value.strip()
    if len(cleaned) > limit:
        raise ValueError(f"{field} must be {limit} characters or fewer.")
    return cleaned


def _validate_trade(payload):
    if not isinstance(payload, dict):
        raise ValueError("Trade data must be an object.")
    cleaned = {}
    for field in TRADE_FIELDS:
        if field not in payload:
            raise ValueError(f"{field.replace('_', ' ').capitalize()} is required.")

    raw_date = _clean_text(payload["date"], "Date", 10)
    try:
        date.fromisoformat(raw_date)
    except ValueError as exc:
        raise ValueError("Date must be a valid date.") from exc
    cleaned["date"] = raw_date

    cleaned["pair"] = _clean_text(payload["pair"], "Pair", PAIR_LIMIT)
    side = _clean_text(payload["side"], "BUY/SELL", 4).upper()
    if side not in ("BUY", "SELL"):
        raise ValueError("BUY/SELL must be BUY or SELL.")
    cleaned["side"] = side

    for field in ("lot", "entry", "exit", "capital_after_target"):
        raw_number = payload[field]
        if isinstance(raw_number, bool) or raw_number is None or str(raw_number).strip() == "":
            raise ValueError(f"{field.replace('_', ' ').capitalize()} is required.")
        try:
            number = float(raw_number)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"{field.replace('_', ' ').capitalize()} must be a valid number."
            ) from exc
        if not math.isfinite(number):
            raise ValueError(
                f"{field.replace('_', ' ').capitalize()} must be a valid number."
            )
        if field == "lot" and number < 0:
            raise ValueError("Lot cannot be negative.")
        cleaned[field] = number

    raw_pnl = payload.get("pnl")
    if raw_pnl is None or (isinstance(raw_pnl, str) and not raw_pnl.strip()):
        cleaned["pnl"] = None
    else:
        if isinstance(raw_pnl, bool):
            raise ValueError("P&L ($) must be a valid number.")
        try:
            pnl = float(raw_pnl)
        except (TypeError, ValueError) as exc:
            raise ValueError("P&L ($) must be a valid number.") from exc
        if not math.isfinite(pnl):
            raise ValueError("P&L ($) must be a valid number.")
        cleaned["pnl"] = pnl

    cleaned["emotion"] = _clean_text(payload["emotion"], "Emotion", EMOTION_LIMIT)
    return cleaned


def _validate_starting_capital(value):
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, bool):
        raise ValueError("Starting Capital (USD) must be a valid number.")
    try:
        capital = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Starting Capital (USD) must be a valid number.") from exc
    if not math.isfinite(capital) or capital < 0:
        raise ValueError("Starting Capital (USD) must be a valid non-negative number.")
    return capital


def create_app(
    storage_dir=None,
    storage_factory=None,
    initialize_storage=True,
    asset_fetcher=None,
):
    app = Flask(__name__, static_folder=None)
    app.config["TEMPLATES_AUTO_RELOAD"] = True
    data_dir = Path(storage_dir) if storage_dir else Path(app.root_path) / "data"
    generals_path = data_dir / "generals.json"
    trades_path = data_dir / "trades.json"
    storage_lock = threading.RLock()
    app.config["DATA_DIR"] = data_dir
    app.config["STORAGE_BACKEND"] = "r2" if storage_factory else "local"

    def read_store():
        if storage_factory is not None:
            return storage_factory().read()
        generals = _read_json(generals_path, [])
        trades = _read_json(trades_path, [])
        return generals, trades

    def save_store(generals, trades):
        if storage_factory is not None:
            storage_factory().save_store(generals, trades)
            return
        _write_json_batch({generals_path: generals, trades_path: trades})

    def save_generals(generals):
        if storage_factory is not None:
            storage_factory().save_generals(generals)
            return
        _write_json(generals_path, generals)

    def save_trades(trades):
        if storage_factory is not None:
            storage_factory().save_trades(trades)
            return
        _write_json(trades_path, trades)

    def find_general(generals, general_id):
        return next((item for item in generals if item.get("id") == general_id), None)

    @app.errorhandler(StoreError)
    def handle_store_error(exc):
        app.logger.error("Journal storage operation failed: %s", exc)
        return _error(str(exc), 500)

    @app.get("/")
    def index():
        if asset_fetcher is not None:
            return asset_fetcher("index.html")
        return render_template("index.html")

    @app.get("/static/<path:filename>", endpoint="static")
    def static_files(filename):
        if asset_fetcher is not None:
            return asset_fetcher(f"static/{filename}")
        return send_from_directory(Path(app.root_path) / "static", filename)

    if asset_fetcher is not None:

        @app.get("/<path:asset_path>")
        def worker_static_fallback(asset_path):
            return asset_fetcher(asset_path)

    @app.get("/healthz")
    def health_check():
        with storage_lock:
            read_store()
        return jsonify({"status": "ok", "storage": app.config["STORAGE_BACKEND"]})

    @app.get("/api/state")
    def get_state():
        with storage_lock:
            generals, trades = read_store()
        return jsonify({"generals": generals, "trades": trades})

    @app.post("/api/generals")
    def add_general():
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return _error("General data must be an object.", 400)
        try:
            name = _clean_text(payload.get("name"), "General name", GENERAL_NAME_LIMIT)
            starting_capital = _validate_starting_capital(
                payload.get("starting_capital")
            )
        except ValueError as exc:
            return _error(str(exc), 400)
        with storage_lock:
            generals, trades = read_store()
            if any(item.get("name", "").strip().casefold() == name.casefold() for item in generals):
                return _error("A General with that name already exists.", 409)
            general = {
                "id": str(uuid.uuid4()),
                "name": name,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            if starting_capital is not None:
                general["starting_capital"] = starting_capital
            generals.append(general)
            save_generals(generals)
        return jsonify(general), 201

    @app.patch("/api/generals/<general_id>")
    def rename_general(general_id):
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return _error("General data must be an object.", 400)
        try:
            name = (
                _clean_text(payload["name"], "General name", GENERAL_NAME_LIMIT)
                if "name" in payload
                else None
            )
            starting_capital = (
                _validate_starting_capital(payload["starting_capital"])
                if "starting_capital" in payload
                else ...
            )
        except ValueError as exc:
            return _error(str(exc), 400)
        with storage_lock:
            generals, _ = read_store()
            general = find_general(generals, general_id)
            if general is None:
                return _error("General not found.", 404)
            if name is not None and any(
                item["id"] != general_id
                and item.get("name", "").strip().casefold() == name.casefold()
                for item in generals
            ):
                return _error("A General with that name already exists.", 409)
            if name is not None:
                general["name"] = name
            if starting_capital is not ...:
                if starting_capital is None:
                    general.pop("starting_capital", None)
                else:
                    general["starting_capital"] = starting_capital
            save_generals(generals)
        return jsonify(general)

    @app.delete("/api/generals/<general_id>")
    def delete_general(general_id):
        with storage_lock:
            generals, trades = read_store()
            if find_general(generals, general_id) is None:
                return _error("General not found.", 404)
            remaining_generals = [item for item in generals if item["id"] != general_id]
            remaining_trades = [
                item for item in trades if item.get("general_id") != general_id
            ]
            save_store(remaining_generals, remaining_trades)
        return jsonify({"deleted": general_id})

    @app.get("/api/generals/<general_id>/trades")
    def get_trades(general_id):
        with storage_lock:
            generals, trades = read_store()
            if find_general(generals, general_id) is None:
                return _error("General not found.", 404)
            result = [item for item in trades if item.get("general_id") == general_id]
        return jsonify(result)

    @app.post("/api/generals/<general_id>/trades")
    def add_trade(general_id):
        try:
            trade_values = _validate_trade(request.get_json(silent=True))
        except ValueError as exc:
            return _error(str(exc), 400)
        with storage_lock:
            generals, trades = read_store()
            if find_general(generals, general_id) is None:
                return _error("General not found.", 404)
            own_trades = [item for item in trades if item.get("general_id") == general_id]
            trade = {
                "id": str(uuid.uuid4()),
                "general_id": general_id,
                "trade_number": len(own_trades) + 1,
                **trade_values,
            }
            trades.append(trade)
            save_trades(trades)
        return jsonify(trade), 201

    @app.put("/api/generals/<general_id>/trades/<trade_id>")
    def edit_trade(general_id, trade_id):
        try:
            trade_values = _validate_trade(request.get_json(silent=True))
        except ValueError as exc:
            return _error(str(exc), 400)
        with storage_lock:
            generals, trades = read_store()
            if find_general(generals, general_id) is None:
                return _error("General not found.", 404)
            trade = next(
                (
                    item
                    for item in trades
                    if item.get("id") == trade_id
                    and item.get("general_id") == general_id
                ),
                None,
            )
            if trade is None:
                return _error("Trade not found.", 404)
            trade.update(trade_values)
            save_trades(trades)
        return jsonify(trade)

    @app.delete("/api/generals/<general_id>/trades/<trade_id>")
    def delete_trade(general_id, trade_id):
        with storage_lock:
            generals, trades = read_store()
            if find_general(generals, general_id) is None:
                return _error("General not found.", 404)
            selected = next(
                (
                    item
                    for item in trades
                    if item.get("id") == trade_id
                    and item.get("general_id") == general_id
                ),
                None,
            )
            if selected is None:
                return _error("Trade not found.", 404)
            remaining = [item for item in trades if item.get("id") != trade_id]
            own_remaining = [
                item for item in remaining if item.get("general_id") == general_id
            ]
            for number, item in enumerate(own_remaining, start=1):
                item["trade_number"] = number
            save_trades(remaining)
        return jsonify({"deleted": trade_id})

    if storage_factory is None and initialize_storage:
        generals_path.parent.mkdir(parents=True, exist_ok=True)
        if not generals_path.exists():
            _write_json(generals_path, [])
        if not trades_path.exists():
            _write_json(trades_path, [])

    return app


app = create_app(initialize_storage=False)


if __name__ == "__main__":
    create_app().run()
