import os
from aiohttp import web

STATIC_SUB_PATH = "clash_sub.yaml"

async def handle_home(request):
    return web.Response(text="Iron Monk Center is Running!")

async def handle_sub(request):
    """Просто отдает файл с диска"""
    if os.path.exists(STATIC_SUB_PATH):
        return web.FileResponse(STATIC_SUB_PATH)
    else:
        # Если файла еще нет (первый запуск), отдаем пустой список
        return web.Response(text="proxies: []", content_type='text/yaml')

async def start_server():
    app = web.Application()
    app.router.add_get('/', handle_home)
    app.router.add_get('/sub', handle_sub)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8080)
    await site.start()
