import asyncio, requests, re, json, base64, time, logging, yaml, os, random
from bs4 import BeautifulSoup
from urllib.parse import urlparse, unquote, parse_qs
import database_vpn as db


# --- НАСТРОЙКИ ---
TG_CHANNELS = [
    "shadowsockskeys", "oneclickvpnkeys", "VlessConfig", "PrivateVPNs", 
    "nV_v2ray", "gurvpn_keys", "vmessh", "VMESS7", "outline_marzban", "outline_k","NotorVPN","V2rayVPN_WireGaurd"
]

EXTERNAL_SUBS = [
    "https://raw.githubusercontent.com/yebekhe/TelegramV2rayCollector/main/sub/normal/mix",
    "https://raw.githubusercontent.com/vfarid/v2ray-share/main/all_v2ray_configs.txt",
    "https://raw.githubusercontent.com/barry-far/V2ray-Configs/main/Sub1.txt",
    "https://raw.githubusercontent.com/mahdibland/V2RayAggregator/master/sub/sub_merge.txt",
    "https://raw.githubusercontent.com/LonUp/NodeList/main/NodeList.txt",
    "https://raw.githubusercontent.com/officialputuid/V2Ray-Config/main/Splitted-v2ray-config/all",
    "https://raw.githubusercontent.com/Ai123999/2Tues/refs/heads/main/2Tues_Notorgamers",
    "https://raw.githubusercontent.com/Ai123999/6Satu/refs/heads/main/6Satu_Notorgamers",
    "https://raw.githubusercontent.com/Ai123999/1Mond/refs/heads/main/1Mond_Notorgamers",
    "https://raw.githubusercontent.com/Ai123999/3Wend/refs/heads/main/3Wend_Notorgamers",
    "https://raw.githubusercontent.com/Ai123999/7Sand/refs/heads/main/7Sand_Notorgamers",
    "https://raw.githubusercontent.com/Ai123999/5Frid/refs/heads/main/5Frid_Notorgamers",
    "https://raw.githubusercontent.com/Ai123999/WhiteeListSub/refs/heads/main/whitelistkeys",
    "https://raw.githubusercontent.com/Ai123999/4Thur/refs/heads/main/4Thur_Notorgamers",
    "https://raw.githubusercontent.com/Ai123999/WhiteKeys/refs/heads/main/WhiteKeys"
]

GH_TOKEN = os.getenv("GH_TOKEN")
GH_REPO = "HitriyVitya/iron-monk-bot"
GH_FILE_PATH = "proxies.yaml"
RESERVE_URL = f"https://raw.githubusercontent.com/HitriyVitya/iron-monk-bot/main/reserve.json"

MAX_TOTAL_ALIVE = 1500 
MAX_PAGES_TG = 500 
TIMEOUT = 2.5      



def safe_decode(s):
    try: return base64.b64decode(s + '=' * (-len(s) % 4)).decode('utf-8', errors='ignore')
    except: return ""

def get_tier(url):
    """СТРОЖАЙШИЙ ФИЛЬТР: SS больше никогда не будет Золотым"""
    u_base = url.split('#')[0].lower()
    
    # 1. Сначала отсекаем Shadowsocks - он никогда не Tier 1
    if u_base.startswith("ss://"):
        if any(c in u_base for c in ['2022', 'gcm', 'poly1305']): return 2
        return 3
    
    # 2. Tier 1: Reality, Hysteria, Trojan+TLS
    if "security=reality" in u_base or "pbk=" in u_base or "hy2" in u_base or "hysteria2" in u_base: return 1
    if u_base.startswith("trojan://") and ("security=tls" in u_base or "tls=tls" in u_base): return 1
    
    # 3. Остальное
    if u_base.startswith("vmess://"): return 2
    return 3

