from aiohttp import web
import database_vpn as db

# Глобальная переменная для хранения подписки в памяти
PROXY_CACHE = "Base is checking... Please wait 1-2 min."

async def handle_home(request):
    return web.Response(text="Iron Monk Hub is Running!")

async def handle_sub(request):
    """Мгновенный ответ из памяти"""
    return web.Response(text=PROXY_CACHE, content_type='text/plain')

def update_internal_cache():
    """Функция для обновления кэша (будет вызываться из пылесоса)"""
    global PROXY_CACHE
    try:
        proxies = db.get_best_proxies_for_sub()
        if proxies:
            PROXY_CACHE = "\n".join(proxies)
    except:
        pass

async def start_server():
    app = web.Application()
    app.router.add_get('/', handle_home)
    app.router.add_get('/sub', handle_sub)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8080)
    await site.start()
