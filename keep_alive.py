from aiohttp import web

async def handle(request):
    # Просто отвечаем "Я жив", если кто-то зайдет на сайт бота
    return web.Response(text="I am alive! Iron Monk is watching you.")

async def start_server():
    app = web.Application()
    app.router.add_get('/', handle)
    runner = web.AppRunner(app)
    await runner.setup()
    # Порт 8080 - стандарт для Render
    site = web.TCPSite(runner, '0.0.0.0', 8080)
    await site.start()