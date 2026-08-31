# -*- coding: utf-8 -*-
"""
銀座やしろ 公式サイト & 遠隔オーダーシステム
- トップページ / 遠隔オーダー / 管理者リアルタイム受注画面
- 決済: エアペイ（Airペイ オンライン決済の「決済リンク」方式）
    1) お客様が注文 → 2) 管理者にメール/LINEで即時通知
    3) 管理者がAirペイ管理画面で決済リンクを作成し、お客様へメール/LINEで送信
    4) 入金確認後、管理画面で「入金確認済み」に更新 → ご希望のタイミングで開栓
- 通知: Gmail SMTP / LINE Messaging API（どちらも未設定ならスキップ）
"""
import os
import json
import sqlite3
import threading
import queue
import uuid
import smtplib
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText

import requests
from flask import Flask, request, jsonify, render_template, Response

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "orders.db")

SHOP = {
    "name": "銀座やしろ",
    "genre": "銀座のミニクラブスナック",
    "zip": "104-0061",
    "address": "東京都中央区銀座8-7-21 三恵ビル3階",
    "tel": "03-3289-5223",
    "email": os.environ.get("SHOP_EMAIL", "kaori.bbp@gmail.com"),
    "line_url": os.environ.get("LINE_URL", "https://line.me/ti/p/QO8Afujo9H"),
    "instagram_url": os.environ.get("INSTAGRAM_URL", "https://www.instagram.com/ginza.yashiro/"),
    "x_url": os.environ.get("X_URL", "https://x.com/ginza_yashiro"),
    "litlink_url": os.environ.get("LITLINK_URL", "https://lit.link/KaoriLinoLeoGinza"),
    "map_query": "銀座やしろ 東京都中央区銀座8-7-21 三恵ビル3階",
    "maps_url": "https://maps.app.goo.gl/vAEweCniYg9m4dvF9",
}

ADMIN_KEY = os.environ.get("ADMIN_KEY", "yashiro-admin-2026")
BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000")

# エアペイ管理画面のURL（管理画面からワンクリックで開けるようにする）
AIRPAY_ADMIN_URL = os.environ.get("AIRPAY_ADMIN_URL", "https://merchant.airpayment.jp/")

app = Flask(__name__)

# ---------------------------------------------------------------- Grand Open
# 2026-09-07 00:00 (JST) に自動で本サイトへ切り替わる。
# それ以前はトップ/オーダーが「工事中ページ」を表示。
# オーナー確認用: URLに ?preview=1 を付けると公開前でも本サイトを閲覧できる。
JST = timezone(timedelta(hours=9))
OPEN_AT = datetime(2026, 9, 7, 0, 0, 0, tzinfo=JST)


def is_open():
    return datetime.now(JST) >= OPEN_AT


