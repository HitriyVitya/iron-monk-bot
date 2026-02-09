import asyncio
import requests
import re
import base64
import json
import time
import logging
import subprocess
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

SINGBOX_BIN = "./sing-box"
FINAL_SUB_PATH = "clash_sub.yaml"

MAX_LINKS_PER_CHANNEL = 500
MAX_PAGES_TG = 10

def safe_decode(s):
    try:
        s = re.sub(r'[^a-zA-Z0-9+/=]', '', s)
        return base64.b64decode(s + '=' * (-len(s) % 4)).decode('utf-8', errors='ignore')
    except: return ""

# --- КОНВЕРТЕР ДЛЯ SING-BOX ---
def link_to_singbox_outbound(link):
    try:
        if link.startswith("vmess://"):
            d = json.loads(safe_decode(link[8:]))
            out = {"type": "vmess", "tag": "proxy", "server": d['add'], "server_port": int(d['port']), "uuid": d['id'], "security": "auto"}
            if d.get('net') == 'ws': out["transport"] = {"type": "ws", "path": d.get('path', '/')}
            if d.get('tls') == 'tls': out["tls"] = {"enabled": True, "insecure": True}
            return out
        if link.startswith("vless://"):
            p = urlparse(link); q = parse_qs(p.query)
            out = {"type": "vless", "tag": "proxy", "server": p.hostname, "server_port": p.port, "uuid": p.username}
            if q.get('security', [''])[0] == 'reality':
                out["tls"] = {"enabled": True, "server_name": q.get('sni', [''])[0], "reality": {"enabled": True, "public_key": q.get('pbk', [''])[0], "short_id": q.get('sid', [''])[0]}, "utls": {"enabled": True, "fingerprint": "chrome"}}
            elif q.get('security', [''])[0] == 'tls':
                out["tls"] = {"enabled": True, "server_name": q.get('sni', [''])[0], "insecure": True}
            if q.get('type', [''])[0] == 'ws':
                out["transport"] = {"type": "ws", "path": q.get('path', ['/'])[0]}
            return out
        if link.startswith("ss://"):
            main = link.split("#")[0].replace("ss://", "")
            if "@" in main:
                u, s = main.split("@", 1); d = safe_decode(u)
                m, pw = d.split(":", 1) if ":" in d else (u.split(":", 1) if ":" in u else ("aes-256-gcm", u))
                return {"type": "shadowsocks", "tag": "proxy", "server": s.split(":")[0], "server_port": int(s.split(":")[1].split("/")[0]), "method": m, "password": pw}
        if link.startswith("trojan://"):
            p = urlparse(link); q = parse_qs(p.query)
            return {"type": "trojan", "tag": "proxy", "server": p.hostname, "server_port": p.port, "password": p.username, "tls": {"enabled": True, "server_name": q.get('sni', [''])[0], "insecure": True}}
    except: pass
    return None

