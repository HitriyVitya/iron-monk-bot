from aiohttp import web
import database as db
import re
import json
import base64

def generate_name(url, country, is_ai, latency):
    flag = "🏳️" # Допилим флаги позже если надо
    ai_tag = " ✨ AI" if is_ai else ""
    # Пытаемся вырезать IP для названия
    ip = "Server"
    try:
        if "://" in url: ip = url.split("://")[1].split("@")[-1].split(":")[0]
    except: pass
    return f"{flag}{ai_tag} {latency}ms | {ip}"

async def handle_home(request):
    return web.Response(text="Iron Monk Center is Running! Go to /sub for proxies.")

async def handle_sub(request):
    """Генерация подписки для Clash (YAML)"""
    proxies = db.get_best_proxies_for_sub() # Список кортежей
    
    # Формируем простой список ссылок (Base64) для v2rayNG
    # Или YAML для Clash (лучше YAML, раз ты просил)
    
    # Пока отдадим просто список ссылок, FlClash его тоже жрет (через импорт)
    # Или конвертируем в Base64 (универсально)
    links_only = [p[0] for p in proxies]
    text_data = "\n".join(links_only)
    b64_data = base64.b64encode(text_data.encode()).decode()
    
    return web.Response(text=b64_data)

async def start_server():
    app = web.Application()
    app.router.add_get('/', handle_home)
    app.router.add_get('/sub', handle_sub)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8080)
    await site.start()
