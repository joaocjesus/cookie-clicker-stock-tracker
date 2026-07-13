#!/usr/bin/env python3
"""Inspect Cookie Clicker Steam Stock Market saves and retain price history."""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import json
import sqlite3
import sys
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import unquote


SCRIPT_DIRECTORY = Path(__file__).resolve().parent
DEFAULT_SOURCE = SCRIPT_DIRECTORY / "save.txt"
DEFAULT_DATABASE = SCRIPT_DIRECTORY / "market.sqlite3"

# Stock Market goods are saved by position, not by name.
GOOD_NAMES = (
    "Cereals",
    "Chocolate",
    "Butter",
    "Sugar",
    "Nuts",
    "Salt",
    "Vanilla",
    "Eggs",
    "Cinnamon",
    "Cream",
    "Jam",
    "White chocolate",
    "Honey",
    "Cookies",
    "Recipes",
    "Subsidiaries",
    "Publicists",
    "Your bakery",
)
BANK_BUILDING_INDEX = 5
FIRST_MARKET_BUILDING_INDEX = 2


class SaveFormatError(ValueError):
    """Raised when a save does not contain recognizable Stock Market data."""


@dataclass(frozen=True)
class MarketPrice:
    good_id: int
    name: str
    inventory: int
    mode: int
    delta: float
    price: float
    unlocked: bool
    hidden: bool


@dataclass(frozen=True)
class MarketSnapshot:
    game_version: str
    prices: tuple[MarketPrice, ...]


def decode_save(encoded_save: bytes) -> str:
    """Decode Cookie Clicker's Base64 save, tolerating browser-style escaping."""
    try:
        encoded = unquote(encoded_save.decode("ascii").strip())
    except UnicodeDecodeError as error:
        raise SaveFormatError("The save is not ASCII Base64 text.") from error

    # Steam appends this marker after the Base64 payload.
    encoded = encoded.removesuffix("!END!")
    encoded += "=" * (-len(encoded) % 4)
    try:
        decoded = base64.b64decode(encoded, altchars=b"-_", validate=True)
    except ValueError as error:
        raise SaveFormatError("The save is not valid Base64 data.") from error

    # A checksum at the very end can contain non-UTF-8 bytes. The save fields
    # needed below are ASCII, so replacement preserves them.
    return decoded.decode("utf-8", errors="replace")


def parse_snapshot(encoded_save: bytes) -> MarketSnapshot:
    """Extract the current Bank Stock Market prices from a Steam save."""
    fields = decode_save(encoded_save).split("|")
    if len(fields) <= 5:
        raise SaveFormatError("The save does not contain the building data section.")

    buildings = fields[5].split(";")
    if len(buildings) <= BANK_BUILDING_INDEX:
        raise SaveFormatError("The save does not contain the Bank building entry.")

    bank_fields = buildings[BANK_BUILDING_INDEX].split(",", 4)
    if len(bank_fields) != 5:
        raise SaveFormatError("The Bank entry has an unexpected format.")

    market_save = bank_fields[4]
    _, separator, good_data = market_save.partition(" ")
    if not separator:
        raise SaveFormatError("The Bank minigame data is missing.")

    # The final token belongs to other Bank minigame state, not a commodity.
    good_data = good_data.rsplit(" ", 1)[0]
    records = good_data.split("!")
    if len(records) < len(GOOD_NAMES):
        raise SaveFormatError(
            f"Expected {len(GOOD_NAMES)} Stock Market goods; found {len(records)}."
        )

    game_details = fields[2].split(";")
    bakery_name = game_details[3] if len(game_details) > 3 else "Your bakery"

    prices: list[MarketPrice] = []
    for good_id, (name, record) in enumerate(zip(GOOD_NAMES, records)):
        values = record.split(":")
        if len(values) < 8:
            raise SaveFormatError(f"Stock Market record {good_id} is incomplete.")
        try:
            price = int(values[0]) / 100
            movement = int(values[2]) / 100
            previous_price = price - movement
            delta = (
                int((price / previous_price - 1) * 10_000) / 100
                if previous_price
                else 0
            )
            building_fields = buildings[FIRST_MARKET_BUILDING_INDEX + good_id].split(",")
            unlocked = len(building_fields) > 1 and int(building_fields[1]) > 0
            prices.append(
                MarketPrice(
                    good_id=good_id,
                    name=bakery_name if good_id == len(GOOD_NAMES) - 1 else name,
                    inventory=int(values[4]),
                    mode=int(values[1]),
                    delta=delta,
                    price=price,
                    unlocked=unlocked,
                    hidden=bool(int(values[5])),
                )
            )
        except ValueError as error:
            raise SaveFormatError(
                f"Stock Market record {good_id} contains an invalid number."
            ) from error

    return MarketSnapshot(game_version=fields[0], prices=tuple(prices))


