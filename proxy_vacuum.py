import asyncio, requests, re, json, base64, time, logging, yaml, os, random
from bs4 import BeautifulSoup
from urllib.parse import urlparse
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
    try: return base64.b64decode(s + '=' * (-len(s) % 4)).decode('utf-8', errors='ignore')
    except: return ""

async def get_countries_batch(ips):
    if not ips: return {}
    res_map = {}
    try:
        unique_ips = list(set(ips))
        r = await asyncio.to_thread(requests.post, "http://ip-api.com/batch?fields=query,countryCode", json=[{"query": i} for i in unique_ips], timeout=10)
        for item in r.json(): res_map[item['query']] = item.get('countryCode', 'UN')
    except: pass
    return res_map

async def scraper_task():
    regex = re.compile(r'(?:vless|vmess|ss|ssr|trojan|hy2|hysteria)://[^\s<"\'\)]+')
    headers = {'User-Agent': 'Mozilla/5.0'}
    while True:
        logging.info("📥 [Scraper] Сбор...")
        # Гитхаб
        for url in EXTERNAL_SUBS:
            try:
                r = await asyncio.to_thread(requests.get, url, headers=headers, timeout=10)
                t = r.text if "://" in r.text[:50] else safe_decode(r.text)
                found = regex.findall(t)
                if found: db.save_proxy_batch([l.strip() for l in found])
            except: pass
        # ТГ - Глубокий поиск (30 страниц)
        for ch in TG_CHANNELS:
            url = f"https://t.me/s/{ch}"
            for _ in range(30):
                try:
                    r = await asyncio.to_thread(requests.get, url, headers=headers, timeout=5)
                    found = regex.findall(r.text)
                    if found: db.save_proxy_batch([l.strip().split('<')[0] for l in found])
                    if 'tme_messages_more' not in r.text: break
                    match = re.search(r'href="(/s/.*?)"', r.text)
                    if match: url = "https://t.me" + match.group(1)
                    else: break
                except: break
        await asyncio.sleep(1200)

async def checker_task():
    sem = asyncio.Semaphore(50)
    while True:
        candidates = db.get_proxies_to_check(100)
        if candidates:
            results = []
            async def verify(url):
                async with sem:
                    try:
                        if "vmess" in url: d = json.loads(safe_decode(url[8:])); host, port = d['add'], int(d['port'])
                        else: p = urlparse(url); host, port = p.hostname, p.port
                        if not host or not port: return
                        st = time.time()
                        _, w = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=1.5)
                        lat = int((time.time() - st) * 1000)
                        w.close(); await w.wait_closed()
                        results.append({'url': url, 'lat': lat, 'ip': host})
                    except: db.update_proxy_status(url, None, 0, "UN")
            
            await asyncio.gather(*(verify(u) for u in candidates))
            
            if results:
                geo_map = await get_countries_batch([r['ip'] for r in results])
                for r in results:
                    cc = geo_map.get(r['ip'], "UN")
                    # Условие AI: быстрый и не РФ/Китай/Иран
                    is_ai = 1 if r['lat'] < 350 and cc not in ['RU','CN','IR'] else 0
                    db.update_proxy_status(r['url'], r['lat'], is_ai, cc)
                
                update_static_file()
        await asyncio.sleep(5)

def update_static_file():
    import yaml
    from keep_alive import link_to_clash_dict
    try:
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
                "proxy-groups": [{"name": "🚀 Auto Select", "type": "url-test", "url": "http://www.gstatic.com/generate_204", "interval": 300, "proxies": [p['name'] for p in clash_proxies]}],
                "rules": ["MATCH,🚀 Auto Select"]
            }
            # АТОМАРНАЯ ЗАПИСЬ (убирает Connection Closed)
            tmp = FINAL_SUB_PATH + ".tmp"
            with open(tmp, 'w', encoding='utf-8') as f:
                yaml.dump(full_config, f, allow_unicode=True, sort_keys=False)
            os.replace(tmp, FINAL_SUB_PATH)
    except: pass

async def vacuum_job():
    asyncio.create_task(scraper_task())
    asyncio.create_task(checker_task())
    while True: await asyncio.sleep(3600)
