"""Web dashboard + REST API (aiohttp). Read endpoints are open on the LAN; anything that changes state needs the token."""
from __future__ import annotations
import asyncio, hmac, json, os, time
from aiohttp import web
from .control import KINDS

HERE = os.path.dirname(__file__)


def make_app(engine, assistant=None) -> web.Application:
    token = engine.cfg["web"].get("token") or os.environ.get("CANOPY_WEB_TOKEN", "")

    def auth(req):
        if not token: return        # no token configured: LAN-trust mode (first-boot default is a generated token)
        got = req.headers.get("Authorization", "").removeprefix("Bearer ").strip() or req.cookies.get("canopy_token", "")
        if not hmac.compare_digest(got, token): raise web.HTTPUnauthorized(text="token required")

    async def body(req):
        try: return await req.json()
        except Exception: raise web.HTTPBadRequest(text="JSON body required")

    async def index(req): return web.FileResponse(os.path.join(HERE, "web", "index.html"))
    async def status(req): return web.json_response(engine.status())

    async def history(req):
        sensor = req.query.get("sensor", "air_temp"); hours = min(float(req.query.get("hours", 24)), 24 * 365)
        bucket = 300 if hours <= 12 else 1800 if hours <= 72 else 3600
        now = engine.clock()
        return web.json_response({"sensor": sensor, "points": engine.store.history(sensor, now - hours * 3600, now, bucket)})

    async def events(req):
        return web.json_response({"events": engine.store.events(engine.clock() - float(req.query.get("hours", 48)) * 3600, 200),
                                  "actuations": engine.store.actuations(engine.clock() - float(req.query.get("hours", 48)) * 3600, 200)})

    async def actuator(req):
        auth(req); kind = req.match_info["kind"]; d = await body(req)
        if kind not in KINDS or d.get("state") not in ("on", "off", "auto"): raise web.HTTPBadRequest(text="bad actuator or state")
        engine.override(kind, {"on": True, "off": False, "auto": None}[d["state"]], float(d.get("minutes", 30)), "dashboard")
        return web.json_response(engine.status()["actuators"][kind])

    async def setpoints(req):
        auth(req)
        try: return web.json_response(engine.set_setpoints(await body(req), "dashboard"))
        except ValueError as e: raise web.HTTPBadRequest(text=str(e))

    async def chat(req):
        auth(req); d = await body(req)
        if assistant is None or not d.get("message"): raise web.HTTPBadRequest(text="assistant unavailable or empty message")
        try: reply = await asyncio.get_running_loop().run_in_executor(None, assistant.ask, str(d["message"])[:4000], "claude")
        except Exception as e: raise web.HTTPServiceUnavailable(text=f"assistant error: {e}")
        return web.json_response({"reply": reply})

    async def stream(req):                                   # server-sent events: live status
        resp = web.StreamResponse(headers={"Content-Type": "text/event-stream", "Cache-Control": "no-cache"})
        await resp.prepare(req); q: asyncio.Queue = asyncio.Queue(maxsize=5); loop = asyncio.get_running_loop()
        def push(st):
            loop.call_soon_threadsafe(lambda: q.full() or q.put_nowait(st))
        engine.listeners.append(push)
        try:
            await resp.write(f"data: {json.dumps(engine.status())}\n\n".encode())
            while True:
                await resp.write(f"data: {json.dumps(await q.get())}\n\n".encode())
        except (ConnectionResetError, asyncio.CancelledError): pass
        finally: engine.listeners.remove(push)
        return resp

    async def health(req): return web.json_response({"ok": True, "t": time.time()})

    app = web.Application(client_max_size=64 * 1024)
    app.add_routes([web.get("/", index), web.get("/api/status", status), web.get("/api/history", history), web.get("/api/events", events),
                    web.get("/api/stream", stream), web.post("/api/actuators/{kind}", actuator), web.put("/api/setpoints", setpoints),
                    web.post("/api/chat", chat), web.get("/healthz", health)])
    return app
