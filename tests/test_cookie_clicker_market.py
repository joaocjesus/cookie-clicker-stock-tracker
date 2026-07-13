import sys
import base64
import tempfile
import unittest
from pathlib import Path


PROJECT_DIRECTORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIRECTORY))

from cookie_clicker_market import (
    GOOD_NAMES,
    SaveFormatError,
    import_contents,
    parse_snapshot,
)


def make_save() -> bytes:
    records = "!".join(
        f"{1625 + good_id}:1:27:100:{140 if good_id == 0 else 0}:0:0:0"
        for good_id in range(len(GOOD_NAMES))
    )
    bank = f"0,0,0,0,0:4:1:10:1: {records} 1,0,0"
    buildings = ["0,0,0,0,"] * 20
    buildings[2] = "120,120,0,0,"
    buildings[3] = "110,110,0,0,"
    buildings[4] = "110,110,0,0,"
    buildings[5] = bank
    details = "0;0;0;Test Bakery"
    decoded = "|".join(("2.053", "", details, "", "", ";".join(buildings)))
    return base64.b64encode(decoded.encode("ascii")) + b"%21END%21"


class ParseSnapshotTests(unittest.TestCase):
    def test_extracts_all_prices_from_a_save(self) -> None:
        snapshot = parse_snapshot(make_save())

        self.assertEqual(snapshot.game_version, "2.053")
        self.assertEqual(
            [price.name for price in snapshot.prices[:-1]], list(GOOD_NAMES[:-1])
        )
        self.assertEqual(len(snapshot.prices), 18)
        self.assertEqual(snapshot.prices[0].price, 16.25)
        self.assertEqual(snapshot.prices[0].inventory, 140)
        self.assertEqual(snapshot.prices[0].delta, 1.68)
        self.assertTrue(snapshot.prices[0].unlocked)
        self.assertEqual(snapshot.prices[4].name, "Nuts")
        self.assertEqual(snapshot.prices[8].name, "Cinnamon")
        self.assertEqual(snapshot.prices[-1].name, "Test Bakery")
        self.assertFalse(snapshot.prices[-1].unlocked)

    def test_rejects_invalid_saves(self) -> None:
        with self.assertRaises(SaveFormatError):
            parse_snapshot(b"not a Cookie Clicker save")

    def test_records_only_one_copy_of_duplicate_save_contents(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first, snapshot = import_contents(
                root / "market.sqlite3",
                Path("uploaded/save.txt"),
                1,
                make_save(),
            )
            second, _ = import_contents(
                root / "market.sqlite3",
                Path("uploaded/save.txt"),
                2,
                make_save(),
            )

            self.assertTrue(first)
            self.assertFalse(second)
            self.assertEqual(len(snapshot.prices), len(GOOD_NAMES))
            self.assertFalse((root / "archives").exists())