
import asyncio
import requests
import re
import base64
import json
import time
import logging
import os
import random
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




FINAL_SUB_PATH = "clash_sub.yaml"

def safe_decode(s):
    try: return base64.b64decode(s + '=' * (-len(s) % 4)).decode('utf-8', errors='ignore')
    except: return ""

async def get_geo_info_batch(ips):
    """Узнает страны и провайдеров пачкой (лимит 100)"""
    if not ips: return {}
    res_map = {}
    try:
        unique_ips = list(set(ips))
        r = await asyncio.to_thread(requests.post, "http://ip-api.com/batch?fields=query,countryCode,isp", json=[{"query": i} for i in unique_ips], timeout=10)
        for item in r.json():
            # Если провайдер хостинговый - помечаем
            isp = item.get('isp', '').lower()
            is_hosting = any(h in isp for h in ['amazon','google','oracle','azure','digitalocean','hetzner','m247','ovh','cloudflare'])
            res_map[item['query']] = {
                'cc': item.get('countryCode', 'UN'),
                'is_hosting': is_hosting
            }
    except: pass
    return res_map

async def scraper_task():
    regex = re.compile(r'(?:vless|vmess|ss|ssr|trojan|hy2|hysteria)://[^\s<"\'\)]+')
    headers = {'User-Agent': 'Mozilla/5.0'}
    while True:
        logging.info("📥 [Scraper] Сбор...")
        for url in EXTERNAL_SUBS:
            try:
                r = await asyncio.to_thread(requests.get, url, headers=headers, timeout=10)
                t = r.text if "://" in r.text[:50] else safe_decode(r.text)
                found = regex.findall(t)
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
    sem = asyncio.Semaphore(50)
    while True:
        candidates = db.get_proxies_to_check(100)
        if candidates:
            logging.info(f"🧪 [Checker] Проверяю {len(candidates)} шт...")
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
                # Получаем ГЕО пачкой
                geo_map = await get_geo_info_batch([r['ip'] for r in results])
                for r in results:
                    info = geo_map.get(r['ip'], {'cc': 'UN', 'is_hosting': True})
                    # AI-Ready если: быстрый пинг И не на хостинге И страна не РФ/Китай
                    is_ai = 1 if r['lat'] < 250 and not info['is_hosting'] and info['cc'] not in ['RU','CN','IR'] else 0
                    db.update_proxy_status(r['url'], r['lat'], is_ai, info['cc'])
                
                from proxy_vacuum import update_static_file
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
                "proxy-groups": [{"name": "🚀 Auto Select", "type": "url-test", "url": "http://www.gstatic.com/generate_204", "interval": 1000, "proxies": [p['name'] for p in clash_proxies]}],
                "rules": ["MATCH,🚀 Auto Select"]
            }
            tmp = FINAL_SUB_PATH + ".tmp"
            with open(tmp, 'w', encoding='utf-8') as f:
                yaml.dump(full_config, f, allow_unicode=True, sort_keys=False)
            os.replace(tmp, FINAL_SUB_PATH)
            logging.info(f"💾 Подписка обновлена: {len(clash_proxies)} шт.")
    except Exception as e: logging.error(f"Config error: {e}")

async def vacuum_job():
    asyncio.create_task(scraper_task())
    asyncio.create_task(checker_task())
    while True: await asyncio.sleep(3600)
