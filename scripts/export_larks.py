#!/usr/bin/env python3
"""Export the free-card larks (America/Chicago) to larks.json.

- "today": today's puzzles as blank grids with clues. No letters, answers or
  punchline text are exported, so the solution never reaches the public site.
- "days": solved puzzles for yesterday and the day before.
Nothing after today is ever exported.
Usage: export_larks.py <path/to/puzzles_prod.db> [out.json] [--date YYYY-MM-DD]
--date sets the most recent solved day (default: yesterday in Chicago).
"""
import json
import sqlite3
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

DAYS = 2  # yesterday and the day before
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


def export_puzzle(row, solved=True):
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
            out = {"n": numbers.get((r, c)), "j": (r, c) in joke_cells}
            if solved:
                out["l"] = cell["value"]
            out_row.append(out)
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
    if not solved:
        # Word lengths only; filler words become ✱ like the in-game card
        tokens = [{"len": len(t["t"])} if t["c"] else {"filler": True} for t in tokens]

    clues = {"across": [], "down": []}
    for w in sorted(words, key=lambda w: w["number"]):
        clues[w["direction"]].append({
            "n": w["number"],
            # Pun words have no clue: they're solved through their crossings
            "clue": (w.get("clue") or {}).get("clueText"),
            "pun": w["word"]["id"] in joke_ids,
            "len": len(w["word"]["word"]),
        })

    puzzle = {
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
        "clues": clues,
    }
    if not solved:
        for key in ("punchline", "explanation"):
            del puzzle[key]
    return puzzle


def load_pack(db, day, solved):
    rows = db.execute(
        """SELECT p.* FROM puzzles p JOIN daily_packs d ON p.pack_id = d.id
           WHERE d.date = ? AND d.pack_type = 'free' ORDER BY p.slot""",
        (day,),
    ).fetchall()
    if not rows:
        sys.exit(f"No free pack found for {day}")
    return {"date": day, "puzzles": [export_puzzle(r, solved) for r in rows]}


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
    newest = datetime.fromisoformat(date).date()
    today = load_pack(db, (newest + timedelta(days=1)).isoformat(), solved=False)
    days = [load_pack(db, (newest - timedelta(days=back)).isoformat(), solved=True)
            for back in range(DAYS)]

    with open(out_path, "w") as f:
        json.dump({"today": today, "days": days}, f, ensure_ascii=False, separators=(",", ":"))
        f.write("\n")
    print(f"Exported today {today['date']} (blank) and {', '.join(d['date'] for d in days)} -> {out_path}")


if __name__ == "__main__":
    main()
