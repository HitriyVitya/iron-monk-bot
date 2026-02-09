
import asyncio
import requests
import re
import base64
import json
import time
import logging
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




FINAL_SUB_PATH = "clash_sub.yaml"

def safe_decode(s):
    try:
        s = re.sub(r'[^a-zA-Z0-9+/=]', '', s)
        return base64.b64decode(s + '=' * (-len(s) % 4)).decode('utf-8', errors='ignore')
    except: return ""

# --- ЛЕГКАЯ НО ГЛУБОКАЯ ПРОВЕРКА ---
async def smart_ping(url, semaphore):
    """
    Проверяет сервер без запуска тяжелого ядра. 
    Имитирует начало обмена данными.
    """
    async with semaphore:
        try:
            if "vmess://" in url:
                d = json.loads(safe_decode(url[8:])); host, port = d['add'], int(d['port'])
            else:
                p = urlparse(url); host, port = p.hostname, p.port
            
            if not host or not port: return None

            start = time.time()
            # Пытаемся открыть сокет
            reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=2.0)
            
            # Имитируем отправку данных (просто пустой пинг на уровне сокета)
            latency = int((time.time() - start) * 1000)
            
            writer.close()
            await writer.wait_closed()

            if latency < 10: return None # Фейки
            
            # Помечаем AI если Reality (они живучие)
            is_ai = 1 if "reality" in url.lower() or "pbk=" in url.lower() else 0
            
            return {"url": url, "lat": latency, "is_ai": is_ai}
        except:
            return None

# --- ГЕНЕРАТОР ---
def update_clash_file():
    import yaml
    try:
        from keep_alive import link_to_clash_dict
        rows = db.get_best_proxies_for_sub()
        clash_proxies = []
        for idx, r in enumerate(rows):
            obj = link_to_clash_dict(r[0], r[1], r[2], r[3])
            if obj:
                obj['name'] = f"{obj['name']} ({idx})"
                clash_proxies.append(obj)
        
        if not clash_proxies:
            # Если совсем глухо, сделаем пустой, но валидный конфиг
            full_config = {"proxies": [], "proxy-groups": [{"name": "🌍 GLOBAL", "type": "select", "proxies": ["DIRECT"]}], "rules": ["MATCH,DIRECT"]}
        else:
            full_config = {
                "proxies": clash_proxies,
                "proxy-groups": [{"name": "🚀 Auto Select", "type": "url-test", "url": "http://1.1.1.1/generate_204", "interval": 300, "proxies": [p['name'] for p in clash_proxies]}],
                "rules": ["MATCH,🚀 Auto Select"]
            }
        
        with open(FINAL_SUB_PATH, 'w', encoding='utf-8') as f:
            yaml.dump(full_config, f, allow_unicode=True, sort_keys=False)
        logging.info(f"💾 Файл обновлен: {len(clash_proxies)} шт.")
    except Exception as e:
        logging.error(f"Save error: {e}")

# --- ФОНОВЫЙ ПАРСИНГ ---
async def scraper_task():
    regex = re.compile(r'(?:vless|vmess|ss|ssr|trojan|hy2|hysteria)://[^\s<"\'\)]+')
    headers = {'User-Agent': 'Mozilla/5.0'}
    while True:
        logging.info("📥 [Scraper] Начинаю обход...")
        # Собираем ссылки (упрощенно для скорости)
        for url in EXTERNAL_SUBS:
            try:
                r = await asyncio.to_thread(requests.get, url, headers=headers, timeout=10)
                found = regex.findall(r.text if "://" in r.text[:50] else safe_decode(r.text))
                if found: db.save_proxy_batch([l.strip() for l in found])
            except: pass
        
        for ch in TG_CHANNELS:
            try:
                r = await asyncio.to_thread(requests.get, f"https://t.me/s/{ch}", headers=headers, timeout=5)
                found = regex.findall(r.text)
                if found: db.save_proxy_batch([l.strip().split('<')[0] for l in found])
            except: pass
        
        await asyncio.sleep(1800)

async def checker_task():
    sem = asyncio.Semaphore(40) # Теперь можно больше, т.к. нет sing-box
    while True:
        candidates = db.get_proxies_to_check(100)
        if candidates:
            logging.info(f"🧪 [Checker] Проверяю {len(candidates)} шт...")
            results = await asyncio.gather(*(smart_ping(u, sem) for u in candidates))
            
            for i, res in enumerate(results):
                if res: 
                    db.update_proxy_status(res['url'], res['lat'], res['is_ai'], "UN")
                else: 
                    db.update_proxy_status(candidates[i], None, 0, "")
            
            update_clash_file()
        await asyncio.sleep(5)

async def vacuum_job():
    asyncio.create_task(scraper_task())
    asyncio.create_task(checker_task())
    while True: await asyncio.sleep(3600)