def push_to_github(content):
    if not GH_TOKEN: return
    try:
        url = f"https://api.github.com/repos/{GH_REPO}/contents/{GH_FILE_PATH}"
        headers = {"Authorization": f"token {GH_TOKEN}", "Accept": "application/vnd.github.v3+json"}
        r = requests.get(url, headers=headers)
        sha = r.json().get('sha') if r.status_code == 200 else None
        b64_content = base64.b64encode(content.encode('utf-8')).decode('utf-8')
        payload = {"message": f"Sync {time.strftime('%H:%M')}", "content": b64_content, "branch": "main"}
        if sha: payload["sha"] = sha
        requests.put(url, headers=headers, json=payload, timeout=15)
    except: pass

async def get_countries_batch(ips):
    """Починил: теперь чекает всех пачками по 100"""
    res_map = {}
    if not ips: return res_map
    unique_ips = list(set(ips))
    for i in range(0, len(unique_ips), 100):
        batch = unique_ips[i:i+100]
        try:
            r = await asyncio.to_thread(requests.post, "http://ip-api.com/batch?fields=query,countryCode", 
                                       json=[{"query": x} for x in batch], timeout=15)
            for item in r.json():
                res_map[item['query']] = item.get('countryCode', 'UN')
        except: pass
    return res_map

async def scraper_task():
    regex = re.compile(r'(?:vless|vmess|ss|ssr|trojan|hy2|hysteria|tuic)://[^\s<"\'\)]+')
    headers = {'User-Agent': 'Mozilla/5.0'}
    while True:
        # Тянем элиту с твоего ПК
        try:
            r = await asyncio.to_thread(requests.get, RESERVE_URL, timeout=15)
            if r.status_code == 200:
                data = r.json(); all_urls = []; t_map = {}
                for t in ['tier1', 'tier2', 'tier3']:
                    v = int(t[-1])
                    for i in data.get(t, []):
                        u = i['u'].replace("💻 ", ""); all_urls.append(u); t_map[u] = v
                db.save_proxy_batch(all_urls, source='pc', tier_dict=t_map)
        except: pass
        
        # Пылесосим ТГ и Гитхаб
        for url in EXTERNAL_SUBS:
            try:
                r = await asyncio.to_thread(requests.get, url, headers=headers, timeout=15)
                text = r.text if "://" in r.text[:50] else safe_decode(r.text)
                db.save_proxy_batch(regex.findall(text), source='auto')
            except: pass
        for ch in TG_CHANNELS:
            base_url = f"https://t.me/s/{ch}"
            for _ in range(15):
                try:
                    r = await asyncio.to_thread(requests.get, base_url, headers=headers, timeout=10)
                    matches = regex.findall(r.text)
                    if matches: db.save_proxy_batch([l.strip().split('<')[0] for l in matches], source='auto')
                    if 'tme_messages_more' not in r.text: break
                    match = re.search(r'href="(/s/.*?before=\d+)"', r.text)
                    base_url = "https://t.me" + match.group(1) if match else None
                    if not base_url: break
                except: break
        await asyncio.sleep(1800)

async def checker_task():
    sem = asyncio.Semaphore(100)
    while True:
        candidates = db.get_proxies_to_check(150)
        if candidates:
            results = []
            async def verify(u):
                async with sem:
                    try:
                        if "vmess" in u:
                            d_str = safe_decode(u[8:])
                            if not d_str: return
                            d = json.loads(d_str); host, port = d['add'], int(d['port'])
                        else:
                            pr = urlparse(u); host, port = pr.hostname, pr.port
                        if not host or not port: return
                        st = time.time(); _, w = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=TIMEOUT)
                        lat = int((time.time() - st) * 1000); w.close(); await w.wait_closed()
                        if lat > 10: results.append((u, lat, host))
                    except: db.update_proxy_status(u, None, 3, "UN")
            
            await asyncio.gather(*(verify(u) for u in candidates))
            if results:
                geo_map = await get_countries_batch([r[2] for r in results])
                for u, lat, host in results:
                    cc = geo_map.get(host, "UN")
                    db.update_proxy_status(u, lat, get_tier(u), cc)
                
                from keep_alive import generate_clash_yaml
                push_to_github(generate_clash_yaml(db.get_best_proxies_for_sub()))
        await asyncio.sleep(10)

async def vacuum_job():
    asyncio.create_task(scraper_task())
    asyncio.create_task(checker_task())
    while True: await asyncio.sleep(3600)
