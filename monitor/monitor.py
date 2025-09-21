import asyncio
import aiohttp
import aiosqlite
import yaml
import os
import time
import smtplib
from email.message import EmailMessage
import logging
import json

from aiohttp import web

logging.basicConfig(level=logging.INFO)
LOG = logging.getLogger("monitor")

DB_FILE = os.getenv("DB_FILE", "/data/monitor.db")
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "30"))  # seconds
TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "10"))
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
EMAIL_TO = os.getenv("EMAIL_TO", "")

TARGETS_FILE = os.getenv("TARGETS_FILE", "/app/targets.yml")

# States cache to send notifications only on change
state_cache = {}

async def send_telegram(text):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        LOG.debug("Telegram not configured")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    async with aiohttp.ClientSession() as sess:
        async with sess.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": text}) as resp:
            if resp.status != 200:
                LOG.warning("Telegram send failed: %s", await resp.text())

def send_email_sync(subject, body):
    if not SMTP_HOST or not EMAIL_TO:
        LOG.debug("Email not configured")
        return
    msg = EmailMessage()
    msg["From"] = SMTP_USER or "monitor@example.com"
    msg["To"] = EMAIL_TO
    msg["Subject"] = subject
    msg.set_content(body)
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as s:
            s.starttls()
            if SMTP_USER and SMTP_PASS:
                s.login(SMTP_USER, SMTP_PASS)
            s.send_message(msg)
    except Exception as e:
        LOG.exception("Sending email failed: %s", e)

async def notify(name, url, status, details):
    text = f"[{name}] {url} -> {status}\n{details}"
    await send_telegram(text)
    # run email sync in threadpool
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, send_email_sync, f"Monitor: {name} {status}", text)

async def init_db():
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS checks (
            id INTEGER PRIMARY KEY,
            name TEXT,
            url TEXT,
            status TEXT,
            http_code INTEGER,
            latency_ms INTEGER,
            ts INTEGER
        )
        """)
        await db.commit()

async def read_targets():
    with open(TARGETS_FILE, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    # expect list of {name: "...", url: "...", interval: ...}
    return data.get("targets", [])

async def check_once(session, target):
    name = target.get("name")
    url = target.get("url")
    try:
        start = time.time()
        async with session.get(url, timeout=TIMEOUT) as resp:
            latency = int((time.time() - start) * 1000)
            status = "UP" if resp.status < 500 else "DOWN"
            code = resp.status
            text_details = f"HTTP {code} in {latency}ms"
    except Exception as e:
        latency = None
        code = None
        status = "DOWN"
        text_details = str(e)

    # save to db
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("INSERT INTO checks (name, url, status, http_code, latency_ms, ts) VALUES (?, ?, ?, ?, ?, ?)",
                         (name, url, status, code, latency, int(time.time())))
        await db.commit()

    # notify on change
    old = state_cache.get(url)
    if old != status:
        state_cache[url] = status
        await notify(name, url, status, text_details)

    LOG.info("%s %s -> %s (%s)", name, url, status, text_details)

async def periodic_worker(target):
    interval = target.get("interval", CHECK_INTERVAL)
    async with aiohttp.ClientSession() as session:
        while True:
            await check_once(session, target)
            await asyncio.sleep(interval)

# Simple web dashboard
async def handle_index(request):
    async with aiosqlite.connect(DB_FILE) as db:
        cursor = await db.execute("SELECT name, url, status, http_code, latency_ms, ts FROM checks ORDER BY id DESC LIMIT 100")
        rows = await cursor.fetchall()
    items = []
    for r in rows:
        items.append({
            "name": r[0], "url": r[1], "status": r[2],
            "code": r[3], "latency": r[4], "ts": r[5]
        })
    html = "<html><head><meta charset='utf-8'><title>Monitor</title></head><body>"
    html += "<h1>Monitor - recent checks</h1><table border='1' cellpadding='6'><tr><th>Name</th><th>URL</th><th>Status</th><th>Code</th><th>Latency ms</th><th>Time</th></tr>"
    for it in items:
        t = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(it["ts"]))
        html += f"<tr><td>{it['name']}</td><td>{it['url']}</td><td>{it['status']}</td><td>{it['code']}</td><td>{it['latency']}</td><td>{t}</td></tr>"
    html += "</table></body></html>"
    return web.Response(text=html, content_type='text/html')

async def init_app():
    await init_db()
    targets = await read_targets()
    for t in targets:
        # seed state cache by marking unknown
        state_cache[t["url"]] = None

    # start periodic tasks
    for t in targets:
        asyncio.create_task(periodic_worker(t))

    app = web.Application()
    app.add_routes([web.get("/", handle_index)])
    return app

if __name__ == "__main__":
    web.run_app(init_app(), host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
