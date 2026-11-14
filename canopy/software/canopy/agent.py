"""Claude-based agricultural assistant.

Uses the Anthropic Messages API with tool use (https://docs.claude.com/en/docs/agents-and-tools/tool-use/overview).
Claude never touches hardware directly: every tool goes through Engine, so controller interlocks, override
time-limits and setpoint bounds apply to the assistant exactly as they do to a human at the dashboard.
"""
from __future__ import annotations
import json, logging, os, time
from .control import KINDS
from .config import SETPOINT_BOUNDS

log = logging.getLogger("canopy.agent")

SYSTEM = """You are Canopy, the assistant built into a greenhouse controller at "{site}". You help the grower \
understand conditions, spot problems early and operate the greenhouse.
- Ground every statement about the greenhouse in tool results; call get_status before answering questions about \
current conditions and get_history for trends. Never invent readings.
- Give practical horticultural advice (VPD, DLI, irrigation timing, disease pressure) sized to what the sensors show, \
and say when you are unsure or when a reading looks like a sensor fault.
- You can switch outputs (time-limited overrides) and change setpoints. Do so only when the grower asks or clearly \
agrees; state exactly what you changed. Safety interlocks in the controller may refuse or shorten an action - \
report that honestly.
- Replies may be spoken aloud: keep them short and plain, no markdown, units spelled naturally.
Current local time: {now}."""

TOOLS = [
    {"name": "get_status", "description": "Current sensor readings, actuator states with the reason for each, active alerts, today's water use and all setpoints.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "get_history", "description": "Bucketed history (avg/min/max) for one sensor over the last N hours.",
     "input_schema": {"type": "object", "properties": {
         "sensor": {"type": "string", "description": "air_temp, humidity, soil_moisture, light, co2, water_flow, or a wireless node key like 'bench2.temperature'"},
         "hours": {"type": "number", "minimum": 0.25, "maximum": 720}}, "required": ["sensor", "hours"]}},
    {"name": "get_events", "description": "Recent alerts, actuator switches and configuration changes.",
     "input_schema": {"type": "object", "properties": {"hours": {"type": "number", "minimum": 1, "maximum": 720}}, "required": ["hours"]}},
    {"name": "set_actuator", "description": "Manually override an output for a limited time, or return it to automatic control. Interlocks still apply.",
     "input_schema": {"type": "object", "properties": {
         "actuator": {"type": "string", "enum": list(KINDS)}, "state": {"type": "string", "enum": ["on", "off", "auto"]},
         "minutes": {"type": "number", "minimum": 1, "maximum": 240, "description": "Override duration; irrigation is capped at 30."}},
         "required": ["actuator", "state"]}},
    {"name": "set_setpoints", "description": "Change one or more automation setpoints. Values outside safe bounds are rejected. Allowed keys: " + ", ".join(SETPOINT_BOUNDS) + ", lights_on, lights_off (HH:MM).",
     "input_schema": {"type": "object", "properties": {"changes": {"type": "object"}}, "required": ["changes"]}},
]


class Assistant:
    def __init__(self, engine, client=None):
        self.engine, self.cfg = engine, engine.cfg["claude"]
        self.client = client
        self.history: list[dict] = []

    def _client(self):
        if self.client is None:
            key = os.environ.get(self.cfg["api_key_env"])
            if not key:
                raise RuntimeError(f"Claude is not configured: set {self.cfg['api_key_env']} in /etc/canopy/canopy.env")
            import anthropic
            self.client = anthropic.Anthropic(api_key=key, max_retries=3, timeout=60)
        return self.client

    # ---- tools
    def run_tool(self, name: str, args: dict, source: str = "claude"):
        e = self.engine
        if name == "get_status": return e.status()
        if name == "get_history":
            hours = min(max(float(args["hours"]), 0.25), 720); now = e.clock()
            bucket = 300 if hours <= 6 else 1800 if hours <= 48 else 3600
            rows = e.store.history(args["sensor"], now - hours * 3600, now, bucket)
            if args["sensor"] == "water_flow":
                return {"sensor": "water_flow", "total_l": round(e.store.total("water_flow", now - hours * 3600, now), 1), "hours": hours}
            step = max(1, len(rows) // 60)
            return {"sensor": args["sensor"], "bucket_s": bucket * step, "points": [
                {"t": time.strftime("%m-%d %H:%M", time.localtime(r["ts"])), "avg": round(r["avg"], 2), "min": round(r["min"], 2), "max": round(r["max"], 2)}
                for r in rows[::step]]}
        if name == "get_events":
            return {"events": [{"t": time.strftime("%m-%d %H:%M", time.localtime(x["ts"])), "level": x["level"], "kind": x["kind"], "message": x["message"]}
                               for x in e.store.events(e.clock() - float(args["hours"]) * 3600, 60)]}
        if name in ("set_actuator", "set_setpoints") and not self.cfg.get("allow_control", True):
            return {"error": "Control by the assistant is disabled in the configuration (claude.allow_control)."}
        if name == "set_actuator":
            st = {"on": True, "off": False, "auto": None}[args["state"]]
            e.override(args["actuator"], st, args.get("minutes", 30), source)
            a = e.status()["actuators"][args["actuator"]]
            return {"requested": args["state"], "actual": "on" if a["on"] else "off", "reason": a["reason"], "override_min_left": a["override_min_left"]}
        if name == "set_setpoints":
            return {"setpoints": e.set_setpoints(args["changes"], source)}
        raise ValueError(f"unknown tool {name}")

    # ---- conversation
    def ask(self, text: str, source: str = "claude") -> str:
        client = self._client()
        self.history.append({"role": "user", "content": text})
        self.history = self.history[-20:]
        while self.history and not (self.history[0]["role"] == "user" and isinstance(self.history[0]["content"], str)):
            self.history.pop(0)                    # never start on an orphaned tool_result
        system = SYSTEM.format(site=self.engine.cfg["site"]["name"], now=self.engine.status()["time"])
        for _ in range(8):                         # bounded tool loop
            resp = client.messages.create(model=self.cfg["model"], max_tokens=self.cfg["max_tokens"], system=system,
                                          tools=TOOLS, messages=self.history)
            self.history.append({"role": "assistant", "content": [b.model_dump() if hasattr(b, "model_dump") else b for b in resp.content]})
            if resp.stop_reason != "tool_use":
                return "".join(getattr(b, "text", "") for b in resp.content if getattr(b, "type", "") == "text").strip()
            results = []
            for b in resp.content:
                if getattr(b, "type", "") != "tool_use": continue
                try: out, err = self.run_tool(b.name, b.input or {}, source), False
                except Exception as ex:
                    log.warning("tool %s failed: %s", b.name, ex); out, err = {"error": str(ex)}, True
                results.append({"type": "tool_result", "tool_use_id": b.id, "content": json.dumps(out, default=str), "is_error": err})
            self.history.append({"role": "user", "content": results})
        return "I could not finish that request - too many steps were needed. Please try a simpler question."