# ---------------------------------------------------------------- DB

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = db()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS orders (
            id TEXT PRIMARY KEY,
            created_at TEXT,
            customer_name TEXT,
            staff TEXT,
            message TEXT,
            open_timing TEXT,
            open_at TEXT,
            items TEXT,
            total INTEGER,
            status TEXT DEFAULT 'new',
            payment_status TEXT DEFAULT 'awaiting_link',
            payment_mode TEXT DEFAULT 'airpay',
            notified INTEGER DEFAULT 0
        )
        """
    )
    conn.commit()
    conn.close()


init_db()

# ---------------------------------------------------------------- Menu

def load_menu():
    with open(os.path.join(DATA_DIR, "menu.json"), encoding="utf-8") as f:
        return json.load(f)

# ---------------------------------------------------------------- Realtime (SSE)

subscribers = []
sub_lock = threading.Lock()


def broadcast(event):
    with sub_lock:
        dead = []
        for q in subscribers:
            try:
                q.put_nowait(event)
            except queue.Full:
                dead.append(q)
        for q in dead:
            subscribers.remove(q)

# ---------------------------------------------------------------- Notifications

def send_email(subject, body):
    host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ.get("SMTP_USER", "")
    pw = os.environ.get("SMTP_PASS", "")
    if not user or not pw:
        app.logger.info("[MAIL] SMTP未設定のためスキップ: %s", subject)
        return False
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = SHOP["email"]
    with smtplib.SMTP(host, port, timeout=15) as s:
        s.starttls()
        s.login(user, pw)
        s.send_message(msg)
    return True


def send_line(text):
    token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
    to = os.environ.get("LINE_OWNER_USER_ID", "")
    if not token or not to:
        app.logger.info("[LINE] Messaging API未設定のためスキップ")
        return False
    r = requests.post(
        "https://api.line.me/v2/bot/message/push",
        headers={"Authorization": "Bearer %s" % token,
                 "Content-Type": "application/json"},
        json={"to": to, "messages": [{"type": "text", "text": text}]},
        timeout=15,
    )
    return r.status_code == 200


def order_text(order):
    lines = [
        "🍾 遠隔オーダーが入りました",
        "注文番号: %s" % order["id"],
        "お名前: %s" % order["customer_name"],
        "指名スタッフ: %s" % (order["staff"] or "指名なし"),
        "開栓タイミング: %s" % order["open_timing"],
    ]
    if order["open_at"]:
        lines.append("開栓希望日時: %s" % order["open_at"])
    lines.append("---- ご注文内容 ----")
    for it in json.loads(order["items"]):
        lines.append("・%s × %d （¥%s）" % (it["name"], it["qty"], format(it["price"] * it["qty"], ",")))
    lines.append("合計: ¥%s" % format(order["total"], ","))
    if order["message"]:
        lines.append("---- メッセージ ----")
        lines.append(order["message"])
    lines.append("---- 次の対応 ----")
    lines.append("Airペイ管理画面で ¥%s の決済リンクを作成し、お客様へ送信してください。" % format(order["total"], ","))
    lines.append("管理画面: %s/admin?key=%s" % (BASE_URL, ADMIN_KEY))
    return "\n".join(lines)


def notify_owner(order):
    """メールとLINEへ並行通知（失敗しても注文自体は守る）"""
    text = order_text(order)

    def _run():
        try:
            send_email("【銀座やしろ】遠隔オーダー受付 #%s" % order["id"], text)
        except Exception as e:  # noqa
            app.logger.error("MAIL送信失敗: %s", e)
        try:
            send_line(text)
        except Exception as e:  # noqa
            app.logger.error("LINE送信失敗: %s", e)
        conn = db()
        conn.execute("UPDATE orders SET notified=1 WHERE id=?", (order["id"],))
        conn.commit()
        conn.close()

    threading.Thread(target=_run, daemon=True).start()

# ---------------------------------------------------------------- Pages

@app.route("/")
def index():
    if not is_open() and request.args.get("preview") != "1":
        return render_template("maintenance.html", shop=SHOP)
    menu = load_menu()
    return render_template("index.html", shop=SHOP, menu=menu)


@app.route("/order")
def order_page():
    if not is_open() and request.args.get("preview") != "1":
        return render_template("maintenance.html", shop=SHOP)
    menu = load_menu()
    return render_template("order.html", shop=SHOP, menu=menu)


@app.route("/recruit")
def recruit_page():
    if not is_open() and request.args.get("preview") != "1":
        return render_template("maintenance.html", shop=SHOP)
    return render_template("recruit.html", shop=SHOP)


@app.route("/order/success")
def order_success():
    order_id = request.args.get("order", "")
    conn = db()
    order = conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
    conn.close()
    return render_template("success.html", shop=SHOP, order=order)


# ---------------------------------------------------------------- APIs

def order_to_dict(row):
    return {
        "id": row["id"],
        "created_at": row["created_at"],
        "customer_name": row["customer_name"],
        "staff": row["staff"],
        "message": row["message"],
        "open_timing": row["open_timing"],
        "open_at": row["open_at"],
        "items": json.loads(row["items"]),
        "total": row["total"],
        "status": row["status"],
        "payment_status": row["payment_status"],
        "payment_mode": row["payment_mode"],
    }


@app.route("/api/checkout", methods=["POST"])
def checkout():
    data = request.get_json(force=True)
    menu = {i["id"]: i for i in load_menu()["items"]}

    items, total = [], 0
    for it in data.get("items", []):
        m = menu.get(it.get("id"))
        if not m:
            continue
        qty = max(1, min(99, int(it.get("qty", 1))))
        items.append({"id": m["id"], "name": m["name"], "price": m["price"], "qty": qty})
        total += m["price"] * qty
    if not items:
        return jsonify({"error": "商品が選択されていません。"}), 400

    customer = (data.get("customer_name") or "").strip()
    if not customer:
        return jsonify({"error": "お名前を入力してください。"}), 400

    order_id = uuid.uuid4().hex[:10]
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = db()
    conn.execute(
        """INSERT INTO orders
           (id, created_at, customer_name, staff, message, open_timing, open_at,
            items, total, status, payment_status, payment_mode)
           VALUES (?,?,?,?,?,?,?,?,?, 'new', 'awaiting_link', 'airpay')""",
        (
            order_id, now, customer,
            (data.get("staff") or "").strip(),
            (data.get("message") or "").strip(),
            data.get("open_timing", "now"),
            (data.get("open_at") or "").strip(),
            json.dumps(items, ensure_ascii=False),
            total,
        ),
    )
    conn.commit()
    order = conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
    conn.close()

    # 受注と同時に管理者へ通知 → 管理画面でエアペイ決済リンクを発行して送付
    notify_owner(dict(order))
    broadcast({"type": "order", "order": order_to_dict(order)})
    return jsonify({"mode": "airpay", "success_url": "/order/success?order=%s" % order_id})


@app.route("/api/admin/orders")
def admin_orders():
    if request.args.get("key") != ADMIN_KEY:
        return jsonify({"error": "unauthorized"}), 403
    conn = db()
    rows = conn.execute(
        "SELECT * FROM orders ORDER BY created_at DESC LIMIT 100"
    ).fetchall()
    conn.close()
    return jsonify([order_to_dict(r) for r in rows])


@app.route("/api/admin/orders/<order_id>/status", methods=["POST"])
def admin_update_status(order_id):
    if request.args.get("key") != ADMIN_KEY:
        return jsonify({"error": "unauthorized"}), 403
    status = (request.get_json(force=True) or {}).get("status", "new")
    if status not in ("new", "preparing", "opened", "done", "cancelled"):
        return jsonify({"error": "invalid status"}), 400
    conn = db()
    conn.execute("UPDATE orders SET status=? WHERE id=?", (status, order_id))
    conn.commit()
    conn.close()
    broadcast({"type": "status", "order_id": order_id, "status": status})
    return jsonify({"ok": True})


@app.route("/api/admin/stream")
def admin_stream():
    if request.args.get("key") != ADMIN_KEY:
        return Response("unauthorized", status=403)
    q = queue.Queue(maxsize=100)
    with sub_lock:
        subscribers.append(q)

    def gen():
        try:
            yield "data: {\"type\":\"connected\"}\n\n"
            while True:
                try:
                    event = q.get(timeout=25)
                    yield "data: %s\n\n" % json.dumps(event, ensure_ascii=False)
                except queue.Empty:
                    yield ": keepalive\n\n"
        finally:
            with sub_lock:
                if q in subscribers:
                    subscribers.remove(q)

    return Response(gen(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


PAYMENT_STATUSES = ("awaiting_link", "link_sent", "paid", "cancelled")


@app.route("/api/admin/orders/<order_id>/payment", methods=["POST"])
def admin_update_payment(order_id):
    """入金ステータス更新（決済リンク送付済み / 入金確認済み など）"""
    if request.args.get("key") != ADMIN_KEY:
        return jsonify({"error": "unauthorized"}), 403
    ps = (request.get_json(force=True) or {}).get("payment_status", "")
    if ps not in PAYMENT_STATUSES:
        return jsonify({"error": "invalid payment status"}), 400
    conn = db()
    conn.execute("UPDATE orders SET payment_status=? WHERE id=?", (ps, order_id))
    conn.commit()
    order = conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
    conn.close()
    if order:
        broadcast({"type": "payment", "order_id": order_id, "payment_status": ps})
    return jsonify({"ok": True})


@app.route("/admin")
def admin_page():
    key = request.args.get("key", "")
    if key != ADMIN_KEY:
        return "管理者キーが違います。正しいURLでアクセスしてください。", 403
    return render_template("admin.html", shop=SHOP, key=key, airpay_url=AIRPAY_ADMIN_URL)


@app.route("/health")
def health():
    return jsonify({"ok": True})


# ---------------------------------------------------------------- SEO
from flask import send_from_directory

@app.route("/robots.txt")
def robots_txt():
    return send_from_directory(app.static_folder, "robots.txt", mimetype="text/plain")

@app.route("/sitemap.xml")
def sitemap_xml():
    return send_from_directory(app.static_folder, "sitemap.xml", mimetype="application/xml")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    app.run(host="0.0.0.0", port=port, threaded=True)
