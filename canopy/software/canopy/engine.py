"""Runtime engine: polls sensors, runs the controller, drives outputs, records history, raises alerts."""
from __future__ import annotations
import asyncio, datetime as dt, functools, logging, os, socket, threading, time
from zoneinfo import ZoneInfo
from . import config as cfgmod, hal
from .control import Controller, KINDS
from .store import Store

log = logging.getLogger("canopy")
UNITS = {"air_temp": "°C", "humidity": "%", "soil_moisture": "%", "light": "lx", "co2": "ppm", "water_flow": "L", "soil_temp": "°C"}


def sd_notify(msg: str):
    """Minimal systemd notify (READY=1 / WATCHDOG=1) without extra dependencies."""
    path = os.environ.get("NOTIFY_SOCKET")
    if not path: return
    if path[0] == "@": path = "\0" + path[1:]
    with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as s:
        try: s.sendto(msg.encode(), path)
        except OSError: pass


def _locked(fn):
    @functools.wraps(fn)
    def w(self, *a, **k):
        with self.lock:
            return fn(self, *a, **k)
    return w


class Engine:
    def __init__(self, cfg: dict, board=None, store: Store | None = None, clock=time.time):
        self.cfg, self.clock = cfg, clock
        self.lock = threading.RLock()        # tick / dashboard / assistant / radios run on different threads
        self.board = board or hal.make(cfg)
        self.store = store or Store(cfg["storage"]["path"], cfg["storage"]["raw_days"])
        saved = self.store.get("setpoints")
        if saved and not cfgmod.validate_setpoints({**cfg["setpoints"], **saved}):
            cfg["setpoints"].update(saved)
        self.ctl = Controller(cfg["setpoints"], cfg["alerts"], ZoneInfo(cfg["site"]["timezone"]))
        self.latest: dict[str, float] = {}; self.seen: dict[str, float] = {}
        self.extra: dict[str, dict] = {}            # wireless (Zigbee / LoRa) node readings
        self.listeners: list = []; self._last_rollup = 0.0
        self.board.all_off()

    # ---- external inputs
    @_locked
    def ingest(self, source: str, values: dict):
        """Readings from wireless nodes; keys matching core kinds feed the controller, the rest are just logged."""
        now = self.clock()
        self.extra[source] = {"ts": now, **values}
        for k, v in values.items():
            if isinstance(v, (int, float)):
                key = k if k in UNITS and k not in ("water_flow",) and self.cfg["hardware"].get("wireless_feeds_control") else f"{source}.{k}"
                self.latest[key] = float(v); self.seen[key] = now
        self.store.add_readings(now, {f"{source}.{k}": v for k, v in values.items() if isinstance(v, (int, float))})

    @_locked
    def set_setpoints(self, changes: dict, source: str) -> dict:
        unknown = [k for k in changes if k not in self.cfg["setpoints"]]
        if unknown: raise ValueError(f"unknown setpoint(s): {', '.join(unknown)}")
        new = {**self.cfg["setpoints"], **changes}
        errs = cfgmod.validate_setpoints(new)
        if errs: raise ValueError("; ".join(errs))
        self.cfg["setpoints"].update(changes)
        self.store.set("setpoints", self.cfg["setpoints"])
        self.store.event("info", "setpoints", f"Setpoints changed by {source}: {changes}", changes, self.clock())
        return self.cfg["setpoints"]

    @_locked
    def override(self, kind: str, state: bool | None, minutes: float = 30, source: str = "manual"):
        self.ctl.set_override(kind, state, self.clock(), minutes, source)
        self.store.event("info", "override", f"{kind} -> {'auto' if state is None else 'on' if state else 'off'} by {source}"
                         + ("" if state is None else f" for {minutes:g} min"), None, self.clock())
        self.tick(read=False)

    # ---- one cycle
    @_locked
    def tick(self, read: bool = True):
        now = self.clock(); flow = 0.0
        if read:
            try: vals = self.board.read()
            except Exception as e:                       # a sensor bus failure must never kill the control loop
                log.exception("sensor read failed"); vals = {}
                self.store.event("error", "sensor", f"Sensor read failed: {e}", None, now)
            flow = vals.get("water_flow", 0.0) or 0.0
            for k, v in vals.items():
                if v is not None: self.latest[k] = float(v); self.seen[k] = now
            self.store.add_readings(now, vals)
        ages = {k: now - t for k, t in self.seen.items()}
        changed = self.ctl.step(now, self.latest, ages, flow)
        for kind, on in changed.items():
            try: self.board.write(kind, on)
            except Exception as e:
                log.exception("actuator write failed"); self.store.event("error", "actuator", f"Failed to switch {kind}: {e}", None, now)
            src = self.ctl.overrides[kind].source if kind in self.ctl.overrides else "auto"
            self.store.actuation(now, kind, on, src, self.ctl.reasons[kind])
        for k, msg in self.ctl.new_alerts.items(): self.store.event("alert", k, msg, None, now)
        for k in self.ctl.cleared_alerts: self.store.event("info", k, f"Alert cleared: {k}", None, now)
        if now - self._last_rollup > 3600: self.store.rollup(now); self._last_rollup = now
        for fn in self.listeners: fn(self.status())
        return changed

    @_locked
    def status(self) -> dict:
        now = self.clock()
        return {
            "time": dt.datetime.fromtimestamp(now, self.ctl.tz).isoformat(timespec="seconds"), "site": self.cfg["site"]["name"],
            "sensors": {k: {"value": round(v, 2), "unit": UNITS.get(k.split(".")[-1], ""), "age_s": round(now - self.seen[k])} for k, v in self.latest.items() if k != "water_flow"},
            "water_today_l": round(self.ctl.litres_today, 1),
            "actuators": {k: {"on": self.ctl.state[k], "reason": self.ctl.reasons[k],
                              "override_min_left": round((self.ctl.overrides[k].until - now) / 60, 1) if k in self.ctl.overrides else None} for k in KINDS},
            "alerts": self.ctl.alerts, "setpoints": self.cfg["setpoints"], "mode": self.cfg["hardware"]["mode"],
        }

    async def run(self):
        sd_notify("READY=1"); period = self.cfg["hardware"]["poll_s"]
        try:
            while True:
                t0 = time.monotonic()
                await asyncio.get_running_loop().run_in_executor(None, self._tick_real)
                sd_notify("WATCHDOG=1")
                await asyncio.sleep(max(0.1, period - (time.monotonic() - t0)))
        finally:
            self.board.all_off()                           # outputs off on any exit path

    def _tick_real(self):
        if isinstance(self.board, hal.SimGreenhouse): self.board.advance(self.cfg["hardware"]["poll_s"] * self.cfg["hardware"].get("sim_speed", 1))
        self.tick()
