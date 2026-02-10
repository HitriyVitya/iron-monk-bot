import sqlite3

DB_NAME = "vpn_storage.db"

def get_connection():
    conn = sqlite3.connect(DB_NAME, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL;") 
    return conn

def init_proxy_db():
    conn = get_connection(); c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS vpn_proxies (
            url TEXT PRIMARY KEY, type TEXT, country TEXT, 
            is_ai INTEGER DEFAULT 0, latency INTEGER DEFAULT 9999,
            fails INTEGER DEFAULT 0, last_check TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit(); conn.close()

def save_proxy_batch(proxies_list):
    conn = get_connection(); c = conn.cursor()
    for url in proxies_list:
        try:
            proto = url.split("://")[0]
            c.execute("INSERT OR IGNORE INTO vpn_proxies (url, type, latency) VALUES (?, ?, 9999)", (url, proto))
        except: pass
    conn.commit(); conn.close()

def get_proxies_to_check(limit=150):
    conn = get_connection(); c = conn.cursor()
    c.execute("SELECT url FROM vpn_proxies WHERE fails < 10 ORDER BY last_check ASC LIMIT ?", (limit,))
    rows = [r[0] for r in c.fetchall()]
    conn.close(); return rows

def update_proxy_status(url, latency, is_ai, country):
    conn = get_connection(); c = conn.cursor()
    if latency is not None:
        c.execute("UPDATE vpn_proxies SET latency=?, is_ai=?, country=?, fails=0, last_check=CURRENT_TIMESTAMP WHERE url=?", (latency, is_ai, country, url))
    else:
        c.execute("UPDATE vpn_proxies SET fails = fails + 1, last_check=CURRENT_TIMESTAMP WHERE url=?", (url,))
    conn.commit(); conn.close()

def get_best_proxies_for_sub():
    conn = get_connection(); c = conn.cursor()
    # Берем 1000 лучших серверов, сначала быстрые
    c.execute("""SELECT url, latency, is_ai, country FROM vpn_proxies 
                 WHERE fails < 3 AND latency < 2500 
                 ORDER BY latency ASC LIMIT 1000""")
    rows = c.fetchall()
    conn.close(); return rows
