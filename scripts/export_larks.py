#!/usr/bin/env python3
"""Export yesterday's free-card larks (America/Chicago) from puzzles_prod.db to larks.json.

Only past days are ever exported, so upcoming puzzles never reach the public site.
Usage: export_larks.py <path/to/puzzles_prod.db> [out.json] [--date YYYY-MM-DD]
"""
import json
import sqlite3
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

SLOT_LABELS = {0: "Lark", 1: "Daily", 2: "Lingo"}
TYPE_LABELS = {"joke": ("😄", "Pun"), "idiom": ("💬", "Word Play")}


def chicago_yesterday():
    return (datetime.now(ZoneInfo("America/Chicago")).date() - timedelta(days=1)).isoformat()


def word_cells(w):
    r, c = w["start"]["row"], w["start"]["col"]
    n = len(w["word"]["word"])
    if w["direction"] == "across":
        return [(r, c + i) for i in range(n)]
    return [(r + i, c) for i in range(n)]


def export_puzzle(row):
    grid = json.loads(row["grid_data"])
    words = json.loads(row["words_data"])
    joke_ids = set(json.loads(row["joke_word_ids"] or "[]"))

    numbers = {}
    for w in words:
        numbers[(w["start"]["row"], w["start"]["col"])] = w["number"]

    joke_words = [w for w in words if w["word"]["id"] in joke_ids]
    joke_cells = {pos for w in joke_words for pos in word_cells(w)}
    joke_strings = {w["word"]["word"] for w in joke_words}

    cells = []
    for r, grid_row in enumerate(grid["cells"]):
        out_row = []
        for c, cell in enumerate(grid_row):
            if cell["type"] != "letter":
                out_row.append(None)
                continue
            out_row.append({
                "l": cell["value"],
                "n": numbers.get((r, c)),
                "j": (r, c) in joke_cells,
            })
        cells.append(out_row)

    # Same tokenising rule as Puzzle.punchlineTokens() in the app.
    tokens = []
    for raw in (row["joke_punchline"] or "").split(" "):
        clean = "".join(ch for ch in raw.upper() if ch.isalpha())
        if not clean:
            continue
        content = clean in joke_strings or any(s in clean for s in joke_strings)
        tokens.append({"t": clean, "c": content})

    emoji, type_label = TYPE_LABELS.get(row["joke_type"], ("😄", "Pun"))
    return {
        "slot": row["slot"],
        "label": SLOT_LABELS.get(row["slot"], "Lark"),
        "type": row["joke_type"],
        "typeEmoji": emoji,
        "typeLabel": type_label,
        "setup": row["joke_setup"],
        "punchline": row["joke_punchline"],
        "tokens": tokens,
        "explanation": row["joke_explanation"],
        "rows": row["grid_rows"],
        "cols": row["grid_cols"],
        "cells": cells,
        "jokeWords": [
            {"row": w["start"]["row"], "col": w["start"]["col"],
             "dir": w["direction"], "len": len(w["word"]["word"])}
            for w in joke_words
        ],
    }


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        sys.exit(__doc__)
    db_path = args[0]
    out_path = args[1] if len(args) > 1 else "larks.json"
    date = chicago_yesterday()
    if "--date" in sys.argv:
        date = sys.argv[sys.argv.index("--date") + 1]
    if date >= datetime.now(ZoneInfo("America/Chicago")).date().isoformat():
        sys.exit(f"Refusing to export {date}: only past days may be published.")

    db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    rows = db.execute(
        """SELECT p.* FROM puzzles p JOIN daily_packs d ON p.pack_id = d.id
           WHERE d.date = ? AND d.pack_type = 'free' ORDER BY p.slot""",
        (date,),
    ).fetchall()
    if not rows:
        sys.exit(f"No free pack found for {date}")

    data = {"date": date, "puzzles": [export_puzzle(r) for r in rows]}
    with open(out_path, "w") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
        f.write("\n")
    print(f"Exported {len(rows)} larks for {date} -> {out_path}")


if __name__ == "__main__":
    main()
