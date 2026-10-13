#!/usr/bin/env python3
"""
Chi Tiêu Thông Minh — Backend API + static file server
SQLite database, REST API, no localStorage.
Run: python3 server.py
Open: http://localhost:3000
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import uuid
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "data", "chi_tieu.db")
PUBLIC_DIR = os.path.join(BASE_DIR, "public")
PORT = int(os.environ.get("PORT", "3000"))


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def row_to_dict(row):
    if row is None:
        return None
    return dict(row)


def rows_to_list(rows):
    return [dict(r) for r in rows]


def json_body(handler):
    length = int(handler.headers.get("Content-Length") or 0)
    if length == 0:
        return {}
    raw = handler.rfile.read(length)
    return json.loads(raw.decode("utf-8"))


def send_json(handler, status, data):
    body = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")
    handler.end_headers()
    handler.wfile.write(body)


def send_file(handler, path):
    if not os.path.isfile(path):
        handler.send_error(404)
        return
    ext = os.path.splitext(path)[1].lower()
    types = {
        ".html": "text/html; charset=utf-8",
        ".js": "application/javascript; charset=utf-8",
        ".css": "text/css; charset=utf-8",
        ".json": "application/json; charset=utf-8",
        ".svg": "image/svg+xml",
        ".png": "image/png",
        ".ico": "image/x-icon",
    }
    ctype = types.get(ext, "application/octet-stream")
    with open(path, "rb") as f:
        data = f.read()
    handler.send_response(200)
    handler.send_header("Content-Type", ctype)
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


# --------------- API handlers ---------------

def api_categories(method, path, qs, body):
    conn = get_db()
    try:
        if method == "GET":
            rows = conn.execute("SELECT * FROM categories ORDER BY type, name").fetchall()
            return 200, rows_to_list(rows)
        if method == "POST":
            name = (body.get("name") or "").strip()
            typ = body.get("type")
            if not name or typ not in ("income", "expense"):
                return 400, {"error": "name và type (income|expense) là bắt buộc"}
            exists = conn.execute(
                "SELECT id FROM categories WHERE lower(name)=lower(?) AND type=?",
                (name, typ),
            ).fetchone()
            if exists:
                return 400, {"error": "Danh mục đã tồn tại"}
            cid = "c_" + uuid.uuid4().hex[:10]
            conn.execute("INSERT INTO categories (id, name, type) VALUES (?,?,?)", (cid, name, typ))
            conn.commit()
            row = conn.execute("SELECT * FROM categories WHERE id=?", (cid,)).fetchone()
            return 201, row_to_dict(row)
        if method == "DELETE":
            m = re.match(r"^/api/categories/([^/]+)$", path)
            if not m:
                return 404, {"error": "Not found"}
            cid = m.group(1)
            used = conn.execute(
                "SELECT COUNT(*) AS n FROM transactions WHERE category_id=?", (cid,)
            ).fetchone()["n"]
            if used:
                return 400, {"error": "Không thể xóa: danh mục đang được dùng trong giao dịch"}
            cur = conn.execute("DELETE FROM categories WHERE id=?", (cid,))
            conn.commit()
            if cur.rowcount == 0:
                return 404, {"error": "Không tìm thấy danh mục"}
            return 200, {"ok": True}
        return 405, {"error": "Method not allowed"}
    finally:
        conn.close()


def api_transactions(method, path, qs, body):
    conn = get_db()
    try:
        m_id = re.match(r"^/api/transactions/([^/]+)$", path)

        if method == "GET" and not m_id:
            sql = "SELECT * FROM transactions WHERE 1=1"
            params = []
            if qs.get("type"):
                sql += " AND type=?"
                params.append(qs["type"][0])
            if qs.get("category_id"):
                sql += " AND category_id=?"
                params.append(qs["category_id"][0])
            if qs.get("month") and qs.get("year"):
                sql += " AND strftime('%m', date)=? AND strftime('%Y', date)=?"
                params.append(qs["month"][0].zfill(2))
                params.append(qs["year"][0])
            if qs.get("keyword"):
                sql += " AND lower(ifnull(note,'')) LIKE ?"
                params.append("%" + qs["keyword"][0].lower() + "%")
            if qs.get("from"):
                sql += " AND date>=?"
                params.append(qs["from"][0])
            if qs.get("to"):
                sql += " AND date<=?"
                params.append(qs["to"][0])
            sql += " ORDER BY date DESC, created_at DESC"
            rows = conn.execute(sql, params).fetchall()
            return 200, rows_to_list(rows)

        if method == "GET" and m_id:
            row = conn.execute("SELECT * FROM transactions WHERE id=?", (m_id.group(1),)).fetchone()
            if not row:
                return 404, {"error": "Không tìm thấy giao dịch"}
            return 200, row_to_dict(row)

        if method == "POST":
            typ = body.get("type")
            amount = body.get("amount")
            date = body.get("date")
            category_id = body.get("category_id")
            note = (body.get("note") or "").strip()
            try:
                amount = float(amount)
            except (TypeError, ValueError):
                return 400, {"error": "Số tiền không hợp lệ"}
            if typ not in ("income", "expense") or amount <= 0 or not date or not category_id:
                return 400, {"error": "type, amount>0, date, category_id là bắt buộc"}
            cat = conn.execute("SELECT id FROM categories WHERE id=?", (category_id,)).fetchone()
            if not cat:
                return 400, {"error": "Danh mục không tồn tại"}
            tid = "t_" + uuid.uuid4().hex[:10]
            created = datetime.now().isoformat()
            conn.execute(
                "INSERT INTO transactions (id, type, amount, date, category_id, note, created_at) VALUES (?,?,?,?,?,?,?)",
                (tid, typ, amount, date, category_id, note, created),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM transactions WHERE id=?", (tid,)).fetchone()
            return 201, row_to_dict(row)

        if method == "PUT" and m_id:
            tid = m_id.group(1)
            existing = conn.execute("SELECT * FROM transactions WHERE id=?", (tid,)).fetchone()
            if not existing:
                return 404, {"error": "Không tìm thấy giao dịch"}
            typ = body.get("type", existing["type"])
            amount = body.get("amount", existing["amount"])
            date = body.get("date", existing["date"])
            category_id = body.get("category_id", existing["category_id"])
            note = body.get("note", existing["note"] or "")
            try:
                amount = float(amount)
            except (TypeError, ValueError):
                return 400, {"error": "Số tiền không hợp lệ"}
            if typ not in ("income", "expense") or amount <= 0 or not date or not category_id:
                return 400, {"error": "Dữ liệu không hợp lệ"}
            conn.execute(
                "UPDATE transactions SET type=?, amount=?, date=?, category_id=?, note=? WHERE id=?",
                (typ, amount, date, category_id, note, tid),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM transactions WHERE id=?", (tid,)).fetchone()
            return 200, row_to_dict(row)

        if method == "DELETE" and m_id:
            cur = conn.execute("DELETE FROM transactions WHERE id=?", (m_id.group(1),))
            conn.commit()
            if cur.rowcount == 0:
                return 404, {"error": "Không tìm thấy giao dịch"}
            return 200, {"ok": True}

        return 405, {"error": "Method not allowed"}
    finally:
        conn.close()


def api_budgets(method, path, qs, body):
    conn = get_db()
    try:
        m_id = re.match(r"^/api/budgets/([^/]+)$", path)

        if method == "GET" and not m_id:
            sql = "SELECT * FROM budgets WHERE 1=1"
            params = []
            if qs.get("month"):
                sql += " AND month=?"
                params.append(int(qs["month"][0]))
            if qs.get("year"):
                sql += " AND year=?"
                params.append(int(qs["year"][0]))
            sql += " ORDER BY category_id"
            rows = conn.execute(sql, params).fetchall()
            return 200, rows_to_list(rows)

        if method == "POST":
            month = int(body.get("month") or 0)
            year = int(body.get("year") or 0)
            category_id = body.get("category_id") or None
            if category_id == "":
                category_id = None
            try:
                limit_amount = float(body.get("limit_amount"))
            except (TypeError, ValueError):
                return 400, {"error": "limit_amount không hợp lệ"}
            if not (1 <= month <= 12) or year < 2000 or limit_amount <= 0:
                return 400, {"error": "month, year, limit_amount là bắt buộc và phải hợp lệ"}
            exists = conn.execute(
                "SELECT id FROM budgets WHERE month=? AND year=? AND ifnull(category_id,'')=ifnull(?, '')",
                (month, year, category_id),
            ).fetchone()
            if exists:
                return 400, {"error": "Đã có ngân sách cho danh mục này trong tháng"}
            bid = "b_" + uuid.uuid4().hex[:10]
            conn.execute(
                "INSERT INTO budgets (id, month, year, category_id, limit_amount) VALUES (?,?,?,?,?)",
                (bid, month, year, category_id, limit_amount),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM budgets WHERE id=?", (bid,)).fetchone()
            return 201, row_to_dict(row)

        if method == "PUT" and m_id:
            bid = m_id.group(1)
            existing = conn.execute("SELECT * FROM budgets WHERE id=?", (bid,)).fetchone()
            if not existing:
                return 404, {"error": "Không tìm thấy ngân sách"}
            month = int(body.get("month", existing["month"]))
            year = int(body.get("year", existing["year"]))
            category_id = body.get("category_id", existing["category_id"])
            if category_id == "":
                category_id = None
            limit_amount = float(body.get("limit_amount", existing["limit_amount"]))
            if limit_amount <= 0:
                return 400, {"error": "limit_amount phải > 0"}
            conn.execute(
                "UPDATE budgets SET month=?, year=?, category_id=?, limit_amount=? WHERE id=?",
                (month, year, category_id, limit_amount, bid),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM budgets WHERE id=?", (bid,)).fetchone()
            return 200, row_to_dict(row)

        if method == "DELETE" and m_id:
            cur = conn.execute("DELETE FROM budgets WHERE id=?", (m_id.group(1),))
            conn.commit()
            if cur.rowcount == 0:
                return 404, {"error": "Không tìm thấy ngân sách"}
            return 200, {"ok": True}

        return 405, {"error": "Method not allowed"}
    finally:
        conn.close()


def api_summary(method, path, qs, body):
    if method != "GET":
        return 405, {"error": "Method not allowed"}
    month = int((qs.get("month") or [datetime.now().month])[0])
    year = int((qs.get("year") or [datetime.now().year])[0])
    conn = get_db()
    try:
        mm = f"{month:02d}"
        yy = str(year)
        income = conn.execute(
            "SELECT COALESCE(SUM(amount),0) AS s FROM transactions WHERE type='income' AND strftime('%m',date)=? AND strftime('%Y',date)=?",
            (mm, yy),
        ).fetchone()["s"]
        expense = conn.execute(
            "SELECT COALESCE(SUM(amount),0) AS s FROM transactions WHERE type='expense' AND strftime('%m',date)=? AND strftime('%Y',date)=?",
            (mm, yy),
        ).fetchone()["s"]
        by_cat = conn.execute(
            """
            SELECT c.id, c.name, COALESCE(SUM(t.amount),0) AS total
            FROM categories c
            LEFT JOIN transactions t ON t.category_id=c.id AND t.type='expense'
              AND strftime('%m',t.date)=? AND strftime('%Y',t.date)=?
            WHERE c.type='expense'
            GROUP BY c.id
            HAVING total > 0
            ORDER BY total DESC
            """,
            (mm, yy),
        ).fetchall()
        return 200, {
            "month": month,
            "year": year,
            "total_income": income,
            "total_expense": expense,
            "balance": income - expense,
            "expense_by_category": rows_to_list(by_cat),
        }
    finally:
        conn.close()


def route_api(method, path, qs, body):
    if path == "/api/categories" or path.startswith("/api/categories/"):
        return api_categories(method, path, qs, body)
    if path == "/api/transactions" or path.startswith("/api/transactions/"):
        return api_transactions(method, path, qs, body)
    if path == "/api/budgets" or path.startswith("/api/budgets/"):
        return api_budgets(method, path, qs, body)
    if path == "/api/summary":
        return api_summary(method, path, qs, body)
    if path == "/api/health":
        return 200, {"ok": True, "db": os.path.exists(DB_PATH)}
    return 404, {"error": "API not found"}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print("[%s] %s" % (self.log_date_time_string(), fmt % args))

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def _handle(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        if path.startswith("/api/"):
            try:
                body = {}
                if self.command in ("POST", "PUT", "PATCH"):
                    body = json_body(self)
                status, data = route_api(self.command, path, qs, body)
                send_json(self, status, data)
            except Exception as e:
                send_json(self, 500, {"error": str(e)})
            return

        # static
        if path == "/" or path == "":
            path = "/index.html"
        # prevent path traversal
        safe = os.path.normpath(path.lstrip("/"))
        if safe.startswith(".."):
            self.send_error(403)
            return
        file_path = os.path.join(PUBLIC_DIR, safe)
        send_file(self, file_path)

    def do_GET(self):
        self._handle()

    def do_POST(self):
        self._handle()

    def do_PUT(self):
        self._handle()

    def do_DELETE(self):
        self._handle()


def main():
    if not os.path.exists(DB_PATH):
        print("ERROR: Database not found at", DB_PATH)
        print("Run init first or copy chi_tieu.db to data/")
        raise SystemExit(1)
    os.makedirs(PUBLIC_DIR, exist_ok=True)
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print("=" * 50)
    print("  Chi Tiêu Thông Minh – Backend + API")
    print("  Database:", DB_PATH)
    print("  URL:      http://localhost:%d" % PORT)
    print("  API:      http://localhost:%d/api/health" % PORT)
    print("=" * 50)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
        server.server_close()


if __name__ == "__main__":
    main()
