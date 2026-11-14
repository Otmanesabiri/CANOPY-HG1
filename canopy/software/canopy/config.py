"""Configuration loading and validation (YAML)."""
from __future__ import annotations
import copy, os, yaml

DEFAULTS = {
    "site": {"name": "Greenhouse", "timezone": "UTC"},
    "hardware": {"mode": "sim", "i2c_bus": 1, "poll_s": 5},
    "storage": {"path": "/var/lib/canopy/canopy.db", "raw_days": 30},
    "web": {"host": "0.0.0.0", "port": 8080, "token": ""},
    "claude": {"model": "claude-sonnet-5-5", "max_tokens": 1024, "api_key_env": "ANTHROPIC_API_KEY",
               "allow_control": True},
    "voice": {"enabled": False, "wake_word": "hey_jarvis", "stt_model": "base.en",
              "piper_voice": "/usr/share/piper/en_US-lessac-medium.onnx", "alsa_device": "default"},
    "mqtt": {"enabled": False, "host": "127.0.0.1", "port": 1883, "topic": "zigbee2mqtt/#"},
    "lora": {"enabled": False, "freq_mhz": 915.0},
    "setpoints": {
        "heat_on_below_c": 16.0, "heat_off_above_c": 18.0,
        "vent_on_above_c": 28.0, "vent_off_below_c": 25.0,
        "humidity_vent_above_pct": 85.0, "humidity_vent_below_pct": 78.0,
        "co2_vent_above_ppm": 1800.0,
        "soil_dry_below_pct": 30.0, "soil_wet_above_pct": 45.0,
        "irrigation_pulse_s": 60, "irrigation_soak_s": 900, "irrigation_max_daily_l": 200.0,
        "irrigation_window": ["06:00", "20:00"],
        "lights_on": "06:00", "lights_off": "22:00", "lights_off_above_lux": 20000.0, "lights_on_below_lux": 12000.0,
    },
    "alerts": {"temp_low_c": 5.0, "temp_high_c": 38.0, "sensor_stale_s": 120, "leak_l_per_min": 0.5},
    "sensors": [], "actuators": [],
}
# hard safety bounds for anything a user or the assistant may change at run time
SETPOINT_BOUNDS = {
    "heat_on_below_c": (0, 30), "heat_off_above_c": (1, 32), "vent_on_above_c": (15, 45), "vent_off_below_c": (10, 44),
    "humidity_vent_above_pct": (40, 100), "humidity_vent_below_pct": (30, 99), "co2_vent_above_ppm": (600, 5000),
    "soil_dry_below_pct": (5, 80), "soil_wet_above_pct": (10, 95), "irrigation_pulse_s": (5, 900),
    "irrigation_soak_s": (60, 14400), "irrigation_max_daily_l": (0, 5000),
    "lights_off_above_lux": (0, 200000), "lights_on_below_lux": (0, 200000),
}
REQUIRED_KINDS = ("air_temp", "humidity", "soil_moisture", "light", "co2", "water_flow")


def _merge(base, over):
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _merge(base[k], v)
        else:
            base[k] = v
    return base


def validate_setpoints(sp: dict) -> list[str]:
    errs = []
    for k, (lo, hi) in SETPOINT_BOUNDS.items():
        if k in sp and not (isinstance(sp[k], (int, float)) and lo <= sp[k] <= hi):
            errs.append(f"{k}={sp[k]!r} outside [{lo}, {hi}]")
    if sp.get("heat_on_below_c", 0) >= sp.get("heat_off_above_c", 1):
        errs.append("heat_on_below_c must be < heat_off_above_c")
    if sp.get("vent_off_below_c", 0) >= sp.get("vent_on_above_c", 1):
        errs.append("vent_off_below_c must be < vent_on_above_c")
    if sp.get("heat_off_above_c", 0) >= sp.get("vent_off_below_c", 1):
        errs.append("heating band must sit below the ventilation band (heat_off_above_c < vent_off_below_c)")
    if sp.get("soil_dry_below_pct", 0) >= sp.get("soil_wet_above_pct", 1):
        errs.append("soil_dry_below_pct must be < soil_wet_above_pct")
    w = sp.get("irrigation_window")
    times = [("lights_on", sp.get("lights_on")), ("lights_off", sp.get("lights_off"))]
    if not (isinstance(w, (list, tuple)) and len(w) == 2):
        errs.append("irrigation_window must be [HH:MM, HH:MM]")
    else:
        times += [("irrigation_window", w[0]), ("irrigation_window", w[1])]
    for k, v in times:
        try:
            h, m = str(v).split(":"); assert 0 <= int(h) < 24 and 0 <= int(m) < 60
        except Exception:
            errs.append(f"{k} must be HH:MM")
    return errs


def load(path: str | None = None) -> dict:
    cfg = copy.deepcopy(DEFAULTS)
    if path and os.path.exists(path):
        with open(path) as f:
            _merge(cfg, yaml.safe_load(f) or {})
    errs = validate_setpoints(cfg["setpoints"])
    ids = [s["id"] for s in cfg["sensors"]] + [a["id"] for a in cfg["actuators"]]
    if len(ids) != len(set(ids)):
        errs.append("duplicate sensor/actuator ids")
    if errs:
        raise ValueError("invalid configuration: " + "; ".join(errs))
    return cfg
