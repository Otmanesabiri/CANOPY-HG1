"""Rule-based climate / irrigation / lighting controller with interlocks, manual overrides and fail-safes.

The controller is deterministic and has no I/O: step(now, readings) -> {actuator_kind: bool}.  Everything that can
switch an output - automation, the dashboard, the Claude assistant, voice - goes through this class, so the same
interlocks always apply.
"""
from __future__ import annotations
import datetime as dt
from dataclasses import dataclass, field

KINDS = ("heater", "vent", "irrigation", "lights")


def _hm(s: str) -> dt.time:
    h, m = s.split(":"); return dt.time(int(h), int(m))


def in_window(t: dt.time, start: str, end: str) -> bool:
    a, b = _hm(start), _hm(end)
    return a <= t < b if a <= b else (t >= a or t < b)


@dataclass
class Override:
    state: bool
    until: float
    source: str


@dataclass
class Controller:
    setpoints: dict
    alerts_cfg: dict
    tz: dt.tzinfo = dt.timezone.utc
    state: dict = field(default_factory=lambda: {k: False for k in KINDS})
    reasons: dict = field(default_factory=lambda: {k: "startup" for k in KINDS})
    overrides: dict = field(default_factory=dict)
    alerts: dict = field(default_factory=dict)          # key -> message (currently active)
    irr_started: float | None = None
    irr_last_end: float = 0.0
    litres_today: float = 0.0
    _day: dt.date | None = None

    # ---- manual control (dashboard, assistant, voice)
    def set_override(self, kind: str, state: bool | None, now: float, minutes: float = 30, source: str = "manual"):
        if kind not in KINDS:
            raise ValueError(f"unknown actuator {kind!r}")
        if state is None:
            self.overrides.pop(kind, None); return
        minutes = max(1.0, min(float(minutes), 240.0 if kind != "irrigation" else 30.0))   # overrides always expire
        self.overrides[kind] = Override(bool(state), now + minutes * 60, source)

    # ---- one control cycle
    def step(self, now: float, r: dict, ages: dict | None = None, flow_l: float = 0.0) -> dict:
        """r: latest readings by kind; ages: seconds since each reading; flow_l: litres measured since last step."""
        sp, ages = self.setpoints, ages or {}
        local = dt.datetime.fromtimestamp(now, self.tz)
        if self._day != local.date():
            self._day, self.litres_today = local.date(), 0.0
        self.litres_today += max(flow_l, 0.0)
        stale = self.alerts_cfg["sensor_stale_s"]
        ok = lambda k: r.get(k) is not None and ages.get(k, 0) <= stale
        want, why, alerts = dict(self.state), dict(self.reasons), {}

        # climate -------------------------------------------------------------
        if ok("air_temp"):
            t = r["air_temp"]
            if t < sp["heat_on_below_c"]: want["heater"], why["heater"] = True, f"{t:.1f}C < {sp['heat_on_below_c']}C"
            elif t > sp["heat_off_above_c"]: want["heater"], why["heater"] = False, f"{t:.1f}C > {sp['heat_off_above_c']}C"
            hot = t > sp["vent_on_above_c"]; cool = t < sp["vent_off_below_c"]
            humid = ok("humidity") and r["humidity"] > sp["humidity_vent_above_pct"]
            dry = not ok("humidity") or r["humidity"] < sp["humidity_vent_below_pct"]
            co2hi = ok("co2") and r["co2"] > sp["co2_vent_above_ppm"]
            co2ok = not ok("co2") or r["co2"] < sp["co2_vent_above_ppm"] * 0.85
            if hot: want["vent"], why["vent"] = True, f"{t:.1f}C > {sp['vent_on_above_c']}C"
            elif humid and t > sp["heat_on_below_c"] + 1: want["vent"], why["vent"] = True, f"humidity {r['humidity']:.0f}%"
            elif co2hi and t > sp["heat_on_below_c"] + 1: want["vent"], why["vent"] = True, f"CO2 {r['co2']:.0f}ppm"
            elif cool and dry and co2ok: want["vent"], why["vent"] = False, "within band"
            elif t <= sp["heat_on_below_c"]: want["vent"], why["vent"] = False, "too cold to ventilate"
            if t < self.alerts_cfg["temp_low_c"]: alerts["temp_low"] = f"Air temperature {t:.1f}C is below {self.alerts_cfg['temp_low_c']}C"
            if t > self.alerts_cfg["temp_high_c"]: alerts["temp_high"] = f"Air temperature {t:.1f}C is above {self.alerts_cfg['temp_high_c']}C"
        else:   # fail-safe: no trusted temperature -> no heat, no forced ventilation
            want["heater"], why["heater"] = False, "fail-safe: air temperature unavailable"
            want["vent"], why["vent"] = False, "fail-safe: air temperature unavailable"
            alerts["sensor_air_temp"] = "Air temperature sensor missing or stale - heating and ventilation disabled"

        # lighting ------------------------------------------------------------
        if in_window(local.time(), sp["lights_on"], sp["lights_off"]):
            if not ok("light"): want["lights"], why["lights"] = True, "photoperiod (no light sensor)"
            elif r["light"] < sp["lights_on_below_lux"]: want["lights"], why["lights"] = True, f"{r['light']:.0f} lx < {sp['lights_on_below_lux']:.0f}"
            elif r["light"] > sp["lights_off_above_lux"]: want["lights"], why["lights"] = False, f"{r['light']:.0f} lx > {sp['lights_off_above_lux']:.0f}"
        else:
            want["lights"], why["lights"] = False, "outside photoperiod"

        # irrigation: pulse, then soak, with a daily volume cap ------------------
        irr = self.state["irrigation"]
        if irr and self.irr_started is not None and now - self.irr_started >= sp["irrigation_pulse_s"]:
            want["irrigation"], why["irrigation"] = False, "pulse complete, soaking"
        elif not irr:
            want["irrigation"] = False
            soaked = now - self.irr_last_end >= sp["irrigation_soak_s"]
            if not ok("soil_moisture"):
                why["irrigation"] = "fail-safe: soil moisture unavailable"
                alerts["sensor_soil"] = "Soil moisture sensor missing or stale - automatic irrigation disabled"
            elif self.litres_today >= sp["irrigation_max_daily_l"]:
                why["irrigation"] = "daily water limit reached"
                if r["soil_moisture"] < sp["soil_dry_below_pct"]:
                    alerts["water_limit"] = f"Soil is dry but the daily limit of {sp['irrigation_max_daily_l']:.0f} L is used up"
            elif r["soil_moisture"] < sp["soil_dry_below_pct"] and soaked and in_window(local.time(), *sp["irrigation_window"]):
                want["irrigation"], why["irrigation"] = True, f"soil {r['soil_moisture']:.0f}% < {sp['soil_dry_below_pct']}%"
            elif r["soil_moisture"] >= sp["soil_wet_above_pct"]:
                why["irrigation"] = "soil moist"
        if irr and ok("soil_moisture") and r["soil_moisture"] >= sp["soil_wet_above_pct"]:
            want["irrigation"], why["irrigation"] = False, "soil moist"

        # manual overrides (always time-limited) --------------------------------
        for k, o in list(self.overrides.items()):
            if now >= o.until: del self.overrides[k]
            else: want[k], why[k] = o.state, f"{o.source} override"

        # interlocks: applied last, nothing bypasses them ------------------------
        if want["heater"] and want["vent"]:
            ov_h, ov_v = "heater" in self.overrides, "vent" in self.overrides
            loser = "heater" if (ov_v and not ov_h) or not (ov_h or ov_v) and ok("air_temp") and r["air_temp"] > sp["heat_off_above_c"] else "vent"
            if ov_h and ov_v: loser = "heater"
            want[loser], why[loser] = False, "interlock: heater and vent never run together"
        if ok("air_temp") and r["air_temp"] > self.alerts_cfg["temp_high_c"] and want["heater"]:
            want["heater"], why["heater"] = False, "interlock: over-temperature"
        if want["irrigation"] and self.litres_today >= sp["irrigation_max_daily_l"]:
            want["irrigation"], why["irrigation"] = False, "interlock: daily water limit"
        if want["irrigation"] and self.irr_started is not None and now - self.irr_started > max(sp["irrigation_pulse_s"], 1800):
            want["irrigation"], why["irrigation"] = False, "interlock: maximum valve-open time"; self.overrides.pop("irrigation", None)

        # leak detection: flow while the valve is commanded closed ---------------
        if not self.state["irrigation"] and not want["irrigation"] and now - self.irr_last_end > 30 and flow_l > 0:
            self._leak = getattr(self, "_leak", 0) + 1
            if self._leak >= 3: alerts["leak"] = "Water is flowing while the irrigation valve is closed - possible leak"
        else:
            self._leak = 0

        # bookkeeping -----------------------------------------------------------
        if want["irrigation"] and not self.state["irrigation"]: self.irr_started = now
        if not want["irrigation"] and self.state["irrigation"]: self.irr_last_end, self.irr_started = now, None
        changed = {k: want[k] for k in KINDS if want[k] != self.state[k]}
        self.state, self.reasons = want, why
        self.new_alerts = {k: v for k, v in alerts.items() if k not in self.alerts}
        self.cleared_alerts = [k for k in self.alerts if k not in alerts]
        self.alerts = alerts
        return changed
