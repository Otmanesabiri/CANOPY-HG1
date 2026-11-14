"""SQLite time-series store: raw readings, hourly roll-ups, events, actuator log, key/value state."""
from __future__ import annotations
import functools, json, os, sqlite3, threading, time

SCHEMA = """
CREATE TABLE IF NOT EXISTS readings(ts REAL NOT NULL, sensor TEXT NOT NULL, value REAL NOT NULL);
CREATE INDEX IF NOT EXISTS readings_idx ON readings(sensor, ts);
CREATE TABLE IF NOT EXISTS hourly(hour INTEGER NOT NULL, sensor TEXT NOT NULL, n INTEGER, avg REAL, min REAL, max REAL,
  PRIMARY KEY(hour, sensor));
CREATE TABLE IF NOT EXISTS events(ts REAL NOT NULL, level TEXT NOT NULL, kind TEXT NOT NULL, message TEXT NOT NULL, data TEXT);
CREATE INDEX IF NOT EXISTS events_idx ON events(ts);
CREATE TABLE IF NOT EXISTS actuations(ts REAL NOT NULL, actuator TEXT NOT NULL, state INTEGER NOT NULL, source TEXT NOT NULL, reason TEXT);
CREATE TABLE IF NOT EXISTS kv(key TEXT PRIMARY KEY, value TEXT);
"""


def _locked(fn):
    @functools.wraps(fn)
    def w(self, *a, **k):
        with self.lock:
            return fn(self, *a, **k)
    return w


class Store:
    def __init__(self, path: str = ":memory:", raw_days: int = 30):
        if path != ":memory:":
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)      # guarded by self.lock
        self.lock = threading.RLock()
        self.db.execute("PRAGMA journal_mode=WAL"); self.db.execute("PRAGMA synchronous=NORMAL")
        self.db.executescript(SCHEMA)
        self.raw_days = raw_days

    @_locked
    def add_readings(self, ts: float, values: dict[str, float]):
        self.db.executemany("INSERT INTO readings VALUES(?,?,?)", [(ts, k, float(v)) for k, v in values.items() if v is not None])
        self.db.commit()

    @_locked
    def event(self, level: str, kind: str, message: str, data: dict | None = None, ts: float | None = None):
        self.db.execute("INSERT INTO events VALUES(?,?,?,?,?)", (ts or time.time(), level, kind, message, json.dumps(data) if data else None))
        self.db.commit()

    @_locked
    def actuation(self, ts: float, actuator: str, state: bool, source: str, reason: str = ""):
        self.db.execute("INSERT INTO actuations VALUES(?,?,?,?,?)", (ts, actuator, int(state), source, reason))
        self.db.commit()

    @_locked
    def events(self, since: float = 0, limit: int = 100, level: str | None = None) -> list[dict]:
        q = "SELECT ts, level, kind, message, data FROM events WHERE ts>=?" + (" AND level=?" if level else "") + " ORDER BY ts DESC LIMIT ?"
        args = (since, level, limit) if level else (since, limit)
        return [dict(ts=r[0], level=r[1], kind=r[2], message=r[3], data=json.loads(r[4]) if r[4] else None) for r in self.db.execute(q, args)]

    @_locked
    def actuations(self, since: float = 0, limit: int = 200) -> list[dict]:
        return [dict(ts=r[0], actuator=r[1], state=bool(r[2]), source=r[3], reason=r[4]) for r in
                self.db.execute("SELECT * FROM actuations WHERE ts>=? ORDER BY ts DESC LIMIT ?", (since, limit))]

    @_locked
    def history(self, sensor: str, since: float, until: float | None = None, bucket_s: int = 300) -> list[dict]:
        """Bucketed avg/min/max; transparently falls back to hourly roll-ups for ranges older than the raw window."""
        until = until or time.time()
        rows = self.db.execute(
            "SELECT CAST(ts/? AS INTEGER)*?, AVG(value), MIN(value), MAX(value), COUNT(*) FROM readings "
            "WHERE sensor=? AND ts>=? AND ts<=? GROUP BY 1 ORDER BY 1", (bucket_s, bucket_s, sensor, since, until)).fetchall()
        out = [dict(ts=r[0], avg=r[1], min=r[2], max=r[3], n=r[4]) for r in rows]
        first_raw = out[0]["ts"] if out else until
        old = self.db.execute("SELECT hour*3600, avg, min, max, n FROM hourly WHERE sensor=? AND hour*3600>=? AND hour*3600<? ORDER BY 1",
                              (sensor, since - 3600, first_raw - 3599)).fetchall()
        return [dict(ts=r[0], avg=r[1], min=r[2], max=r[3], n=r[4]) for r in old] + out

    @_locked
    def total(self, sensor: str, since: float, until: float | None = None) -> float:
        """Sum of a counter-style sensor (e.g. litres per poll interval)."""
        r = self.db.execute("SELECT COALESCE(SUM(value),0) FROM readings WHERE sensor=? AND ts>=? AND ts<=?",
                            (sensor, since, until or time.time())).fetchone()
        return float(r[0])

    @_locked
    def rollup(self, now: float | None = None):
        """Aggregate complete hours into `hourly`, then drop raw rows past the retention window."""
        now = now or time.time(); this_hour = int(now // 3600)
        self.db.execute(
            "INSERT OR REPLACE INTO hourly SELECT CAST(ts/3600 AS INTEGER) h, sensor, COUNT(*), AVG(value), MIN(value), MAX(value) "
            "FROM readings WHERE ts < ? GROUP BY h, sensor", (this_hour * 3600,))
        self.db.execute("DELETE FROM readings WHERE ts < ?", (now - self.raw_days * 86400,))
        self.db.execute("DELETE FROM events WHERE ts < ?", (now - 365 * 86400,))
        self.db.commit()

    @_locked
    def get(self, key: str, default=None):
        r = self.db.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
        return json.loads(r[0]) if r else default

    @_locked
    def set(self, key: str, value):
        self.db.execute("INSERT OR REPLACE INTO kv VALUES(?,?)", (key, json.dumps(value))); self.db.commit()
