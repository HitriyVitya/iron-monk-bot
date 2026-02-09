from aiohttp import web
import database_vpn as db
import base64

async def handle_home(request):
    return web.Response(text="Monk Bot is Alive. /sub for proxies.")

async def handle_sub(request):
    proxies = db.get_best_proxies_for_sub()
    text = "\n".join(proxies)
    # Кодируем в Base64 для клиентов
    b64 = base64.b64encode(text.encode()).decode()
    return web.Response(text=b64)

async def start_server():
    app = web.Application()
    app.router.add_get('/', handle_home)
    app.router.add_get('/sub', handle_sub)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8080)
    await site.start()
