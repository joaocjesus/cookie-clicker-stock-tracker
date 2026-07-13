#!/usr/bin/env python3
"""Run the local Cookie Clicker Stock Market dashboard."""

from __future__ import annotations

import argparse
import json
import mimetypes
import sqlite3
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

from cookie_clicker_market import (
    DEFAULT_DATABASE,
    SaveFormatError,
    import_contents,
    read_stable_file,
)


SCRIPT_DIRECTORY = Path(__file__).resolve().parent
WEB_DIRECTORY = SCRIPT_DIRECTORY / "web"
MAX_UPLOAD_BYTES = 2 * 1024 * 1024


def load_history(database_path: Path) -> list[dict[str, object]]:
    """Return stored market data grouped into chronological snapshots."""
    if not database_path.exists():
        return []

    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(
            """
            SELECT s.id, s.captured_at, s.source_path, s.game_version,
                   p.good_id, p.good_name, p.inventory, p.mode, p.delta,
                     p.price, p.unlocked, p.hidden
            FROM snapshots AS s
            JOIN prices AS p ON p.snapshot_id = s.id
            ORDER BY s.id, p.good_id
            """
        ).fetchall()

    snapshots: list[dict[str, object]] = []
    active_id: int | None = None
    for row in rows:
        snapshot_id, captured_at, source_path, game_version, *price = row
        if snapshot_id != active_id:
            snapshots.append(
                {
                    "captured_at": captured_at,
                    "source_path": source_path,
                    "game_version": game_version,
                    "prices": [],
                }
            )
            active_id = snapshot_id
        snapshots[-1]["prices"].append(
            {
                "good_id": price[0],
                "name": price[1],
                "inventory": price[2],
                "mode": price[3],
                "delta": price[4],
                "price": price[5],
                "unlocked": bool(price[6]),
                "hidden": bool(price[7]),
            }
        )
    return snapshots


class DashboardHandler(SimpleHTTPRequestHandler):
    """Serve dashboard assets and a small JSON API, bound to localhost only."""

    database_path: Path

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, directory=str(WEB_DIRECTORY), **kwargs)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/api/history":
            self.respond_json(HTTPStatus.OK, {"snapshots": load_history(self.database_path)})
            return
        if self.path == "/":
            self.path = "/index.html"
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        try:
            if self.path == "/api/import-path":
                body = self.read_body()
                source_value = json.loads(body).get("source_path", "")
                if not isinstance(source_value, str) or not source_value.strip():
                    raise ValueError("Enter the full path to save.txt.")
                source_path = Path(source_value).expanduser().resolve()
                contents, source_mtime_ns = read_stable_file(source_path)
            elif self.path == "/api/import-upload":
                contents = self.read_body()
                source_path = Path("uploaded") / unquote(
                    self.headers.get("X-File-Name", "save.txt")
                ).replace("/", "_").replace("\\", "_")
                source_mtime_ns = int(datetime.now(UTC).timestamp() * 1_000_000_000)
            else:
                self.respond_json(HTTPStatus.NOT_FOUND, {"error": "Unknown API endpoint."})
                return

            inserted, snapshot = import_contents(
                self.database_path,
                source_path,
                source_mtime_ns,
                contents,
            )
            self.respond_json(
                HTTPStatus.OK,
                {
                    "inserted": inserted,
                    "game_version": snapshot.game_version,
                    "prices": len(snapshot.prices),
                },
            )
        except (OSError, ValueError, SaveFormatError, json.JSONDecodeError) as error:
            self.respond_json(HTTPStatus.BAD_REQUEST, {"error": str(error)})

    def read_body(self) -> bytes:
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError as error:
            raise ValueError("Invalid request length.") from error
        if not 0 < content_length <= MAX_UPLOAD_BYTES:
            raise ValueError("The uploaded save must be between 1 byte and 2 MB.")
        return self.rfile.read(content_length)

    def respond_json(self, status: HTTPStatus, body: dict[str, object]) -> None:
        content = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--host", default="127.0.0.1", help="Default: 127.0.0.1 (local only).")
    parser.add_argument("--port", type=int, default=8765, help="Default: 8765.")
    return parser


def main() -> int:
    arguments = build_parser().parse_args()
    DashboardHandler.database_path = arguments.database.resolve()
    server = ThreadingHTTPServer((arguments.host, arguments.port), DashboardHandler)
    print(f"Dashboard available at http://{arguments.host}:{arguments.port}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())