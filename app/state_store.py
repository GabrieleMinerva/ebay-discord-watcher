import sqlite3
import time

class StateStore:
    def __init__(self, path):
        self.path = path
        self._init()

    def _init(self):
        con = sqlite3.connect(self.path)
        cur = con.cursor()
        cur.execute("""
        CREATE TABLE IF NOT EXISTS posted_items(
            query_name TEXT,
            item_id TEXT,
            posted_at INTEGER,
            PRIMARY KEY(query_name,item_id)
        )
        """)
        con.commit()
        con.close()

    def was_posted(self, query, item_id):
        con = sqlite3.connect(self.path)
        cur = con.cursor()
        cur.execute("SELECT 1 FROM posted_items WHERE query_name=? AND item_id=?",
                    (query,item_id))
        r = cur.fetchone()
        con.close()
        return r is not None

    def mark_posted(self, query_name: str, item_id: str, ts_epoch: int | None = None) -> None:
        if ts_epoch is None:
            ts_epoch = int(time.time())

        con = sqlite3.connect(self.path)
        cur = con.cursor()
        cur.execute(
            "INSERT OR IGNORE INTO posted_items(query_name,item_id,posted_at) VALUES (?,?,?)",
            (query_name, item_id, ts_epoch),
        )
        con.commit()
        con.close()
