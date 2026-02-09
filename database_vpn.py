import sqlite3

DB_NAME = "vpn_storage.db"

def init_proxy_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS vpn_proxies (url TEXT PRIMARY KEY, type TEXT, latency INTEGER, fails INTEGER DEFAULT 0, last_check TIMESTAMP)''')
    conn.commit(); conn.close()

def save_proxy_batch(proxies_list):
    conn = sqlite3.connect(DB_NAME); c = conn.cursor()
    for url in proxies_list:
        try:
            proto = url.split("://")[0]
            c.execute("INSERT OR IGNORE INTO vpn_proxies (url, type, latency) VALUES (?, ?, 9999)", (url, proto))
        except: pass
    conn.commit(); conn.close()

def get_proxies_to_check(limit=100):
    conn = sqlite3.connect(DB_NAME); c = conn.cursor()
    c.execute("SELECT url FROM vpn_proxies WHERE fails < 5 ORDER BY last_check ASC LIMIT ?", (limit,))
    rows = [r[0] for r in c.fetchall()]
    conn.close(); return rows

def update_proxy_status(url, latency):
    conn = sqlite3.connect(DB_NAME); c = conn.cursor()
    if latency is not None:
        c.execute("UPDATE vpn_proxies SET latency=?, fails=0, last_check=CURRENT_TIMESTAMP WHERE url=?", (latency, url))
    else:
        c.execute("UPDATE vpn_proxies SET fails = fails + 1, last_check=CURRENT_TIMESTAMP WHERE url=?", (url,))
    conn.commit(); conn.close()

def get_best_proxies_for_sub():
    conn = sqlite3.connect(DB_NAME); c = conn.cursor()
    c.execute("SELECT url FROM vpn_proxies WHERE fails < 3 AND latency < 2000 ORDER BY latency ASC LIMIT 500")
    rows = [r[0] for r in c.fetchall()]
    conn.close(); return rows
