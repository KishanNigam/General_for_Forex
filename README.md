# Forex Trading Journal

A small journal for organizing trading records by General. The app runs on your computer and saves data in JSON files.

## Start the website on Windows

1. Open PowerShell in this project folder.
2. Create a Python environment:

   ```powershell
   py -m venv .venv
   ```

3. Activate it:

   ```powershell
   .\.venv\Scripts\Activate.ps1
   ```

4. Install the app package:

   ```powershell
   python -m pip install -r requirements.txt
   ```

5. Start the website:

   ```powershell
   python app.py
   ```

6. Open `http://127.0.0.1:5000` in your browser.
7. To stop the website, return to PowerShell and press `Ctrl+C`.

## Create and manage Generals

1. Select **Add General** on the home page.
2. Enter a name and, if known, a **Starting Capital (USD)** amount. Select **Save**. A new General opens automatically.
3. Select **Add Trade** to enter a trade. New trades appear after the earlier trades.
4. Enter the realized result in **P&L ($)**. This field is optional. Leave it blank if the result is not recorded. The app does not calculate P&L from Entry and Exit.
5. Use **Edit** or **Delete** in a trade row to manage that trade. Editing a trade's P&L updates its row color and the meter.
6. Select **Back to Generals** to see your accounts. Use **Open**, **Rename**, or **Delete** on a General card. **Edit General** in a journal lets you change the name or starting capital.
7. Deleting a General asks for confirmation and also deletes its trades.

## P&L meter

- Recorded positive P&L is shown with a green trade row and green ring section.
- Recorded negative P&L is shown with a red trade row and red ring section.
- Zero P&L and missing P&L use neutral rows.
- The meter adds positive P&L for Profit and the absolute value of negative P&L for Loss.
- Total Capital is Starting Capital plus recorded Profit minus recorded Loss. It is shown only when starting capital is set and every trade has a recorded P&L. Otherwise the meter says **Not set** or **Incomplete data**.
- Old records stay unchanged. Trades without a P&L field show **Not recorded** and make the total incomplete.
- All currency amounts use USD. **Capital after target** is not used as P&L.

## Saved data

- General details are saved in `data/generals.json`.
- Trade records are saved in `data/trades.json`; every trade stores the ID of its General.
- The files are created the first time the app starts. Changes are saved as you make them.
- Keep a backup copy of the `data` folder if you need to protect your journal.

The app is intended for one local user and one running server at a time. Its JSON files are not encrypted or synchronized to another device. Do not edit the files while the app is running. If a JSON file is damaged, the app reports a storage error instead of replacing the file with empty data.

## Trading rules popup

The popup appears when the page opens. Check every configured rule to close it. It appears again two minutes after it is closed. The rules are listed in `static/rules.js`; update that file to change them. The app does not store rule acknowledgements with your journal.

## Run tests

1. Install the package as shown above.
2. Run:

   ```powershell
   python -m unittest discover -s tests -v
   ```
