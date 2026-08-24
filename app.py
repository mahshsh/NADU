#!/usr/bin/env python3
# TANOLI Non-Stop Messenger - WEB EDITION (Cloud Backup Server)
# Sending engine same as phone version. Control via browser.
import os, json, time, requests, threading, sqlite3
from datetime import datetime
from flask import Flask, request, redirect, render_template_string

HOME = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(HOME, "nano_queue.db")
CONFIG_FILE = os.path.join(HOME, "nano_config.json")
LOG_FILE = os.path.join(HOME, "nano_daemon.log")
STATS_FILE = os.path.join(HOME, "nano_stats.json")

app = Flask(__name__)
lock = threading.Lock()
stats = {"sent": 0, "failed": 0}

def load_stats():
    global stats
    try: stats = json.load(open(STATS_FILE))
    except: pass
def save_stats():
    try: json.dump(stats, open(STATS_FILE, "w"))
    except: pass
def load_config():
    try: return json.load(open(CONFIG_FILE))
    except: return {"delay": 60, "engine": False}
def save_config(c):
    json.dump(c, open(CONFIG_FILE, "w"))
def log(msg):
    try:
        with open(LOG_FILE, "a") as f:
            f.write(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}\n")
    except: pass

conn = sqlite3.connect(DB_FILE, check_same_thread=False, timeout=30)
conn.cursor().execute('''CREATE TABLE IF NOT EXISTS queue
    (id INTEGER PRIMARY KEY AUTOINCREMENT, token TEXT, uid TEXT,
     hater_name TEXT, message TEXT, attempts INTEGER DEFAULT 0,
     status TEXT DEFAULT 'pending')''')
conn.commit()

def check_internet():
    try:
        requests.get("https://graph.facebook.com", timeout=5); return True
    except: return False

def sender_daemon():
    log("[DAEMON] TANOLI web engine ready.")
    while True:
        try:
            cfg = load_config()
            if not cfg.get("engine", False):
                time.sleep(2); continue
            if not check_internet():
                time.sleep(5); continue
            c = conn.cursor()
            c.execute("SELECT id, token, uid, hater_name, message, attempts FROM queue WHERE status='pending' ORDER BY id LIMIT 1")
            task = c.fetchone()
            if not task:
                time.sleep(2); continue
            msg_id, token, uid, hater_name, message, attempts = task
            url = f"https://graph.facebook.com/v18.0/t_{uid}/"
            final_msg = message.replace("{name}", hater_name).replace("{NAME}", hater_name.upper())
            try:
                r = requests.post(url, data={'access_token': token, 'message': final_msg}, timeout=15)
                if r.status_code == 200:
                    c.execute("UPDATE queue SET status='pending', attempts=0 WHERE id=?", (msg_id,))
                    conn.commit()
                    with lock: stats['sent'] += 1; save_stats()
                    log(f"[SENT] To {hater_name}")
                    time.sleep(cfg.get('delay', 60))
                elif r.status_code == 400:
                    err = ''
                    try: err = r.json().get('error', {}).get('message', '')
                    except: pass
                    if 'expired' in err.lower() or 'invalid' in err.lower():
                        c.execute("UPDATE queue SET status='dead' WHERE id=?", (msg_id,)); conn.commit()
                        log(f"[DEAD TOKEN] ID {msg_id}"); time.sleep(60)
                    else:
                        with lock: stats['failed'] += 1; save_stats(); time.sleep(10)
                elif r.status_code == 429:
                    time.sleep(60)
                else:
                    time.sleep(10)
            except Exception as e:
                log(f"[ERR] {str(e)[:40]}"); time.sleep(5)
        except Exception as e:
            log(f"[CRITICAL] {e}"); time.sleep(10)

PAGE = """<!doctype html><html><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>TANOLI Server</title><style>
body{background:#000;color:#fff;font-family:monospace;padding:16px}
h1{color:#0ff}.g{color:#0f0}.y{color:#ff0}.r{color:#f55}
.box{border:2px solid #0ff;padding:10px;margin:10px 0;border-radius:8px}
input,textarea{width:100%;background:#111;color:#0ff;border:1px solid #0ff;padding:8px;margin:4px 0;font-family:monospace;box-sizing:border-box}
button{background:#0ff;color:#000;border:0;padding:10px 18px;font-weight:bold;margin:4px;font-family:monospace}
button.off{background:#f55}a{color:#f55}</style></head><body>
<h1>🚀 TANOLI NON-STOP MESSENGER</h1>
<div class=box>Server: <b>TANOLI ⚡</b> (Cloud Backup)<br>
Status: {% if engine %}<span class=g>ONLINE (LOOPING)</span>{% else %}<span class=y>PAUSED (ENGINE OFF)</span>{% endif %}<br>
<span class=g>Sent: {{sent}}</span> &nbsp; <span class=y>Active: {{active}}</span> &nbsp; <span class=r>Fail: {{fail}}</span><br>
Speed: {{delay}}s delay</div>
<div class=box><form method=post action=/toggle>
<button class="{{ 'off' if engine else '' }}">{{ 'ENGINE OFF karo' if engine else 'ENGINE ON karo' }}</button></form></div>
<div class=box><b>Add Target</b>
<form method=post action=/add>
<input name=token placeholder="Access Token" required>
<input name=uid placeholder="Target UID" required>
<input name=hater_name placeholder="Hater Name">
<textarea name=message rows=3 placeholder="Message ({name} use kar sakte ho)" required></textarea>
<input name=delay type=number placeholder="Delay seconds (optional)">
<button>ADD TO LOOP</button></form></div>
<div class=box><b>Active Loops</b>
{% for t in loops %}<div>{{t[0]}}. {{t[3]}} (UID: {{t[2]}}) - {{t[4][:40]}} <a href=/del?id={{t[0]}}>✗ remove</a></div>{% endfor %}
{% if not loops %}<span class=y>No active loops</span>{% endif %}</div>
</body></html>"""

@app.route("/")
def index():
    load_stats(); cfg = load_config()
    c = conn.cursor()
    c.execute("SELECT id, token, uid, hater_name, message, status FROM queue WHERE status='pending' ORDER BY id")
    loops = c.fetchall()
    return render_template_string(PAGE, sent=stats.get('sent',0), fail=stats.get('failed',0),
        active=len(loops), delay=cfg.get('delay',60), engine=cfg.get('engine',False), loops=loops)

@app.route("/add", methods=["POST"])
def add():
    token = request.form.get("token","").strip()
    uid = request.form.get("uid","").strip()
    name = request.form.get("hater_name","").strip() or "Target"
    msg = request.form.get("message","").strip()
    d = request.form.get("delay","").strip()
    if token and uid and msg:
        c = conn.cursor()
        c.execute("INSERT INTO queue (token,uid,hater_name,message,status) VALUES (?,?,?,?, 'pending')", (token,uid,name,msg))
        conn.commit()
        if d.isdigit() and int(d) > 0:
            cfg = load_config(); cfg['delay'] = int(d); save_config(cfg)
        log(f"[ADD] {name}")
    return redirect("/")

@app.route("/toggle", methods=["POST"])
def toggle():
    cfg = load_config(); cfg['engine'] = not cfg.get('engine', False); save_config(cfg)
    log("[ENGINE] " + ("ON" if cfg['engine'] else "OFF"))
    return redirect("/")

@app.route("/del")
def delete():
    c = conn.cursor(); c.execute("DELETE FROM queue WHERE id=?", (request.args.get("id"),)); conn.commit()
    return redirect("/")

if __name__ == "__main__":
    threading.Thread(target=sender_daemon, daemon=True).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
