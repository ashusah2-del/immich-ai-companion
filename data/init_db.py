#!/usr/bin/env python3
"""Initialize the persistent prompts database and import seed sources."""
import json
import sqlite3
from pathlib import Path

DATA_DIR = Path(__file__).parent
DB_PATH = DATA_DIR / "prompts.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS prompts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,           -- e.g. 'compiled', 'promptplum'
    source_url TEXT,
    slug TEXT,
    title TEXT,
    category TEXT,
    ai_tools TEXT,                  -- JSON array as text
    prompt_text TEXT NOT NULL,
    image_url TEXT,
    times_used INTEGER NOT NULL DEFAULT 0,
    last_used_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    subject_gender TEXT,            -- male|female|neutral, backfilled by classify_gender.py
    UNIQUE(source, slug)
);

CREATE TABLE IF NOT EXISTS enhancement_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    immich_asset_id TEXT NOT NULL,
    original_filename TEXT,
    prompt_id INTEGER REFERENCES prompts(id),
    output_path TEXT,
    immich_album_asset_id TEXT,
    status TEXT NOT NULL DEFAULT 'pending',  -- pending|success|failed
    error TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    kind TEXT NOT NULL DEFAULT 'restore',  -- restore|design|filter|collage
    variant TEXT,                          -- filter preset name or collage template name
    used_in_collage INTEGER NOT NULL DEFAULT 0,  -- filter runs: already composited into a collage?
    meta TEXT                              -- JSON, e.g. collage member enhancement_runs.id list
);
"""


def import_compiled(conn):
    path = DATA_DIR / "prompts_seed.json"
    if not path.exists():
        return 0
    data = json.loads(path.read_text(encoding="utf-8"))
    n = 0
    for p in data["prompts"]:
        slug = str(p["id"])
        before = conn.total_changes
        conn.execute(
            """INSERT OR IGNORE INTO prompts
               (source, source_url, slug, title, category, ai_tools, prompt_text)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            ("compiled", None, slug, p["title"], p["category"], None, p["prompt"]),
        )
        n += conn.total_changes - before
    return n


def import_promptplum(conn):
    path = DATA_DIR / "promptplum_prompts.json"
    if not path.exists():
        return 0
    data = json.loads(path.read_text(encoding="utf-8"))
    n = 0
    for p in data:
        if not p.get("promptText") or not p.get("slug"):
            continue
        before = conn.total_changes
        conn.execute(
            """INSERT OR IGNORE INTO prompts
               (source, source_url, slug, title, category, ai_tools, prompt_text, image_url)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                "promptplum",
                p.get("url"),
                p["slug"],
                p.get("title"),
                p.get("category"),
                json.dumps(p.get("aiTools")) if p.get("aiTools") else None,
                p["promptText"],
                p.get("image"),
            ),
        )
        n += conn.total_changes - before
    return n


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    n1 = import_compiled(conn)
    n2 = import_promptplum(conn)
    conn.commit()
    total = conn.execute("SELECT COUNT(*) FROM prompts").fetchone()[0]
    by_source = conn.execute("SELECT source, COUNT(*) FROM prompts GROUP BY source").fetchall()
    print(f"Inserted: compiled={n1} promptplum={n2}")
    print(f"Total prompts in DB: {total}")
    for src, cnt in by_source:
        print(f"  {src}: {cnt}")
    conn.close()

    from classify_gender import main as classify_main
    classify_main()


if __name__ == "__main__":
    main()
