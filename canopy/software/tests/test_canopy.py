import copy, datetime as dt, json, types
import pytest
from canopy import config, hal, radios, voice
from canopy.control import Controller, in_window
from canopy.store import Store
from canopy.engine import Engine
from canopy.agent import Assistant
from canopy.webapp import make_app

T0 = dt.datetime(2026, 6, 1, 12, 0, tzinfo=dt.timezone.utc).timestamp()      # noon UTC


def ctl():
    c = config.load(None); return Controller(c["setpoints"], c["alerts"])

GOOD = {"air_temp": 20.0, "humidity": 60.0, "soil_moisture": 40.0, "light": 30000.0, "co2": 600.0}


# ------------------------------------------------------------------ controller
def test_heating_hysteresis():
    c = ctl()
    c.step(T0, {**GOOD, "air_temp": 15.0}); assert c.state["heater"]
    c.step(T0 + 5, {**GOOD, "air_temp": 17.0}); assert c.state["heater"]            # inside band: stays on
    c.step(T0 + 10, {**GOOD, "air_temp": 18.5}); assert not c.state["heater"]
    c.step(T0 + 15, {**GOOD, "air_temp": 17.0}); assert not c.state["heater"]       # inside band: stays off

def test_vent_on_heat_humidity_co2():
    c = ctl(); c.step(T0, {**GOOD, "air_temp": 29.0}); assert c.state["vent"]
    c = ctl(); c.step(T0, {**GOOD, "humidity": 90.0}); assert c.state["vent"]
    c = ctl(); c.step(T0, {**GOOD, "co2": 2500.0}); assert c.state["vent"]
    c = ctl(); c.step(T0, {**GOOD, "humidity": 90.0, "air_temp": 15.0}); assert not c.state["vent"] and c.state["heater"]

def test_interlock_heater_vent_even_with_overrides():
    c = ctl(); c.set_override("heater", True, T0); c.set_override("vent", True, T0)
    c.step(T0, GOOD); assert not (c.state["heater"] and c.state["vent"])
    c = ctl(); c.set_override("heater", True, T0); c.step(T0, {**GOOD, "air_temp": 39.0})
    assert not c.state["heater"] and "temp_high" in c.alerts

def test_failsafe_on_missing_or_stale_temperature():
    c = ctl(); c.step(T0, {**GOOD, "air_temp": 10.0}); assert c.state["heater"]
    c.step(T0 + 5, {**GOOD, "air_temp": 10.0}, ages={"air_temp": 500})
    assert not c.state["heater"] and "sensor_air_temp" in c.alerts
    c = ctl(); c.step(T0, {k: v for k, v in GOOD.items() if k != "soil_moisture"}); assert not c.state["irrigation"] and "sensor_soil" in c.alerts

def test_irrigation_pulse_soak_and_daily_cap():
    c = ctl(); dry = {**GOOD, "soil_moisture": 20.0}
    c.step(T0, dry); assert c.state["irrigation"]
    c.step(T0 + 30, dry, flow_l=6); assert c.state["irrigation"]
    c.step(T0 + 61, dry, flow_l=6); assert not c.state["irrigation"]                # pulse over
    c.step(T0 + 300, dry); assert not c.state["irrigation"]                         # still soaking
    c.step(T0 + 61 + 901, dry); assert c.state["irrigation"]                        # soak over, still dry
    c.step(T0 + 61 + 905, dry, flow_l=500); assert not c.state["irrigation"]        # cap hit -> interlock
    c.step(T0 + 4000, dry); assert not c.state["irrigation"] and "water_limit" in c.alerts
    c.set_override("irrigation", True, T0 + 4001); c.step(T0 + 4001, dry); assert not c.state["irrigation"]   # cap beats override

def test_irrigation_window_and_wet_stop():
    c = ctl(); night = T0 + 12 * 3600
    c.step(night, {**GOOD, "soil_moisture": 20.0}); assert not c.state["irrigation"]
    c = ctl(); c.step(T0, {**GOOD, "soil_moisture": 20.0}); c.step(T0 + 10, {**GOOD, "soil_moisture": 50.0}); assert not c.state["irrigation"]

def test_override_expires_and_is_capped():
    c = ctl(); c.set_override("lights", False, T0, minutes=100000)
    assert c.overrides["lights"].until <= T0 + 240 * 60
    c.step(T0, {**GOOD, "light": 100.0}); assert not c.state["lights"]
    c.step(T0 + 241 * 60, {**GOOD, "light": 100.0}); assert c.state["lights"]
    c.set_override("irrigation", True, T0, minutes=500); assert c.overrides["irrigation"].until <= T0 + 30 * 60

def test_lights_photoperiod_and_lux_hysteresis():
    c = ctl(); c.step(T0, {**GOOD, "light": 5000.0}); assert c.state["lights"]
    c.step(T0 + 5, {**GOOD, "light": 15000.0}); assert c.state["lights"]
    c.step(T0 + 10, {**GOOD, "light": 25000.0}); assert not c.state["lights"]
    c = ctl(); c.step(T0 + 11 * 3600, {**GOOD, "light": 0.0}); assert not c.state["lights"]   # 23:00
    assert in_window(dt.time(23, 0), "22:00", "06:00") and not in_window(dt.time(12, 0), "22:00", "06:00")

