# Forex Trading Journal

A Flask journal for organizing trading records by General. The existing HTML,
CSS, JavaScript, CRUD API, JSON format, P&L meter, and mandatory trading-rules
popup are retained. Use local JSON storage on Windows or Cloudflare R2 when
deployed as a Python Worker.

## Run locally on Windows

Open PowerShell in the project folder:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python app.py
```

Open <http://127.0.0.1:5000>. Stop the server with **Ctrl+C**. The local
adapter stores Generals in `data\generals.json` and trades in
`data\trades.json`. Existing files are read as-is; the app creates an empty
file only when that file does not already exist. Cloudflare commands do not
change these local files.

To run the automated tests:

```powershell
python -m unittest discover -s tests -v
```

## Features and data

- Each General has its own trades. General and trade CRUD is available through
  the existing `/api` endpoints.
- Positive P&L is green, negative P&L is red, and missing or zero P&L is
  neutral. The circular meter totals recorded profit and loss.
- Total Capital is Starting Capital plus recorded Profit minus recorded Loss.
  It is shown only when starting capital is set and every trade has recorded
  P&L. Entry/Exit and **Capital after target** do not calculate P&L.
- The rules popup appears when the page opens and requires every rule to be
  checked. It returns two minutes after it is closed. Rules are configured in
  `static\rules.js`; acknowledgements are not saved.
- `GET /healthz` reads the configured data store and returns a JSON `status`
  of `ok` when storage is available.

## Prepare Cloudflare Workers

The Worker uses Cloudflare's supported Python Flask WSGI adapter and the
Workers Static Assets binding. The deployment configuration is
[`wrangler.jsonc`](./wrangler.jsonc); Python dependencies are in
[`pyproject.toml`](./pyproject.toml). General records and trades remain JSON
arrays stored separately in the R2 objects `generals.json` and `trades.json`.

### One-time Cloudflare setup

1. In the Cloudflare dashboard, open **R2 Object Storage** and create a bucket
   (for example, `forex-trading-journal-data`).
2. Edit `wrangler.jsonc` and replace
   `replace-with-your-r2-bucket-name` with your exact bucket name. Keep the
   binding name `TRADING_DATA` unchanged.
3. Install [Node.js](https://nodejs.org/) and [uv](https://docs.astral.sh/uv/)
   on the deployment computer. In PowerShell, install the Python Worker
   dependencies:

   ```powershell
   uv sync --group dev
   ```

4. Build the Worker asset folder from the existing Flask template and static
   files:

   ```powershell
   uv run python scripts\build_assets.py
   ```

   The generated `public` files are ignored by Git. Re-run this command after
   changing the template or frontend assets and before each deployment.

### Test the Worker locally

From the project folder, run:

```powershell
uv run pywrangler dev
```

In another PowerShell window, check the response:

```powershell
Invoke-RestMethod http://127.0.0.1:8787/healthz
Invoke-WebRequest http://127.0.0.1:8787/
```

The health response should include `status = ok` and `storage = r2`. Wrangler
uses its local R2 simulation in this mode; it does not use the production
bucket unless you explicitly configure remote bindings.

### Deploy from PowerShell

After choosing the R2 bucket and updating `wrangler.jsonc`:

```powershell
uv run python scripts\build_assets.py
uv run pywrangler deploy
```

Follow Wrangler's interactive Cloudflare sign-in in your own browser. No API
token or account credential belongs in this repository. Once deployed, open
the Worker URL shown by Wrangler and verify
`https://<your-worker>.<your-subdomain>.workers.dev/healthz` returns
`{"status":"ok","storage":"r2"}`. Also open the root URL and confirm the
journal loads its styles and scripts.

### Connect the GitHub repository

In the Cloudflare dashboard, go to **Workers & Pages**:

1. Select **Create application**, then **Import a repository** (or open an
   existing Worker and choose **Settings → Builds → Connect**).
2. Authorize GitHub in Cloudflare, select this repository and the branch to
   deploy, and set the project root to the repository root.
3. Set the **Build command** to
   `uv sync --group dev && uv run python scripts/build_assets.py`.
4. Set the **Deploy command** to `uv run pywrangler deploy`. Confirm the
   connected build environment has Node.js and `uv` available. Keep the
   Cloudflare Worker name consistent with `name` in `wrangler.jsonc`.
5. Save the Git connection. Pushes to the selected branch will build and
   deploy the Worker. Complete the first deployment from PowerShell above if
   the dashboard requires a Worker to exist before connecting the repository.

Cloudflare Workers Builds manages its own deployment authorization; do not
add a Cloudflare token to the repository. Bindings are configured by
`wrangler.jsonc`; ensure the connected Worker is using this configuration.

### Use existing local JSON records in R2 (optional)

The app does not automatically copy or delete local data. To seed a new,
empty R2 bucket, first back up the local `data` folder. In the Cloudflare
dashboard, open **R2 Object Storage → your bucket → Objects → Upload**, and
upload the contents of `data\generals.json` as the object named
`generals.json`; repeat for `data\trades.json` as `trades.json`. This does
not modify the local JSON files. Only seed an empty bucket: uploading an
object with an existing key replaces the cloud object. Verify both object
names in the dashboard before deploying.

## Important deployment privacy note

As requested, the Worker has **no authentication**. Its `workers.dev` URL and
all CRUD API endpoints are public; anyone who discovers the URL can read,
change, or delete the journal. Do not deploy real or sensitive trading data
unless you are comfortable with this exposure. Add Cloudflare Access or
application authentication before treating the deployed journal as private.
The local Windows app remains local to your machine.

R2 strongly-consistently persists each object, but R2 does not provide a
transaction spanning both JSON objects. Deleting a General and its trades
updates the two objects sequentially. Keep independent backups of important
data. The app is designed for one journal owner and does not provide separate
per-user accounts.

## Official Cloudflare references

- [Flask on Python Workers](https://developers.cloudflare.com/workers/languages/python/packages/flask/)
- [Python Workers](https://developers.cloudflare.com/workers/languages/python/)
- [Workers Static Assets](https://developers.cloudflare.com/workers/static-assets/)
- [R2 Workers API](https://developers.cloudflare.com/r2/api/workers/workers-api-reference/)
- [Workers Builds Git integration](https://developers.cloudflare.com/workers/ci-cd/builds/)
