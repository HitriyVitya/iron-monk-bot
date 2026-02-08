import asyncio
import requests
import re
import database as db
from bs4 import BeautifulSoup

CHANNELS = [
    "shadowsockskeys", "oneclickvpnkeys", "v2ray_outlineir", "v2ray_free_conf", 
    "VlessConfig", "PrivateVPNs", "gurvpn_keys", "vmessh", "VMESS7"
]

# Сколько СТРАНИЦ истории выкачать при первом запуске (потом снизим)
PAGES_DEPTH = 30 

async def scrape_all():
    """Высасывает вообще всё из ТГ"""
    pattern = re.compile(r'(?:vless|vmess|ss|trojan|hy2|tuic)://[^\s<"\'\)]+')
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    for channel in CHANNELS:
        url = f"https://t.me/s/{channel}"
        print(f"📡 Глубокий парсинг: {channel}")
        
        for _ in range(PAGES_DEPTH):
            try:
                resp = requests.get(url, headers=headers, timeout=10)
                soup = BeautifulSoup(resp.text, 'html.parser')
                matches = pattern.findall(resp.text)
                
                if matches:
                    db.add_to_warehouse(matches)
                
                # Листаем назад
                more = soup.find('a', class_='tme_messages_more')
                if more and 'href' in more.attrs:
                    url = "https://t.me" + more['href']
                    await asyncio.sleep(1) # Не частим, чтобы ТГ не забанил
                else: break
            except: break

async def heavy_checker():
    """Бесконечный цикл проверки пачками через Sing-box"""
    while True:
        to_check = db.get_next_proxies_to_check(10) # Берем по 10 штук
        if not to_check:
            await asyncio.sleep(60)
            continue
            
        for url in to_check:
            # ТУТ БУДЕТ ВЫЗОВ SING-BOX (добавим следующим шагом)
            # Пока просто быстрая проверка порта для теста системы
            db.update_proxy_status(url, True, 100, 0) 
            await asyncio.sleep(1)

async def proxy_worker():
    # 1. Первый раз высасываем историю
    await scrape_all()
    # 2. Запускаем вечный чекер
    await heavy_checker()
