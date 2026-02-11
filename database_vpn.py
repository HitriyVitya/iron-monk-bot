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
            tier INTEGER DEFAULT 3, latency INTEGER DEFAULT 9999,
            fails INTEGER DEFAULT 0, last_check TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            source TEXT DEFAULT 'auto')''')
    conn.commit(); conn.close()

def save_proxy_batch(proxies_list, source='auto', tier_dict=None):
    conn = get_connection(); c = conn.cursor()
    from proxy_vacuum import get_tier # Импорт внутри для точности
    for url in proxies_list:
        try:
            proto = url.split("://")[0]
            t = tier_dict.get(url, get_tier(url)) if tier_dict else get_tier(url)
            # ВАЖНО: Всегда обновляем tier, чтобы убрать ложное золото!
            c.execute("""INSERT INTO vpn_proxies (url, type, tier, source, fails) 
                         VALUES (?, ?, ?, ?, 0)
                         ON CONFLICT(url) DO UPDATE SET tier=?, fails=0""", (url, proto, t, source, t))
        except: pass
    conn.commit(); conn.close()

def get_proxies_to_check(limit=150):
    conn = get_connection(); c = conn.cursor()
    c.execute("SELECT url FROM vpn_proxies WHERE fails < 15 ORDER BY last_check ASC LIMIT ?", (limit,))
    rows = [r[0] for r in c.fetchall()]
    conn.close(); return rows

def update_proxy_status(url, latency, tier, country):
    conn = get_connection(); c = conn.cursor()
    if latency is not None:
        # ПРИНУДИТЕЛЬНО обновляем и тир, и страну!
        c.execute("UPDATE vpn_proxies SET latency=?, tier=?, country=?, fails=0, last_check=CURRENT_TIMESTAMP WHERE url=?", (latency, tier, country, url))
    else:
        c.execute("UPDATE vpn_proxies SET fails = fails + 1, last_check=CURRENT_TIMESTAMP WHERE url=?", (url,))
    conn.commit(); conn.close()

def get_best_proxies_for_sub():
    conn = get_connection(); c = conn.cursor()
    # Сначала 1000 элиты (Tier 1), потом 500 остальных
    c.execute("SELECT url, latency, tier, country, source FROM vpn_proxies WHERE fails < 3 AND latency < 3500 AND tier = 1 ORDER BY latency ASC LIMIT 1000")
    t1 = c.fetchall()
    c.execute("SELECT url, latency, tier, country, source FROM vpn_proxies WHERE fails < 3 AND latency < 3500 AND tier > 1 ORDER BY tier ASC, latency ASC LIMIT 500")
    others = c.fetchall()
    conn.close()
    return t1 + others
