import sqlite3
from contextlib import contextmanager

from . import config


@contextmanager
def get_conn():
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def get_categories():
    """Return [(category, count), ...] ordered by count desc."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT category, COUNT(*) as cnt FROM prompts GROUP BY category ORDER BY cnt DESC"
        ).fetchall()
        return [(r["category"], r["cnt"]) for r in rows]


def get_prompts_by_category(category, gender=None):
    """List (id, title) prompts in a category.

    If `gender` ('male'/'female') is given, prefer prompts tagged with that
    gender or 'neutral', so a prompt written for one gender's subject isn't
    handed to a photo of the other. Falls back to the unfiltered list if
    filtering would leave nothing to choose from.
    """
    with get_conn() as conn:
        if gender:
            rows = conn.execute(
                "SELECT id, title FROM prompts WHERE category = ? "
                "AND (subject_gender = ? OR subject_gender = 'neutral' OR subject_gender IS NULL) "
                "ORDER BY id",
                (category, gender),
            ).fetchall()
            if rows:
                return [(r["id"], r["title"]) for r in rows]
        rows = conn.execute(
            "SELECT id, title FROM prompts WHERE category = ? ORDER BY id", (category,)
        ).fetchall()
        return [(r["id"], r["title"]) for r in rows]


def get_prompt_by_id(prompt_id):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM prompts WHERE id = ?", (prompt_id,)).fetchone()
        return dict(row) if row else None


def get_processed_asset_ids(kind="restore"):
    """Return the set of immich_asset_id values already recorded for this kind of run,
    so each worker (restore/design) tracks its own exclusion list independently."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT DISTINCT immich_asset_id FROM enhancement_runs WHERE kind = ?", (kind,)
        ).fetchall()
        return {r["immich_asset_id"] for r in rows}


def mark_prompt_used(prompt_id):
    with get_conn() as conn:
        conn.execute(
            "UPDATE prompts SET times_used = times_used + 1, last_used_at = datetime('now') WHERE id = ?",
            (prompt_id,),
        )
        conn.commit()


def record_enhancement_run(immich_asset_id, original_filename, prompt_id, output_path,
                            status="pending", error=None, immich_album_asset_id=None, kind="restore",
                            variant=None, meta=None):
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO enhancement_runs
               (immich_asset_id, original_filename, prompt_id, output_path,
                immich_album_asset_id, status, error, kind, variant, meta)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (immich_asset_id, original_filename, prompt_id, output_path,
             immich_album_asset_id, status, error, kind, variant, meta),
        )
        conn.commit()
        return cur.lastrowid


def get_uncollaged_filter_outputs(limit):
    """Return recent successful filter-worker runs not yet folded into a collage."""
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT id, immich_asset_id, output_path, variant FROM enhancement_runs
               WHERE kind = 'filter' AND status = 'success' AND used_in_collage = 0
               ORDER BY created_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_recent_variants(kind, limit):
    """Return the last `limit` successful runs' `variant` values for this kind,
    most recent first - used to force real rotation through a preset list
    (e.g. cartoon_pipeline excluding recently-used styles) instead of trusting
    an LLM's "best fit" pick alone, which can develop a strong favorite and
    never surface the rest of the list.

    Excludes variants ending in "_compare" (cartoon_pipeline's comparison-
    collage record) - that's a second row for the same style pick, not a
    separate pick, and would otherwise double-count a style's turn in the
    rotation window."""
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT variant FROM enhancement_runs
               WHERE kind = ? AND status = 'success' AND variant IS NOT NULL
                 AND variant NOT LIKE '%\\_compare' ESCAPE '\\'
               ORDER BY created_at DESC LIMIT ?""",
            (kind, limit),
        ).fetchall()
        return [r["variant"] for r in rows]


def get_ai_generated_asset_ids():
    """All immich_album_asset_id values we've ever uploaded ourselves, across every
    worker kind - used to keep our own outputs out of then-and-now candidate pools
    alongside the filename-based check in immich_client."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT DISTINCT immich_album_asset_id FROM enhancement_runs "
            "WHERE immich_album_asset_id IS NOT NULL"
        ).fetchall()
        return {r["immich_album_asset_id"] for r in rows}


def mark_collaged(run_ids):
    with get_conn() as conn:
        conn.executemany(
            "UPDATE enhancement_runs SET used_in_collage = 1 WHERE id = ?",
            [(run_id,) for run_id in run_ids],
        )
        conn.commit()


def get_run_history(kind=None, limit=None):
    """Return enhancement_runs joined with their prompt title/category, newest first."""
    query = """
        SELECT er.id, er.kind, er.immich_asset_id, er.original_filename,
               p.title AS prompt_title, p.category AS prompt_category,
               er.output_path, er.immich_album_asset_id, er.status, er.error, er.created_at
        FROM enhancement_runs er
        LEFT JOIN prompts p ON p.id = er.prompt_id
    """
    params = []
    if kind:
        query += " WHERE er.kind = ?"
        params.append(kind)
    query += " ORDER BY er.id DESC"
    if limit:
        query += " LIMIT ?"
        params.append(limit)
    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]
