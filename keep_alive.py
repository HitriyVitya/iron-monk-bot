import os
from aiohttp import web

FINAL_SUB_PATH = "clash_sub.yaml"

async def handle_sub(request):
    if os.path.exists(FINAL_SUB_PATH):
        return web.FileResponse(FINAL_SUB_PATH)
    return web.Response(text="proxies: []", content_type='text/yaml')

async def start_server():
    app = web.Application()
    app.router.add_get('/', lambda r: web.Response(text="Monk Center Online"))
    app.router.add_get('/sub', handle_sub)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8080)
    await site.start()