def read_stable_file(path: Path, attempts: int = 3) -> tuple[bytes, int]:
    """Read a save only if it did not change during the copy operation."""
    for _ in range(attempts):
        before = path.stat()
        contents = path.read_bytes()
        after = path.stat()
        if before.st_mtime_ns == after.st_mtime_ns and before.st_size == after.st_size:
            return contents, after.st_mtime_ns
    raise OSError(f"{path} changed while it was being copied; try again shortly.")


def open_database(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS snapshots (
            id INTEGER PRIMARY KEY,
            captured_at TEXT NOT NULL,
            source_path TEXT NOT NULL,
            source_mtime_ns INTEGER NOT NULL,
            source_sha256 TEXT NOT NULL UNIQUE,
            game_version TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS prices (
            snapshot_id INTEGER NOT NULL REFERENCES snapshots(id) ON DELETE CASCADE,
            good_id INTEGER NOT NULL,
            good_name TEXT NOT NULL,
            inventory INTEGER NOT NULL,
            mode INTEGER NOT NULL,
            delta REAL NOT NULL,
            price REAL NOT NULL,
            unlocked INTEGER NOT NULL DEFAULT 1,
            hidden INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (snapshot_id, good_id)
        );
        """
    )
    columns = {row[1] for row in connection.execute("PRAGMA table_info(prices)")}
    if "price_tenths" in columns:
        connection.execute("ALTER TABLE prices RENAME COLUMN price_tenths TO price")
        columns.remove("price_tenths")
        columns.add("price")
    if "unlocked" not in columns:
        connection.execute("ALTER TABLE prices ADD COLUMN unlocked INTEGER NOT NULL DEFAULT 1")
    if "hidden" not in columns:
        connection.execute("ALTER TABLE prices ADD COLUMN hidden INTEGER NOT NULL DEFAULT 0")
    snapshot_columns = {
        row[1] for row in connection.execute("PRAGMA table_info(snapshots)")
    }
    if "archive_path" in snapshot_columns:
        connection.execute("UPDATE snapshots SET archive_path = '' WHERE archive_path <> ''")
    return connection


def store_snapshot(
    database_path: Path,
    source_path: Path,
    source_mtime_ns: int,
    contents: bytes,
    snapshot: MarketSnapshot,
) -> bool:
    """Store a new imported save. Returns False when its content was seen before."""
    content_hash = hashlib.sha256(contents).hexdigest()
    captured_at = datetime.now(UTC).isoformat()
    with open_database(database_path) as connection:
        existing = connection.execute(
            "SELECT id FROM snapshots WHERE source_sha256 = ?", (content_hash,)
        ).fetchone()
        if existing:
            return False

        snapshot_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(snapshots)")
        }
        if "archive_path" in snapshot_columns:
            cursor = connection.execute(
                """
                INSERT INTO snapshots (
                    captured_at, source_path, source_mtime_ns, source_sha256,
                    archive_path, game_version
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    captured_at,
                    str(source_path),
                    source_mtime_ns,
                    content_hash,
                    "",
                    snapshot.game_version,
                ),
            )
        else:
            cursor = connection.execute(
                """
                INSERT INTO snapshots (
                    captured_at, source_path, source_mtime_ns, source_sha256,
                    game_version
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    captured_at,
                    str(source_path),
                    source_mtime_ns,
                    content_hash,
                    snapshot.game_version,
                ),
            )
        connection.executemany(
            """
            INSERT INTO prices (
                snapshot_id, good_id, good_name, inventory, mode, delta, price,
                unlocked, hidden
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    cursor.lastrowid,
                    price.good_id,
                    price.name,
                    price.inventory,
                    price.mode,
                    price.delta,
                    price.price,
                    price.unlocked,
                    price.hidden,
                )
                for price in snapshot.prices
            ],
        )
    return True


