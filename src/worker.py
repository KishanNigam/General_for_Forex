from flask import Response, request
from pyodide.ffi import run_sync
from workers import wsgi

from app import create_app
from storage import R2JsonStore, StoreError


def _get_worker_environment():
    environment = request.environ.get("workers.env")
    if environment is None:
        raise StoreError("Cloudflare Worker environment bindings are unavailable.")
    return environment


def _storage_factory():
    try:
        bucket = _get_worker_environment().TRADING_DATA
    except AttributeError as exc:
        raise StoreError("The TRADING_DATA R2 binding is unavailable.") from exc
    return R2JsonStore(bucket, run_sync)


def _fetch_asset(path):
    assets = _get_worker_environment().ASSETS
    response = run_sync(assets.fetch(f"https://assets.local/{path}"))
    return Response(
        run_sync(response.bytes()),
        status=response.status,
        headers=response.headers,
    )


app = create_app(
    storage_factory=_storage_factory,
    initialize_storage=False,
    asset_fetcher=_fetch_asset,
)

Default = wsgi.entrypoint(app)
