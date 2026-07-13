# Cookie Clicker Stock Market Monitor

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)
[![Python 3](https://img.shields.io/badge/Python-3.x-3776AB.svg?logo=python&logoColor=white)](https://www.python.org/)

A dependency-free local dashboard that reads Cookie Clicker's Steam save and
tracks Bank Stock Market prices over time.

Use observed highs and lows to make better buy and sell decisions, or monitor
the market while Cookie Clicker runs in the background.

<p align="center">
  <img width="100%" alt="Cookie Clicker Stock Market price table" src="https://github.com/user-attachments/assets/647b7b5d-b654-4f40-bab3-a99ab3ad86ac" />
</p>
<p align="center">
  <img width="100%" alt="Cookie Clicker Stock Market price history chart" src="https://github.com/user-attachments/assets/db7011aa-55a9-43c6-a5f7-3b05bc89dcdd" />
</p>

## Features

- Reads Steam `save.txt` files without modifying them.
- Records price history in a local SQLite database.
- Imports from a saved file path or manual upload.
- Automatically refreshes the save path every minute.
- Shows current prices, inventory, market mode, and observed highs and lows.
- Highlights goods below a configurable price threshold.
- Stores optional purchase-cost notes and highlights profitable prices.
- Compares multiple goods on an interactive price-history chart.
- Remembers dashboard preferences in browser local storage.
- Uses only the Python standard library—no packages to install.

## Requirements

- Python 3.9 or newer
- Cookie Clicker on Steam
- The Bank's Stock Market minigame unlocked

## Quick start

Clone the repository and start the dashboard:

```sh
git clone https://github.com/joaocjesus/cookie-clicker-stock-tracker.git
cd cookie-clicker-stock-tracker
python3 cookie_clicker_market_web.py
```

Open <http://127.0.0.1:8765>, then either:

1. Enter the complete path to the Steam `save.txt` and select **Read saved
   location**; or
2. Select **Upload save.txt** to import a manually copied save.

Enable automatic refresh to re-read the saved path once per minute.

## Finding the Steam save

The usual Windows location is:

```text
C:\Program Files (x86)\Steam\userdata\<SteamID>\1454400\remote\save.txt
```

If Steam is installed elsewhere, use that installation's `userdata` directory.
When the game runs on another computer, share or copy the file so it is
accessible from the computer running this dashboard.

## Command-line usage

Import one save:

```sh
python3 cookie_clicker_market.py snapshot --source /path/to/save.txt
```

Continuously watch a save:

```sh
python3 cookie_clicker_market.py watch --source /path/to/save.txt --interval 60
```

Export the timeline to CSV:

```sh
python3 cookie_clicker_market.py export --output market_prices.csv
```

Write the current prices to JSON:

```sh
python3 cookie_clicker_market.py snapshot \
  --source /path/to/save.txt \
  --json-output current_market.json
```

Run `python3 cookie_clicker_market.py <command> --help` for all options.

## Data and privacy

- The source save is read-only; the tool never writes to Steam's `userdata`
  directory.
- Price history is stored locally in `market.sqlite3`, which is created on the
  first import and local.
- Source paths, purchase-cost notes, chart selections, and display preferences
  are stored in the browser's local storage.
- The dashboard binds to `127.0.0.1` by default, so other devices cannot access
  it.
- A snapshot is added only when the save contents change.

The save contains the current market state, not historical prices. Observed
highs and lows therefore cover only snapshots collected by this tool.

## Development

Run the dependency-free test suite:

```sh
python3 -m unittest discover -s tests -v
```

The parser fails with a format error rather than silently recording incorrect
data if a future Cookie Clicker update changes the save layout.

Contributions and bug reports are welcome. Please open an issue before making a
large behavioral change.

## Disclaimer

Cookie Clicker is created by Orteil and Opti. This project is unofficial and is
not affiliated with or endorsed by the game's creators.

## License

Copyright © 2026 Joao Jesus.

Licensed under the [GNU General Public License v3.0](LICENSE). You may use,
modify, and redistribute this software, including commercially. Distributed
versions must remain GPL-licensed and retain the copyright and license notices.
