import asyncio
import requests
import re
import base64
import json
import time
import logging
import yaml
from bs4 import BeautifulSoup
from urllib.parse import urlparse, unquote, parse_qs, quote
import database_vpn as db
# --- СПИСКИ ---
TG_CHANNELS = [
    "shadowsockskeys", "oneclickvpnkeys", "v2ray_outlineir",
    "v2ray_free_conf", "v2rayngvpn", "v2ray_free_vpn",
    "gurvpn_keys", "vmessh", "VMESS7", "VlessConfig",
    "PrivateVPNs", "nV_v2ray", "NotorVPN", "FairVpn_V2ray",
    "outline_marzban", "outline_k"
]

EXTERNAL_SUBS = [
    "https://raw.githubusercontent.com/yebekhe/TelegramV2rayCollector/main/sub/normal/mix",
    "https://raw.githubusercontent.com/vfarid/v2ray-share/main/all_v2ray_configs.txt",
    "https://raw.githubusercontent.com/barry-far/V2ray-Configs/main/Sub1.txt",
    "https://raw.githubusercontent.com/mahdibland/V2RayAggregator/master/sub/sub_merge.txt",
    "https://raw.githubusercontent.com/LonUp/NodeList/main/NodeList.txt",
    "https://raw.githubusercontent.com/officialputuid/V2Ray-Config/main/Splitted-v2ray-config/all"
]

STATIC_SUB_PATH = "clash_sub.yaml"

def safe_decode(s):
    try:
        s = re.sub(r'[^a-zA-Z0-9+/=]', '', s)
        return base64.b64decode(s + '=' * (-len(s) % 4)).decode('utf-8', errors='ignore')
    except: return ""

def link_to_clash_dict(url, latency, is_ai, country):
    """Конвертер ссылки в формат Clash"""
    try:
        flag = "".join(chr(ord(c) + 127397) for c in country.upper()) if len(country)==2 else "🏳️"
        ai_tag = " ✨ AI" if is_ai else ""
        try: srv = url.split('@')[-1].split(':')[0].split('.')[-1]
        except: srv = "srv"
        name = f"{flag}{ai_tag} {latency}ms | {srv}"

        if url.startswith("vmess://"):
            d = json.loads(safe_decode(url[8:]))
            return {'name': name, 'type': 'vmess', 'server': d.get('add'), 'port': int(d.get('port')), 'uuid': d.get('id'), 'alterId': 0, 'cipher': 'auto', 'udp': True, 'tls': d.get('tls') == 'tls', 'skip-cert-verify': True, 'network': d.get('net', 'tcp')}
        
        if url.startswith(("vless://", "trojan://")):
            p = urlparse(url); q = parse_qs(p.query); tp = 'vless' if url.startswith('vless') else 'trojan'
            obj = {'name': name, 'type': tp, 'server': p.hostname, 'port': p.port, 'uuid': p.username or p.password, 'password': p.username or p.password, 'udp': True, 'skip-cert-verify': True, 'tls': q.get('security', [''])[0] in ['tls', 'reality'], 'network': q.get('type', ['tcp'])[0]}
            if tp == 'trojan' and 'uuid' in obj: del obj['uuid']
            if q.get('security', [''])[0] == 'reality':
                obj['servername'] = q.get('sni', [''])[0]
                obj['reality-opts'] = {'public-key': q.get('pbk', [''])[0], 'short-id': q.get('sid', [''])[0]}
                obj['client-fingerprint'] = 'chrome'
            return obj

        if url.startswith("ss://"):
            main = url.split("#")[0].replace("ss://", "")
            if "@" in main:
                u, s = main.split("@", 1); d = safe_decode(u)
                m, pw = d.split(":", 1) if ":" in d else (u.split(":", 1) if ":" in u else ("aes-256-gcm", u))
                return {'name': name, 'type': 'ss', 'server': s.split(":")[0], 'port': int(s.split(":")[1].split("/")[0]), 'cipher': m, 'password': pw, 'udp': True}
    except: pass
    return None

def update_static_sub():
    """Собирает живых и пишет в файл"""
    try:
        rows = db.get_best_proxies_for_sub()
        clash_proxies = []
        for r in rows:
            obj = link_to_clash_dict(r[0], r[1], r[2], r[3])
            if obj:
                while any(p['name'] == obj['name'] for p in clash_proxies): obj['name'] += " "
                clash_proxies.append(obj)
        if clash_proxies:
            with open(STATIC_SUB_PATH, 'w', encoding='utf-8') as f:
                yaml.dump({'proxies': clash_proxies}, f, allow_unicode=True, sort_keys=False)
            logging.info(f"💾 Подписка обновлена: {len(clash_proxies)} серверов.")
    except Exception as e: logging.error(f"Save error: {e}")

async def scraper_task():
    regex = re.compile(r'(?:vless|vmess|ss|ssr|trojan|hy2|hysteria)://[^\s<"\'\)]+')
    headers = {'User-Agent': 'Mozilla/5.0'}
    while True:
        logging.info("📥 [Scraper] Сбор...")
        links = set()
        for url in EXTERNAL_SUBS:
            try:
                r = requests.get(url, headers=headers, timeout=10); t = r.text
                d = safe_decode(t); t = d if "://" in d else t
                for l in regex.findall(t): links.add(l.strip())
            except: pass
        for ch in TG_CHANNELS:
            try:
                r = requests.get(f"https://t.me/s/{ch}", headers=headers, timeout=5)
                for l in regex.findall(r.text): links.add(l.strip().split('<')[0])
            except: pass
        if links: db.save_proxy_batch(list(links))
        await asyncio.sleep(1800)

async def checker_task():
    while True:
        candidates = db.get_proxies_to_check(100)
        if not candidates:
            await asyncio.sleep(10); continue
        
        sem = asyncio.Semaphore(50)
        async def verify(url):
            async with sem:
                try:
                    if "vmess://" in url:
                        d = json.loads(safe_decode(url[8:])); host, port = d['add'], int(d['port'])
                    else:
                        p = urlparse(url); host, port = p.hostname, p.port
                    if not host or not port: return
                    st = time.time()
                    _, w = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=1.5)
                    lat = int((time.time() - st) * 1000)
                    w.close(); await w.wait_closed()
                    is_ai = 1 if lat < 200 or "reality" in url.lower() else 0
                    db.update_proxy_status(url, lat, is_ai, "UN") # Страну определим в будущем
                except: db.update_proxy_status(url, None, 0, "")

        await asyncio.gather(*(verify(u) for u in candidates))
        update_static_sub() # Обновляем файл после каждой пачки
        await asyncio.sleep(5)

async def vacuum_job():
    asyncio.create_task(scraper_task())
    asyncio.create_task(checker_task())
    while True: await asyncio.sleep(3600)
