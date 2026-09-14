"""SQLite 持久化：工程、快照、搜索结果、装配图。"""
import json
import os
import sqlite3
import time

DB_PATH = os.environ.get(
    "ORGANLAB_DB", os.path.join(os.path.dirname(__file__), "organlab.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    model_json  TEXT NOT NULL,
    created_at  REAL NOT NULL,
    updated_at  REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS snapshots (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id  INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    label       TEXT NOT NULL,
    model_json  TEXT NOT NULL,
    created_at  REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS search_runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id  INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    result_json TEXT NOT NULL,
    adopted_idx INTEGER,
    created_at  REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS drawings (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id  INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    kind        TEXT NOT NULL,
    svg         TEXT NOT NULL,
    created_at  REAL NOT NULL
);
"""


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    conn = get_db()
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


def list_projects():
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT id, name, created_at, updated_at FROM projects "
            "ORDER BY updated_at DESC").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def load_project(pid):
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
        if not row:
            return None
        return {"id": row["id"], "name": row["name"],
                "model": json.loads(row["model_json"]),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"]}
    finally:
        conn.close()


def create_project(name, model):
    conn = get_db()
    try:
        now = time.time()
        cur = conn.execute(
            "INSERT INTO projects(name, model_json, created_at, updated_at) "
            "VALUES(?,?,?,?)",
            (name, json.dumps(model, ensure_ascii=False), now, now))
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def save_project(pid, name, model):
    conn = get_db()
    try:
        conn.execute(
            "UPDATE projects SET name=?, model_json=?, updated_at=? WHERE id=?",
            (name, json.dumps(model, ensure_ascii=False), time.time(), pid))
        conn.commit()
    finally:
        conn.close()


def delete_project(pid):
    conn = get_db()
    try:
        conn.execute("DELETE FROM projects WHERE id=?", (pid,))
        conn.commit()
    finally:
        conn.close()


def add_snapshot(pid, label, model):
    conn = get_db()
    try:
        cur = conn.execute(
            "INSERT INTO snapshots(project_id,label,model_json,created_at) "
            "VALUES(?,?,?,?)",
            (pid, label, json.dumps(model, ensure_ascii=False), time.time()))
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def list_snapshots(pid):
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT id,label,created_at FROM snapshots WHERE project_id=? "
            "ORDER BY id DESC", (pid,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def load_snapshot(sid):
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM snapshots WHERE id=?",
                           (sid,)).fetchone()
        return None if not row else {
            "id": row["id"], "project_id": row["project_id"],
            "label": row["label"],
            "model": json.loads(row["model_json"])}
    finally:
        conn.close()


def save_search_run(pid, result, adopted_idx=None):
    conn = get_db()
    try:
        cur = conn.execute(
            "INSERT INTO search_runs(project_id,result_json,adopted_idx,"
            "created_at) VALUES(?,?,?,?)",
            (pid, json.dumps(result, ensure_ascii=False), adopted_idx,
             time.time()))
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def list_search_runs(pid):
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT id,adopted_idx,created_at FROM search_runs "
            "WHERE project_id=? ORDER BY id DESC", (pid,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def save_drawing(pid, kind, svg):
    conn = get_db()
    try:
        cur = conn.execute(
            "INSERT INTO drawings(project_id,kind,svg,created_at) "
            "VALUES(?,?,?,?)",
            (pid, kind, svg, time.time()))
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def latest_drawing(pid, kind):
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT id,svg,created_at FROM drawings WHERE project_id=? AND kind=? "
            "ORDER BY id DESC LIMIT 1", (pid, kind)).fetchone()
        return None if not row else dict(row)
    finally:
        conn.close()