def test_leak_alert():
    c = ctl()
    for i in range(4): c.step(T0 + 100 + i * 5, GOOD, flow_l=0.2)
    assert "leak" in c.alerts


# ------------------------------------------------------------------ config / store
def test_setpoint_validation():
    sp = config.load(None)["setpoints"]
    assert config.validate_setpoints(sp) == []
    assert config.validate_setpoints({**sp, "heat_on_below_c": 60})
    assert config.validate_setpoints({**sp, "heat_off_above_c": 27.0})             # overlaps ventilation band
    assert config.validate_setpoints({**sp, "lights_on": "25:00"})

def test_store_history_rollup_retention():
    s = Store(raw_days=1)
    for i in range(0, 3 * 86400, 600): s.add_readings(T0 + i, {"air_temp": 20 + (i % 3600) / 3600})
    now = T0 + 3 * 86400; s.rollup(now)
    assert s.db.execute("SELECT COUNT(*) FROM readings WHERE ts<?", (now - 86400,)).fetchone()[0] == 0
    h = s.history("air_temp", T0, now, 3600)
    assert 70 <= len(h) <= 73 and h[0]["ts"] <= T0 + 3600 and abs(h[5]["avg"] - 20.42) < 0.1
    s.set("k", {"a": 1}); assert s.get("k") == {"a": 1}


# ------------------------------------------------------------------ closed loop on the simulator
def sim_engine(hours=0):
    cfg = config.load(None); cfg = copy.deepcopy(cfg); cfg["storage"]["path"] = ":memory:"
    clock = types.SimpleNamespace(t=T0 - 12 * 3600)                                 # start at midnight
    board = hal.SimGreenhouse(t0=clock.t); e = Engine(cfg, board, Store(), lambda: clock.t)
    for _ in range(int(hours * 3600 / 5)):
        board.advance(5); clock.t += 5; e.tick()
    return e, clock

def test_two_simulated_days_stay_in_band():
    e, clock = sim_engine(48)
    temps = [p for p in e.store.history("air_temp", clock.t - 40 * 3600, clock.t, 600)]
    assert min(p["min"] for p in temps) > 14.0 and max(p["max"] for p in temps) < 31.0
    soil = e.store.history("soil_moisture", clock.t - 40 * 3600, clock.t, 600)
    assert min(p["min"] for p in soil) > 24.0 and max(p["max"] for p in soil) < 60.0
    acts = e.store.actuations(0, 10000)
    assert {a["actuator"] for a in acts} >= {"heater", "vent", "irrigation", "lights"}
    assert 0 < e.store.total("water_flow", clock.t - 86400, clock.t) <= e.cfg["setpoints"]["irrigation_max_daily_l"]
    on = {k: False for k in ("heater", "vent")}; by_ts = {}
    for a in acts: by_ts.setdefault(a["ts"], []).append(a)
    for ts in sorted(by_ts):                                                          # heater and vent never overlap
        for a in by_ts[ts]:
            if a["actuator"] in on: on[a["actuator"]] = a["state"]
        assert not (on["heater"] and on["vent"])
    assert not [x for x in e.store.events(0, 1000) if x["level"] == "error"]

def test_sensor_failure_does_not_kill_loop():
    e, clock = sim_engine(0.1)
    e.board.read = lambda: (_ for _ in ()).throw(OSError("bus stuck"))
    for _ in range(40): clock.t += 5; e.tick()
    assert not e.ctl.state["heater"] and "sensor_air_temp" in e.ctl.alerts
    assert any(x["kind"] == "sensor" for x in e.store.events(0, 100))


# ------------------------------------------------------------------ Claude assistant (API mocked)
class Block(types.SimpleNamespace):
    def model_dump(self): return dict(self.__dict__)

class FakeClaude:
    def __init__(self, script): self.script, self.calls = list(script), []
    @property
    def messages(self): return self
    def create(self, **kw):
        self.calls.append(json.loads(json.dumps(kw, default=str))); content, stop = self.script.pop(0)
        return types.SimpleNamespace(content=content, stop_reason=stop)

