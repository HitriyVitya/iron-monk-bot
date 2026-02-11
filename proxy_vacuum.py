import asyncio, requests, re, json, base64, time, logging, yaml, os, random
from bs4 import BeautifulSoup
from urllib.parse import urlparse, unquote, parse_qs
import database_vpn as db

# --- НАСТРОЙКИ ---
TG_CHANNELS = [
    "shadowsockskeys", "oneclickvpnkeys", "VlessConfig", "PrivateVPNs", 
    "nV_v2ray", "gurvpn_keys", "vmessh", "VMESS7", "outline_marzban", "outline_k"
]

EXTERNAL_SUBS = [
    "https://raw.githubusercontent.com/yebekhe/TelegramV2rayCollector/main/sub/normal/mix",
    "https://raw.githubusercontent.com/vfarid/v2ray-share/main/all_v2ray_configs.txt",
    "https://raw.githubusercontent.com/barry-far/V2ray-Configs/main/Sub1.txt"
]

# Гитхаб для пуша (Витрина) и пулла (Резерв с ПК)
GH_TOKEN = os.getenv("GH_TOKEN")
GH_REPO = "HitriyVitya/iron-monk-bot"
RESERVE_URL = f"https://raw.githubusercontent.com/HitriyVitya/iron-monk-bot/main/reserve.json"

MAX_TOTAL_ALIVE = 1500 
MAX_PAGES_TG = 500 # Листаем историю до корки
TIMEOUT = 2.5      # Баланс для проверки порта

def safe_decode(s):
    try:
        s = re.sub(r'[^a-zA-Z0-9+/=]', '', s)
        return base64.b64decode(s + '=' * (-len(s) % 4)).decode('utf-8', errors='ignore')
    except: return ""

def get_tier(url):
    u = url.lower()
    is_reality = "security=reality" in u or "pbk=" in u
    if is_reality or "hy2" in u or "hysteria2" in u or u.startswith("trojan://"):
        return 1
    if u.startswith("vmess://") or (u.startswith("ss://") and any(x in u for x in ['gcm', 'poly1305', '2022'])):
        return 2
    return 3

def push_to_github(content):
    if not GH_TOKEN: return
    try:
        url = f"https://api.github.com/repos/{GH_REPO}/contents/proxies.yaml"
        headers = {"Authorization": f"token {GH_TOKEN}", "Accept": "application/vnd.github.v3+json"}
        r = requests.get(url, headers=headers)
        sha = r.json().get('sha') if r.status_code == 200 else None
        b64_content = base64.b64encode(content.encode('utf-8')).decode('utf-8')
        payload = {"message": f"Sync {time.strftime('%H:%M')}", "content": b64_content, "branch": "main"}
        if sha: payload["sha"] = sha
        requests.put(url, headers=headers, json=payload, timeout=15)
        logging.info("🚀 Витрина на GitHub обновлена")
    except Exception as e: logging.error(f"GH Push Error: {e}")

async def pull_reserve():
    """Тянем элитную базу, которую твой ПК залил на Гитхаб"""
    logging.info("📡 [Pull] Загрузка элиты с ПК...")
    try:
        r = await asyncio.to_thread(requests.get, RESERVE_URL, timeout=15)
        if r.status_code == 200:
            data = r.json()
            all_urls = []
            tier_map = {}
            for t in ['tier1', 'tier2', 'tier3']:
                tier_val = int(t[-1])
                for item in data.get(t, []):
                    url = item['u'].replace("💻 ", "")
                    all_urls.append(url)
                    tier_map[url] = tier_val
            # Сохраняем в базу Koyeb с пометкой source='pc'
            db.save_proxy_batch(all_urls, source='pc', tier_dict=tier_map)
            logging.info(f"✅ [Pull] Синхронизировано {len(all_urls)} серверов с ПК")
    except Exception as e: logging.error(f"Pull Error: {e}")

async def scraper_task():
    regex = re.compile(r'(?:vless|vmess|ss|ssr|trojan|hy2|hysteria|tuic)://[^\s<"\'\)]+')
    headers = {'User-Agent': 'Mozilla/5.0'}
    while True:
        logging.info("📥 [Scraper] Начинаю глубокий выгреб...")
        await pull_reserve() # Сначала актуализируем элиту
        
        # 1. Гитхаб источники
        for url in EXTERNAL_SUBS:
            try:
                r = await asyncio.to_thread(requests.get, url, headers=headers, timeout=15)
                text = r.text if "://" in r.text[:50] else safe_decode(r.text)
                found = regex.findall(text)
                if found: db.save_proxy_batch([l.strip() for l in found], source='auto')
            except: pass

        # 2. ТГ (Бесконечная листалка)
        for ch in TG_CHANNELS:
            base_url = f"https://t.me/s/{ch}"
            for _ in range(MAX_PAGES_TG):
                try:
                    r = await asyncio.to_thread(requests.get, base_url, headers=headers, timeout=10)
                    matches = regex.findall(r.text)
                    if matches: db.save_proxy_batch([l.strip().split('<')[0] for l in matches], source='auto')
                    if 'tme_messages_more' not in r.text: break
                    match = re.search(r'href="(/s/.*?before=\d+)"', r.text)
                    if match: base_url = "https://t.me" + match.group(1)
                    else: break
                except: break
        
        logging.info("💤 [Scraper] Сплю 40 минут.")
        await asyncio.sleep(2400)

async def checker_task():
    sem = asyncio.Semaphore(100)
    while True:
        candidates = db.get_proxies_to_check(200)
        if candidates:
            results = []
            async def verify(url):
                async with sem:
                    try:
                        if "vmess" in url: d = json.loads(safe_decode(url[8:])); h, p = d['add'], int(d['port'])
                        else: pr = urlparse(url); h, p = pr.hostname, pr.port
                        if not h or not p: return
                        st = time.time()
                        _, w = await asyncio.wait_for(asyncio.open_connection(h, p), timeout=TIMEOUT)
                        lat = int((time.time() - st) * 1000)
                        w.close(); await w.wait_closed()
                        if lat > 10: results.append((url, lat))
                    except: db.update_proxy_status(url, None, 3, "UN")
            
            await asyncio.gather(*(verify(u) for u in candidates))
            
            for url, lat in results:
                # Определяем тир на лету для авто-сбора
                tier = get_tier(url)
                db.update_proxy_status(url, lat, tier, "UN")
            
            # ФОРМИРУЕМ VIP-ПОДПИСКУ И ПУШИМ
            from keep_alive import generate_clash_yaml
            vip_data = db.get_vip_sub()
            if vip_data:
                yaml_content = generate_clash_yaml(vip_data)
                push_to_github(yaml_content)

        await asyncio.sleep(5)

async def vacuum_job():
    asyncio.create_task(scraper_task())
    asyncio.create_task(checker_task())
    while True: await asyncio.sleep(3600)
