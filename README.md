# Cookie Clicker Stock Market Monitor

A dependency-free Python tool for the Steam version of Cookie Clicker. It reads
the save without modifying it, extracts the Bank Stock Market's **current**
prices, and stores a historical timeline in SQLite.

## Why use it?

The Stock Market only shows its current price in-game. This monitor records
historical prices so you can compare the current value with the lows and highs
you have observed, helping you decide when to buy or sell. It also keeps the
timeline updated while Cookie Clicker runs in the background, so you can check
market movement without bringing the game to the foreground.

## Safety and limits

- The Steam save is only read; the script never writes to Steam's `userdata`
  folder.
- Run the watcher on the Windows PC where Cookie Clicker is running. The game
  must be open for Stock Market prices to advance.
- A new record is stored only when the copied save's contents differ. Cookie
  Clicker autosaves periodically, so use a polling interval slightly longer
  than its autosave interval.

## Visual dashboard

Start the local dashboard:

    python cookie_clicker_market_web.py

Then open <http://127.0.0.1:8765>. It provides two import options:

- **Read saved location** reads the complete Windows Steam `save.txt` path.
  The path is kept only in that browser's local storage, so it is filled in
  next time the dashboard opens.
- **Upload save.txt** adds a manually copied save. This works even when the
  game runs on another PC.

The optional automatic refresh re-reads the saved source path once per minute.
The dashboard is bound to `127.0.0.1`, so no other device can connect to it.
It charts the selected good across imported snapshots, and the table lets you
switch between all 18 goods.

## Verify the parser

The test suite creates its own synthetic save and does not need a real game
save:

    python -m unittest discover -s tests -v

## Read the live Windows Steam save

The usual source location is:

    C:\Program Files (x86)\Steam\userdata\<SteamID>\1454400\remote\save.txt

If Steam was installed elsewhere, use that Steam installation's `userdata`
directory instead. Start the watcher with the complete path to the file:

    python cookie_clicker_market.py watch --source "C:\Program Files (x86)\Steam\userdata\<SteamID>\1454400\remote\save.txt" --interval 60

Press `Ctrl+C` to stop it. The default output files are placed beside the
script:

- `market.sqlite3` is the locally generated history database. It is created
  automatically on the first import.

## Export the timeline

Create a spreadsheet-friendly CSV from every saved snapshot:

    python cookie_clicker_market.py export --output market_prices.csv

Each row contains the local capture time, commodity, current price, owned
stock, mode, and price movement value from Cookie Clicker's save.

## Optional JSON output

For a single current-price JSON file, use:

    python cookie_clicker_market.py snapshot --json-output current_market.json

The parser is based on the current save fixture. If a future Cookie Clicker
update changes the save layout, the tool stops with a format error instead of
silently recording incorrect prices.