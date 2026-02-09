import asyncio
import requests
import re
import base64
import json
import time
import logging
from bs4 import BeautifulSoup
from urllib.parse import urlparse
import database_vpn as db
import keep_alive
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

def safe_decode(s):
    try:
        s = re.sub(r'[^a-zA-Z0-9+/=]', '', s)
        padding = len(s) % 4
        if padding: s += '=' * (4 - padding)
        return base64.b64decode(s).decode('utf-8', errors='ignore')
    except: return ""

def extract_ip_port(link):
    try:
        if link.startswith("vmess://"):
            data = json.loads(safe_decode(link[8:]))
            return data.get('add'), int(data.get('port'))
        p = urlparse(link)
        if link.startswith("ss://") and "@" in link:
            part = link.split("@")[-1].split("#")[0].split("/")[0]
            if ":" in part: 
                return part.split(":")[0].replace("[","").replace("]",""), int(part.split(":")[1])
        if p.hostname and p.port: return p.hostname, p.port
    except: pass
    return None, None

async def check_tcp(ip, port):
    try:
        st = time.time()
        conn = asyncio.open_connection(ip, port)
        _, w = await asyncio.wait_for(conn, timeout=1.2) # Жесткий таймаут 1.2 сек
        lat = int((time.time() - st) * 1000)
        w.close()
        await w.wait_closed()
        return lat
    except: return None

# --- ЗАДАЧА 1: ПЫЛЕСОС (Сосет и сразу сохраняет) ---
async def scraper_task():
    regex = re.compile(r'(?:vless|vmess|ss|ssr|trojan|hy2|hysteria|hysteria2|tuic|socks5)://[^\s<"\'\)]+')
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    while True:
        logging.info("📥 [Scraper] Старт цикла сбора...")
        
        # 1. ГИТХАБ (Быстро)
        for url in EXTERNAL_SUBS:
            try:
                r = requests.get(url, headers=headers, timeout=15)
                text = r.text
                if len(text) > 20 and not "://" in text[:50]:
                    d = safe_decode(text)
                    if d: text = d
                
                batch = []
                for l in regex.findall(text): batch.append(l.strip())
                
                if batch:
                    count = db.save_proxy_batch(batch)
                    if count > 0: logging.info(f"📥 [Scraper] +{count} с Гитхаба")
            except: pass
            await asyncio.sleep(1) # Небольшая пауза между запросами

        # 2. ТЕЛЕГРАМ (Медленно, но много)
        for ch in TG_CHANNELS:
            url = f"https://t.me/s/{ch}"
            for _ in range(5): # Листаем только 5 страниц за раз, чтобы не виснуть
                try:
                    r = requests.get(url, headers=headers, timeout=5)
                    soup_text = r.text
                    
                    batch = []
                    for l in regex.findall(soup_text):
                        batch.append(l.strip().split('<')[0])
                    
                    if batch:
                        count = db.save_proxy_batch(batch)
                        # logging.info(f"📥 [Scraper] +{count} с {ch}") # Можно раскомментить для дебага
                    
                    if 'tme_messages_more' in soup_text:
                        match = re.search(r'href="(/s/.*?)"', soup_text)
                        if match: url = "https://t.me" + match.group(1)
                        else: break
                    else: break
                    await asyncio.sleep(0.5)
                except: break
        
        logging.info("💤 [Scraper] Цикл завершен. Сплю 30 минут.")
        await asyncio.sleep(1800)

# --- ЗАДАЧА 2: ЧЕКЕР (Берет из базы и проверяет) ---
async def checker_task():
    while True:
        # Берем 100 непроверенных или старых
        candidates = db.get_proxies_to_check(limit=100)
        
        if not candidates:
            # Если проверять нечего, спим чуть-чуть и ждем пылесос
            await asyncio.sleep(10)
            continue
            
        # logging.info(f"🧪 [Checker] Проверяю пачку из {len(candidates)}...")
        
        sem = asyncio.Semaphore(50) # 50 потоков
        
        async def verify(url):
            async with sem:
                ip, port = extract_ip_port(url)
                if not ip or not port:
                    db.update_proxy_status(url, None, 0, "")
                    return

                lat = await check_tcp(ip, port)
                if lat:
                    # AI (простая эвристика)
                    is_ai = 1 if "reality" in url.lower() or "pbk=" in url.lower() else 0
                    db.update_proxy_status(url, lat, is_ai, "🏳️")
                else:
                    db.update_proxy_status(url, None, 0, "")

        await asyncio.gather(*(verify(u) for u in candidates))
        # ... в конце функции checker_task, после await asyncio.gather ...
        await asyncio.gather(*(verify(u) for u in candidates))
        
   
            # ВЫЗЫВАЕМ ОБНОВЛЕНИЕ КЭША
        import keep_alive
        keep_alive.update_internal_cache()
        await asyncio.sleep(2)

# --- ЗАПУСК ---
async def vacuum_job():
    # Запускаем два независимых цикла
    asyncio.create_task(scraper_task())
    asyncio.create_task(checker_task())
    
    # Сам vacuum_job висит вечно, чтобы таск не закрылся
    while True:
        await asyncio.sleep(3600)
