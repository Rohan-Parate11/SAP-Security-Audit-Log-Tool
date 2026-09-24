"""Shared helpers for rule modules. Not part of the public rules API."""
from collections import defaultdict

from ..storage.db import get_connection

# Memoizes fetch_events() within a single run_all_rules() pass - several
# rules request the identical (msg_codes, event_class, system_id, client)
# combination (AU3 five times, AU1 four times, across the 13 registered
# rules as of this writing), each independently re-querying and re-sorting
# the same large result set from scratch. Found live: on a ~670K-row
# events table, that redundancy alone made sync_findings() take ~98s for
# a single-day ad-hoc job, long enough that the Collect page's "running…"
# polling text looked stuck (it wasn't - see registry.py's run_all_rules()
# for why this is safe: no write happens between rule calls in one pass,
# so the same query is guaranteed to return the same rows).
# None = caching disabled (the default, for any fetch_events() call made
# outside of run_all_rules() - e.g. a script or a one-off rule test).
_cache: dict | None = None


def fetch_events(msg_codes=None, event_class=None, system_id=None, client=None):
    """Fetch normalized events ordered by user then time, optionally filtered.

    Returns a list of sqlite3.Row. Filtering by msg_code list or a single
    event_class covers what the current rules need; extend if a rule needs
    something richer.
    """
    cache_key = None
    if _cache is not None:
        cache_key = (tuple(sorted(msg_codes)) if msg_codes else None, event_class, system_id, client)
        if cache_key in _cache:
            return _cache[cache_key]

    conn = get_connection()
    try:
        clauses = []
        params = []
        if msg_codes:
            placeholders = ", ".join("?" for _ in msg_codes)
            clauses.append(f"msg_code IN ({placeholders})")
            params.extend(msg_codes)
        if event_class:
            clauses.append("event_class = ?")
            params.append(event_class)
        if system_id:
            clauses.append("source_system = ?")
            params.append(system_id)
        if client:
            clauses.append("client = ?")
            params.append(client)

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"SELECT * FROM events {where} ORDER BY user_id, event_timestamp"
        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()

    if _cache is not None:
        _cache[cache_key] = rows
    return rows


def group_by_user(rows):
    by_user = defaultdict(list)
    for row in rows:
        by_user[row["user_id"]].append(row)
    return by_user
