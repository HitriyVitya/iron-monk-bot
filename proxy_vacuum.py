
import asyncio, requests, re, json, base64, time, logging, yaml, os, random
from bs4 import BeautifulSoup
from urllib.parse import urlparse, unquote, parse_qs
import database_vpn as db
# --- НАСТРОЙКИ ---
TG_CHANNELS = [
    "shadowsockskeys", "oneclickvpnkeys", "VlessConfig", "PrivateVPNs", "nV_v2ray", "gurvpn_keys", "vmessh", "VMESS7", "outline_marzban", "outline_k"
]

EXTERNAL_SUBS = [
    "https://raw.githubusercontent.com/yebekhe/TelegramV2rayCollector/main/sub/normal/mix",
    "https://raw.githubusercontent.com/vfarid/v2ray-share/main/all_v2ray_configs.txt",
    "https://raw.githubusercontent.com/barry-far/V2ray-Configs/main/Sub1.txt",
    "https://raw.githubusercontent.com/mahdibland/V2RayAggregator/master/sub/sub_merge.txt",
    "https://raw.githubusercontent.com/LonUp/NodeList/main/NodeList.txt",
    "https://raw.githubusercontent.com/officialputuid/V2Ray-Config/main/Splitted-v2ray-config/all"
]



GH_TOKEN = os.getenv("GH_TOKEN")
GH_REPO = "HitriyVitya/iron-monk-bot"
GH_FILE_PATH = "proxies.yaml"

# ЛИМИТЫ (ВЫКРУТИЛИ НА МАКСИМУМ)
MAX_TOTAL_ALIVE = 1500 # 1000 Tier 1 + 500 остальных
MAX_PAGES_TG = 2000     # Глубочайшая пагинация истории
TIMEOUT = 4.0          # Даем серверам шанс ответить


def safe_decode(s):
    try:
        s = re.sub(r'[^a-zA-Z0-9+/=]', '', s)
        return base64.b64decode(s + '=' * (-len(s) % 4)).decode('utf-8', errors='ignore')
    except: return ""

def get_tier(url):
    """Строгая иерархия БЕЗ учета названия (fragment)"""
    # Отрезаем всё после #, чтобы не вестись на названия
    main_url = url.split('#')[0].lower()
    
    # Tier 1: Reality, Hysteria 2, Trojan
    if "security=reality" in main_url or "pbk=" in main_url: return 1
    if "hy2" in main_url or "hysteria2" in main_url: return 1
    if url.startswith("trojan://"): return 1
    
    # Tier 2: VMess, Современные Shadowsocks
    if url.startswith("vmess://"): return 2
    if url.startswith("ss://"):
        # Если в функциональной части есть современные шифры
        if any(x in main_url for x in ['gcm', 'poly1305', '2022']): return 2
        return 3
        
    return 3

def push_to_github(content):
    if not GH_TOKEN: return
    try:
        url = f"https://api.github.com/repos/{GH_REPO}/contents/{GH_FILE_PATH}"
        headers = {"Authorization": f"token {GH_TOKEN}", "Accept": "application/vnd.github.v3+json"}
        r = requests.get(url, headers=headers)
        sha = r.json().get('sha') if r.status_code == 200 else None
        b64_content = base64.b64encode(content.encode('utf-8')).decode('utf-8')
        payload = {"message": f"Update Tier-System {time.strftime('%H:%M')}", "content": b64_content, "branch": "main"}
        if sha: payload["sha"] = sha
        requests.put(url, headers=headers, json=payload, timeout=15)
    except: pass

async def get_countries_batch(ips):
    res_map = {}
    if not ips: return res_map
    try:
        unique_ips = list(set(ips))[:100]
        r = await asyncio.to_thread(requests.post, "http://ip-api.com/batch?fields=query,countryCode", json=[{"query": i} for i in unique_ips], timeout=15)
        for item in r.json():
            res_map[item['query']] = item.get('countryCode', 'UN')
    except: pass
    return res_map

async def scraper_task():
    regex = re.compile(r'(?:vless|vmess|ss|ssr|trojan|hy2|hysteria|tuic)://[^\s<"\'\)]+')
    headers = {'User-Agent': 'Mozilla/5.0'}
    while True:
        logging.info("📥 [Scraper] Глобальный выгреб...")
        # Гитхаб
        for url in EXTERNAL_SUBS:
            try:
                r = await asyncio.to_thread(requests.get, url, headers=headers, timeout=15)
                text = r.text if "://" in r.text[:50] else safe_decode(r.text)
                found = regex.findall(text)
                if found: db.save_proxy_batch([l.strip() for l in found])
            except: pass
        # ТГ
        for ch in TG_CHANNELS:
            base_url = f"https://t.me/s/{ch}"
            for _ in range(MAX_PAGES_TG):
                try:
                    r = await asyncio.to_thread(requests.get, base_url, headers=headers, timeout=10)
                    matches = regex.findall(r.text)
                    if matches: db.save_proxy_batch([l.strip().split('<')[0] for l in matches])
                    if 'tme_messages_more' not in r.text: break
                    match = re.search(r'href="(/s/.*?before=\d+)"', r.text)
                    if match: base_url = "https://t.me" + match.group(1)
                    else: break
                except: break
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
                        if "vmess" in url: 
                            d = json.loads(safe_decode(url[8:])); host, port = d['add'], int(d['port'])
                        else: 
                            p = urlparse(url); host, port = p.hostname, p.port
                        if not host or not port: return
                        
                        st = time.time()
                        _, w = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=2.5)
                        lat = int((time.time() - st) * 1000)
                        w.close(); await w.wait_closed()
                        results.append({'url': url, 'lat': lat, 'ip': host})
                    except: db.update_proxy_status(url, None, 3, "UN")
            
            await asyncio.gather(*(verify(u) for u in candidates))
            
            if results:
                geo_map = await get_countries_batch([r['ip'] for r in results])
                for r in results:
                    cc = geo_map.get(r['ip'], "UN")
                    tier = get_tier(r['url'])
                    db.update_proxy_status(r['url'], r['lat'], tier, cc)
                
                # ГЕНЕРАЦИЯ И ПУШ
                from keep_alive import link_to_clash_dict
                rows = db.get_best_proxies_for_sub()
                clash_proxies = []
                for idx, r in enumerate(rows):
                    obj = link_to_clash_dict(r[0], r[1], r[2], r[3])
                    if obj:
                        obj['name'] = f"{obj['name']} ({idx})"
                        clash_proxies.append(obj)
                
                if clash_proxies:
                    full_config = {
                        "proxies": clash_proxies,
                        "proxy-groups": [{
                            "name": "🚀 Auto Select", "type": "url-test", 
                            "url": "https://www.google.com/generate_204", 
                            "interval": 600, "timeout": 5000, 
                            "proxies": [p['name'] for p in clash_proxies]
                        }],
                        "rules": ["MATCH,🚀 Auto Select"]
                    }
                    push_to_github(yaml.dump(full_config, allow_unicode=True, sort_keys=False))
        await asyncio.sleep(5)

async def vacuum_job():
    asyncio.create_task(scraper_task())
    asyncio.create_task(checker_task())
    while True: await asyncio.sleep(3600)