# --- ТЯЖЕЛАЯ ПРОВЕРКА ЧЕРЕЗ ЯДРО ---
async def heavy_check(url, semaphore):
    async with semaphore:
        port = random.randint(30000, 40000)
        outbound = link_to_singbox_outbound(url)
        if not outbound: return None
        
        config = {
            "log": {"level": "silent"},
            "inbounds": [{"type": "mixed", "listen": "127.0.0.1", "listen_port": port}],
            "outbounds": [outbound, {"type": "direct", "tag": "direct"}]
        }
        
        cfg_file = f"cfg_{port}.json"
        with open(cfg_file, 'w') as f: json.dump(config, f)
        
        proc = None
        try:
            # Запускаем ядро
            proc = subprocess.Popen([SINGBOX_BIN, "run", "-c", cfg_file], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            await asyncio.sleep(2.0) # Даем время на коннект
            
            # Тест 1: Обычный Гугл
            start = time.time()
            check = await asyncio.create_subprocess_shell(
                f"curl -x socks5h://127.0.0.1:{port} -s -o /dev/null -w '%{{http_code}}' --max-time 5 http://www.google.com/generate_204",
                stdout=asyncio.subprocess.PIPE
            )
            stdout, _ = await asyncio.wait_for(check.communicate(), timeout=6)
            lat = int((time.time() - start) * 1000)
            
            if stdout.decode().strip() == "204":
                # Тест 2: Google AI Studio (Gemini)
                ai_check = await asyncio.create_subprocess_shell(
                    f"curl -x socks5h://127.0.0.1:{port} -s -o /dev/null -w '%{{http_code}}' --max-time 5 https://aistudio.google.com",
                    stdout=asyncio.subprocess.PIPE
                )
                ai_out, _ = await ai_check.communicate()
                # 200 или 403 (если блок региона, но прокси работает) - считаем что AI тянет
                is_ai = 1 if ai_out.decode().strip() in ["200", "403"] else 0
                return {"url": url, "lat": lat, "is_ai": is_ai}
        except: pass
        finally:
            if proc: proc.terminate()
            if os.path.exists(cfg_file): os.remove(cfg_file)
        return None

# --- ОБНОВЛЕНИЕ ФАЙЛА CLASH ---
def update_clash_file():
    try:
        rows = db.get_best_proxies_for_sub() # (url, lat, is_ai, country)
        import keep_alive
        clash_proxies = []
        for idx, r in enumerate(rows):
            obj = keep_alive.link_to_clash_dict(r[0], r[1], r[2], r[3])
            if obj:
                # ГАРАНТИРУЕМ УНИКАЛЬНОСТЬ ИМЕНИ
                obj['name'] = f"{obj['name']} ({idx})"
                clash_proxies.append(obj)
        
        if not clash_proxies: return

        full_config = {
            "proxies": clash_proxies,
            "proxy-groups": [
                {"name": "🚀 Auto Select", "type": "url-test", "url": "http://www.gstatic.com/generate_204", "interval": 300, "proxies": [p['name'] for p in clash_proxies]},
                {"name": "🌍 GLOBAL", "type": "select", "proxies": ["🚀 Auto Select"] + [p['name'] for p in clash_proxies]}
            ],
            "rules": ["MATCH,🌍 GLOBAL"]
        }
        
        tmp = FINAL_SUB_PATH + ".tmp"
        with open(tmp, 'w', encoding='utf-8') as f:
            yaml.dump(full_config, f, allow_unicode=True, sort_keys=False)
        os.replace(tmp, FINAL_SUB_PATH)
        logging.info(f"💾 Подписка обновлена: {len(clash_proxies)} шт.")
    except Exception as e: logging.error(f"Save error: {e}")

# --- ФОНОВЫЕ ЗАДАЧИ ---
async def scraper_task():
    regex = re.compile(r'(?:vless|vmess|ss|ssr|trojan|hy2|hysteria)://[^\s<"\'\)]+')
    headers = {'User-Agent': 'Mozilla/5.0'}
    while True:
        logging.info("📥 [Scraper] Сбор...")
        for url in EXTERNAL_SUBS:
            try:
                r = await asyncio.to_thread(requests.get, url, headers=headers, timeout=10)
                t = r.text if "://" in r.text[:50] else safe_decode(r.text)
                for l in regex.findall(t): db.save_proxy_batch([l.strip()])
            except: pass
        
        for ch in TG_CHANNELS:
            url = f"https://t.me/s/{ch}"
            for _ in range(MAX_PAGES_TG):
                try:
                    r = await asyncio.to_thread(requests.get, url, headers=headers, timeout=5)
                    found = regex.findall(r.text)
                    if found: db.save_proxy_batch([l.strip().split('<')[0] for l in found])
                    if 'tme_messages_more' not in r.text: break
                    m = re.search(r'href="(/s/.*?)"', r.text)
                    if m: url = "https://t.me" + m.group(1)
                    else: break
                except: break
        await asyncio.sleep(1800)

async def checker_task():
    sem = asyncio.Semaphore(3) # Не больше 3 проверок сразу (Koyeb может упасть от RAM)
    while True:
        candidates = db.get_proxies_to_check(30) # Проверяем по 30 шт
        if not candidates:
            await asyncio.sleep(10); continue
        
        results = await asyncio.gather(*(heavy_check(u, sem) for u in candidates))
        
        for i, res in enumerate(results):
            if res: db.update_proxy_status(res['url'], res['lat'], res['is_ai'], "UN")
            else: db.update_proxy_status(candidates[i], None, 0, "")
        
        update_clash_file()
        await asyncio.sleep(5)

async def vacuum_job():
    asyncio.create_task(scraper_task())
    asyncio.create_task(checker_task())
    while True: await asyncio.sleep(3600)