def import_contents(
    database_path: Path,
    source_path: Path,
    source_mtime_ns: int,
    contents: bytes,
) -> tuple[bool, MarketSnapshot]:
    """Parse and record one save that has already been read safely."""
    snapshot = parse_snapshot(contents)
    inserted = store_snapshot(
        database_path,
        source_path,
        source_mtime_ns,
        contents,
        snapshot,
    )
    return inserted, snapshot


def snapshot_as_json(snapshot: MarketSnapshot) -> str:
    return json.dumps(
        {
            "game_version": snapshot.game_version,
            "prices": [asdict(price) for price in snapshot.prices],
        },
        indent=2,
    )


def print_prices(snapshot: MarketSnapshot) -> None:
    print(f"Cookie Clicker {snapshot.game_version} Stock Market")
    print(f"{'Good':<25} {'Price':>10} {'Owned':>8} {'Trend':>9}")
    for price in snapshot.prices:
        print(f"{price.name:<25} ${price.price:>9.2f} {price.inventory:>8} {price.delta:>+9.2f}")


def import_save(arguments: argparse.Namespace) -> bool:
    source_path = arguments.source.expanduser().resolve()
    contents, source_mtime_ns = read_stable_file(source_path)
    inserted, snapshot = import_contents(
        arguments.database,
        source_path,
        source_mtime_ns,
        contents,
    )
    if arguments.json_output:
        arguments.json_output.write_text(snapshot_as_json(snapshot) + "\n", encoding="utf-8")
    print_prices(snapshot)
    print("Imported a new save." if inserted else "Save already imported; prices shown above.")
    return inserted


def watch_saves(arguments: argparse.Namespace) -> None:
    print(f"Watching {arguments.source.expanduser()} every {arguments.interval:g} seconds. Press Ctrl+C to stop.")
    while True:
        try:
            import_save(arguments)
        except (OSError, SaveFormatError) as error:
            print(f"Not imported: {error}", file=sys.stderr)
        time.sleep(arguments.interval)


def export_prices(database_path: Path, output_path: Path) -> int:
    with open_database(database_path) as connection:
        rows = connection.execute(
            """
                 SELECT s.captured_at, s.source_mtime_ns, s.game_version,
                     p.good_id, p.good_name, p.inventory, p.mode, p.delta,
                     p.price, p.unlocked, p.hidden
            FROM snapshots AS s
            JOIN prices AS p ON p.snapshot_id = s.id
            ORDER BY s.id, p.good_id
            """
        ).fetchall()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.writer(output)
        writer.writerow(
            (
                "captured_at",
                "source_mtime_ns",
                "game_version",
                "good_id",
                "good_name",
                "inventory",
                "mode",
                "delta",
                "price",
                "unlocked",
                "hidden",
            )
        )
        writer.writerows(rows)
    return len(rows)


def add_storage_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--source",
        type=Path,
        default=DEFAULT_SOURCE,
        help="Steam save to read (default: save.txt beside this script).",
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=DEFAULT_DATABASE,
        help="SQLite history file to update (default: market.sqlite3).",
    )
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    snapshot_parser = commands.add_parser("snapshot", help="Copy, parse, and store one save.")
    add_storage_arguments(snapshot_parser)
    snapshot_parser.add_argument("--json-output", type=Path, help="Also write the current prices as JSON.")

    watch_parser = commands.add_parser("watch", help="Import saves repeatedly while the game runs.")
    add_storage_arguments(watch_parser)
    watch_parser.add_argument("--interval", type=float, default=30.0, help="Seconds between checks (default: 30).")

    export_parser = commands.add_parser("export", help="Export all imported prices as a CSV file.")
    export_parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    export_parser.add_argument("--output", type=Path, default=SCRIPT_DIRECTORY / "market_prices.csv")
    return parser


def main() -> int:
    parser = build_parser()
    arguments = parser.parse_args()
    try:
        if arguments.command == "snapshot":
            import_save(arguments)
        elif arguments.command == "watch":
            watch_saves(arguments)
        elif arguments.command == "export":
            count = export_prices(arguments.database, arguments.output)
            print(f"Exported {count} price rows to {arguments.output}.")
    except (OSError, SaveFormatError) as error:
        parser.error(str(error))
    except KeyboardInterrupt:
        print("\nStopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())