"""Wireless sensor bridges: Zigbee (via Zigbee2MQTT -> MQTT) and LoRa (on-board RFM95W / SX1276)."""
from __future__ import annotations
import json, logging, threading, time

log = logging.getLogger("canopy.radio")
ZB_MAP = {"temperature": "temperature", "humidity": "humidity", "soil_moisture": "soil_moisture", "illuminance_lux": "light",
          "illuminance": "light", "co2": "co2", "battery": "battery", "water_leak": "leak"}


def zigbee_payload(topic: str, payload: bytes):
    """zigbee2mqtt/<friendly_name> {json} -> (source, values) or None."""
    parts = topic.split("/")
    if len(parts) != 2 or parts[1] == "bridge": return None
    try: d = json.loads(payload)
    except ValueError: return None
    vals = {ZB_MAP[k]: (float(v) if not isinstance(v, bool) else float(v)) for k, v in d.items() if k in ZB_MAP and isinstance(v, (int, float, bool))}
    return (parts[1], vals) if vals else None


def start_zigbee(engine):
    import paho.mqtt.client as mqtt
    c = engine.cfg["mqtt"]
    cli = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    cli.on_connect = lambda cl, u, f, rc, p=None: cl.subscribe(c["topic"])
    def on_msg(cl, u, m):
        r = zigbee_payload(m.topic, m.payload)
        if r: engine.ingest(*r)
    cli.on_message = on_msg
    cli.connect_async(c["host"], c["port"]); cli.loop_start(); return cli


def lora_packet(raw: bytes):
    """Canopy node frame: ASCII 'CN1,<node_id>,<key>=<value>,...'  e.g.  CN1,bench2,temperature=21.4,soil_moisture=37"""
    try:
        f = raw.decode("ascii").strip().split(",")
        if f[0] != "CN1" or not f[1].replace("_", "").isalnum(): return None
        return f[1], {k: float(v) for k, v in (x.split("=", 1) for x in f[2:])}
    except (ValueError, IndexError, UnicodeDecodeError):
        return None


class SX1276:
    """Minimal receive-only LoRa driver (SF7 / 125 kHz / CR 4-5, explicit header, CRC on)."""
    def __init__(self, freq_mhz=915.0, bus=0, cs=0, reset_gpio=22):
        import spidev, gpiod
        from gpiod.line import Direction, Value
        self.spi = spidev.SpiDev(); self.spi.open(bus, cs); self.spi.max_speed_hz = 2_000_000
        rst = gpiod.request_lines("/dev/gpiochip0", consumer="canopy-lora", config={reset_gpio: gpiod.LineSettings(direction=Direction.OUTPUT, output_value=Value.ACTIVE)})
        rst.set_value(reset_gpio, Value.INACTIVE); time.sleep(0.01); rst.set_value(reset_gpio, Value.ACTIVE); time.sleep(0.01)
        if self.rd(0x42) != 0x12: raise IOError("SX1276 not found")
        self.wr(0x01, 0x80); time.sleep(0.01)                       # sleep + LoRa mode
        frf = int(freq_mhz * 1e6 / (32e6 / 2 ** 19))
        for reg, val in ((0x06, frf >> 16), (0x07, frf >> 8 & 0xFF), (0x08, frf & 0xFF), (0x0F, 0), (0x1D, 0x72), (0x1E, 0x74), (0x26, 0x04), (0x39, 0x12)):
            self.wr(reg, val)
        self.wr(0x01, 0x85)                                           # continuous receive

    def rd(self, reg): return self.spi.xfer2([reg & 0x7F, 0])[1]
    def wr(self, reg, val): self.spi.xfer2([reg | 0x80, val & 0xFF])

    def poll(self):
        irq = self.rd(0x12)
        if not irq & 0x40: return None
        self.wr(0x12, 0xFF)
        if irq & 0x20: return None                                    # CRC error
        n = self.rd(0x13); self.wr(0x0D, self.rd(0x10))
        return bytes(self.spi.xfer2([0x00] + [0] * n)[1:]), self.rd(0x1A) - 157


def start_lora(engine):
    radio = SX1276(engine.cfg["lora"]["freq_mhz"])
    def run():
        while True:
            try:
                p = radio.poll()
                if p:
                    r = lora_packet(p[0])
                    if r: engine.ingest(r[0], {**r[1], "rssi": p[1]})
            except Exception: log.exception("LoRa poll failed"); time.sleep(5)
            time.sleep(0.05)
    threading.Thread(target=run, daemon=True).start(); return radio
