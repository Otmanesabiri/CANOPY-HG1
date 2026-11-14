"""Entry point:  python -m canopy [-c /etc/canopy/config.yaml]"""
import argparse, asyncio, logging
from aiohttp import web
from . import config
from .engine import Engine
from .agent import Assistant
from .webapp import make_app


async def amain(cfg):
    log = logging.getLogger("canopy")
    engine = Engine(cfg); assistant = Assistant(engine)
    for name, flag in (("radios.start_zigbee", cfg["mqtt"]["enabled"]), ("radios.start_lora", cfg["lora"]["enabled"]), ("voice.start", cfg["voice"]["enabled"])):
        if not flag: continue
        try:                                                    # optional subsystems must never stop automation
            mod, fn = name.split("."); m = __import__(f"canopy.{mod}", fromlist=[fn])
            getattr(m, fn)(*((engine, assistant) if mod == "voice" else (engine,)))
            log.info("%s started", name)
        except Exception as e:
            log.error("%s failed to start: %s", name, e); engine.store.event("error", "subsystem", f"{name} failed to start: {e}")
    runner = web.AppRunner(make_app(engine, assistant)); await runner.setup()
    await web.TCPSite(runner, cfg["web"]["host"], cfg["web"]["port"]).start()
    log.info("dashboard on http://%s:%s (%s mode)", cfg["web"]["host"], cfg["web"]["port"], cfg["hardware"]["mode"])
    await engine.run()


def main():
    ap = argparse.ArgumentParser(prog="canopy"); ap.add_argument("-c", "--config", default="/etc/canopy/config.yaml")
    ap.add_argument("-v", "--verbose", action="store_true"); a = ap.parse_args()
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    try: asyncio.run(amain(config.load(a.config)))
    except KeyboardInterrupt: pass


if __name__ == "__main__":
    main()
