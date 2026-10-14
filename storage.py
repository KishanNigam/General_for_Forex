import json


class StoreError(RuntimeError):
    pass


class R2JsonStore:
    _GENERALS_KEY = "generals.json"
    _TRADES_KEY = "trades.json"

    def __init__(self, bucket, run_sync):
        self._bucket = bucket
        self._run_sync = run_sync

    def _read_array(self, key):
        try:
            stored_object = self._run_sync(self._bucket.get(key))
            if stored_object is None:
                return []
            value = json.loads(self._run_sync(stored_object.text()))
        except Exception as exc:
            raise StoreError(f"Could not read {key} from R2: {exc}") from exc
        if not isinstance(value, list) or any(
            not isinstance(item, dict) for item in value
        ):
            raise StoreError(f"{key} in R2 must contain a JSON array of objects.")
        return value

    def _write_array(self, key, value):
        payload = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
        try:
            self._run_sync(self._bucket.put(key, payload))
        except Exception as exc:
            raise StoreError(f"Could not write {key} to R2: {exc}") from exc

    def read(self):
        return (
            self._read_array(self._GENERALS_KEY),
            self._read_array(self._TRADES_KEY),
        )

    def save_generals(self, generals):
        self._write_array(self._GENERALS_KEY, generals)

    def save_trades(self, trades):
        self._write_array(self._TRADES_KEY, trades)

    def save_store(self, generals, trades):
        self.save_generals(generals)
        self.save_trades(trades)
