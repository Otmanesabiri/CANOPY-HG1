# Canopy software

Python 3.11+, one process (`python -m canopy`), four moving parts:

```
 sensors ──> Engine.tick() every 5 s ──> Controller.step()  ──> relays
 (hal.py)        │   (engine.py)          (control.py: rules, interlocks, overrides, alerts)
                 ├──> Store (SQLite: raw 30 days, hourly roll-ups kept, events, actuator log)
                 ├──> Web dashboard + REST + live stream (webapp.py, aiohttp, token auth for writes)
                 ├──> Assistant (agent.py): Claude Messages API with tool use
                 ├──> Voice (voice.py): wake word / button -> Whisper -> Assistant -> Piper
                 └──> Radios (radios.py): Zigbee2MQTT over MQTT, LoRa node frames
```

## Control rules (all setpoints editable from the dashboard, by voice or by the assistant)

| Loop | Behaviour |
|---|---|
| Heating | on below `heat_on_below_c`, off above `heat_off_above_c` (hysteresis) |
| Ventilation | on above `vent_on_above_c`, or for high humidity / CO2 when it is not cold; off inside the band |
| Irrigation | when soil is below `soil_dry_below_pct`: one pulse of `irrigation_pulse_s`, then a soak of `irrigation_soak_s`, only inside `irrigation_window`, stopping at `irrigation_max_daily_l` (flow meter) |
| Lighting | inside the photoperiod, on below `lights_on_below_lux`, off above `lights_off_above_lux` |

Interlocks that nothing bypasses (manual overrides and the assistant included): heater and vent never run together;
heater off above the over-temperature alarm; irrigation stops at the daily water limit and after 30 minutes of
continuous valve-open time; all overrides expire (max 4 h, irrigation 30 min). Fail-safes: a missing or stale air
temperature disables heating and ventilation, a missing soil reading disables automatic irrigation, and both raise
alerts. Flow with the valve closed raises a leak alert. Setpoints are bounds-checked (`config.SETPOINT_BOUNDS`).

## Claude integration

`agent.py` calls the Anthropic Messages API (`anthropic` SDK) with five tools: `get_status`, `get_history`,
`get_events`, `set_actuator`, `set_setpoints`. Tools call the same `Engine` methods as the dashboard, so the
assistant is subject to every interlock and bound above, and each action is written to the event log with source
`claude` or `voice`. Set `claude.allow_control: false` for a read-only assistant. The model name is configuration
(`claude.model`); check https://docs.claude.com/en/docs/about-claude/models for current model IDs. The API key
lives in `/etc/canopy/canopy.env` (`ANTHROPIC_API_KEY`), readable only by root and the service user.
Automation never depends on the cloud: with no key or no internet the controller, dashboard and logging carry on
and the assistant endpoints return a clear error.

## REST API

| Method | Path | Auth | |
|---|---|---|---|
| GET | `/api/status` | - | readings, outputs + reasons, alerts, setpoints |
| GET | `/api/history?sensor=air_temp&hours=24` | - | bucketed avg/min/max |
| GET | `/api/events?hours=48` | - | alerts, changes, actuator log |
| GET | `/api/stream` | - | server-sent events, one status object per control cycle |
| POST | `/api/actuators/{heater,vent,irrigation,lights}` `{"state":"on|off|auto","minutes":30}` | token | time-limited override |
| PUT | `/api/setpoints` `{...}` | token | validated setpoint changes |
| POST | `/api/chat` `{"message":"..."}` | token | ask the assistant |

Send the token as `Authorization: Bearer <token>`. The dashboard is plain HTTP on the LAN; for remote access put it
behind a VPN (Tailscale/WireGuard) rather than exposing port 8080.

## Sensors supported out of the box

SCD41 (CO2, temperature, humidity) or SHT4x on a Qwiic port, BH1750 light sensor, capacitive soil probe on AIN0,
hall flow meter on FLOW1, DS18B20 soil temperature, plus Modbus RTU helpers for RS-485 probes, Zigbee devices through
Zigbee2MQTT (`zigbee2mqtt/<name>` -> `<name>.<field>` series) and LoRa nodes sending
`CN1,<node>,<key>=<value>,...` at SF7/125 kHz.

## Running and testing

```
cd software && pip install -e ".[dev]"
pytest                       # 19 tests: controller, store, 48 h closed-loop simulation, assistant, web API, protocols, voice
python -m canopy -c my.yaml  # hardware.mode: sim  -> full system against the built-in greenhouse simulator
```

Voice needs `pip install ".[voice]" piper-tts` and a Piper voice file; set `voice.enabled: true`.