def test_assistant_tool_loop_and_guardrails():
    e, clock = sim_engine(0.2)
    fake = FakeClaude([
        ([Block(type="tool_use", id="t1", name="get_status", input={}),
          Block(type="tool_use", id="t2", name="set_actuator", input={"actuator": "irrigation", "state": "on", "minutes": 200})], "tool_use"),
        ([Block(type="tool_use", id="t3", name="set_setpoints", input={"changes": {"heat_on_below_c": 95}})], "tool_use"),
        ([Block(type="text", text="Irrigation is on for 30 minutes. I could not set heating to 95 degrees.")], "end_turn")])
    a = Assistant(e, client=fake); reply = a.ask("water the plants and set heat to 95")
    assert "30 minutes" in reply and e.ctl.state["irrigation"]
    assert e.ctl.overrides["irrigation"].until <= clock.t + 30 * 60 + 1              # capped despite asking for 200
    assert e.cfg["setpoints"]["heat_on_below_c"] == 16.0                             # out-of-bounds change rejected
    r2 = fake.calls[1]["messages"][-1]["content"]; r3 = fake.calls[2]["messages"][-1]["content"]
    assert [x["tool_use_id"] for x in r2] == ["t1", "t2"] and json.loads(r2[0]["content"])["sensors"]["air_temp"]
    assert r3[0]["is_error"] and "outside" in r3[0]["content"]
    assert fake.calls[0]["tools"][0]["name"] == "get_status" and "Canopy" in fake.calls[0]["system"]
    assert any("claude" in x["message"] for x in e.store.events(0, 50))               # audit trail

def test_assistant_control_can_be_disabled_and_missing_key_is_clear(monkeypatch):
    e, _ = sim_engine(0); e.cfg["claude"]["allow_control"] = False
    a = Assistant(e); assert "disabled" in a.run_tool("set_actuator", {"actuator": "vent", "state": "on"})["error"]
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"): a.ask("hi")


# ------------------------------------------------------------------ web API
async def test_web_api(aiohttp_client):
    e, clock = sim_engine(1); e.cfg["web"]["token"] = "s3cret"
    fake = FakeClaude([([Block(type="text", text="All good.")], "end_turn")])
    c = await aiohttp_client(make_app(e, Assistant(e, client=fake))); H = {"Authorization": "Bearer s3cret"}
    st = await (await c.get("/api/status")).json(); assert set(st["actuators"]) == {"heater", "vent", "irrigation", "lights"}
    assert (await c.get("/")).status == 200 and (await c.get("/healthz")).status == 200
    assert len((await (await c.get("/api/history?sensor=air_temp&hours=1")).json())["points"]) >= 10
    assert (await c.post("/api/actuators/vent", json={"state": "on"})).status == 401
    r = await c.post("/api/actuators/vent", json={"state": "on", "minutes": 5}, headers=H); assert (await r.json())["on"] is True
    assert (await c.post("/api/actuators/bogus", json={"state": "on"}, headers=H)).status == 400
    assert (await c.put("/api/setpoints", json={"vent_on_above_c": 99}, headers=H)).status == 400
    assert (await (await c.put("/api/setpoints", json={"vent_on_above_c": 30}, headers=H)).json())["vent_on_above_c"] == 30
    assert (await (await c.post("/api/chat", json={"message": "status?"}, headers=H)).json())["reply"] == "All good."
    ev = await (await c.get("/api/events")).json(); assert any(a["source"] == "dashboard" for a in ev["actuations"])


# ------------------------------------------------------------------ drivers / radios / voice
def test_protocol_helpers():
    assert hal.crc8_sensirion(b"\xBE\xEF") == 0x92                                    # Sensirion datasheet vector
    assert hal.modbus_read_request(1, 0, 1) == bytes.fromhex("010300000001840a")
    body = bytes.fromhex("0103020123"); assert hal.modbus_parse(body + hal.modbus_crc(body), 1) == [0x0123]
    with pytest.raises(IOError): hal.modbus_parse(body + b"\x00\x00", 1)
    assert radios.zigbee_payload("zigbee2mqtt/bench2", b'{"temperature":21.5,"humidity":55,"linkquality":80}') == ("bench2", {"temperature": 21.5, "humidity": 55.0})
    assert radios.zigbee_payload("zigbee2mqtt/bridge/state", b"online") is None
    assert radios.lora_packet(b"CN1,tunnel_3,temperature=18.25,soil_moisture=33") == ("tunnel_3", {"temperature": 18.25, "soil_moisture": 33.0})
    assert radios.lora_packet(b"\xff\x00garbage") is None

def test_wireless_ingest_is_logged():
    e, clock = sim_engine(0); e.ingest("bench2", {"temperature": 21.5})
    assert e.status()["sensors"]["bench2.temperature"]["value"] == 21.5 and e.store.history("bench2.temperature", 0, clock.t + 1)

def test_voice_loop_with_fakes():
    loud = (b"\x00\x10" * 1280)[:2560]; quiet = b"\x00\x00" * 1280
    mic = types.SimpleNamespace(q=[quiet] + [loud] * 5 + [quiet] * 40); mic.chunk = lambda: mic.q.pop(0) if mic.q else quiet
    said = []; a = types.SimpleNamespace(ask=lambda t, source: f"echo {t} via {source}")
    v = voice.VoiceLoop(a, mic, types.SimpleNamespace(transcribe=lambda pcm: "how warm is it" if len(pcm) > 20000 else ""),
                        types.SimpleNamespace(say=said.append), button=lambda: True)
    assert v.once() == "echo how warm is it via voice" and said == ["echo how warm is it via voice"]
    v.button = lambda: False; assert v.once() is None
