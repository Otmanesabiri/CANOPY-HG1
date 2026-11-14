"""Hardware abstraction: a physics-ish simulator (default, used for tests/dev) and the real Canopy GH-1 board.

Both expose:  read() -> {kind: value}   (air_temp C, humidity %, soil_moisture %, light lx, co2 ppm, water_flow L since last read)
              write(kind, bool)         (heater / vent / irrigation / lights)
              all_off()
"""
from __future__ import annotations
import glob, math, random, struct, threading, time

RELAY_CHANNEL = {"irrigation": 0, "vent": 2, "heater": 4, "lights": 5}   # MCP23017 GPA bit -> ULN2803 OUT(n+1)


class SimGreenhouse:
    def __init__(self, seed: int = 1, t0: float | None = None):
        self.rng = random.Random(seed); self.t = t0 or time.time(); self.out = {k: False for k in RELAY_CHANNEL}
        self.temp, self.rh, self.soil, self.co2 = 19.0, 65.0, 38.0, 600.0

    def _outside(self, t):
        h = (t % 86400) / 3600
        sun = max(0.0, math.sin((h - 6) / 12 * math.pi))
        return 8 + 9 * sun, sun

    def advance(self, dt: float):
        self.t += dt; out_t, sun = self._outside(self.t)
        k_loss = 1 / 1800 * (6 if self.out["vent"] else 1)
        gain = (0.012 if self.out["heater"] else 0) + 0.006 * sun + (0.001 if self.out["lights"] else 0)
        self.temp += dt * (k_loss * (out_t - self.temp) + gain)
        self.rh += dt * ((0.004 if not self.out["vent"] else -0.03) + (0.02 if self.out["irrigation"] else 0)); self.rh = min(99, max(25, self.rh))
        self.soil += dt * ((0.25 if self.out["irrigation"] else 0) - 0.00015 * (1 + 2 * sun)); self.soil = min(80, max(5, self.soil))
        self.co2 += dt * ((420 - self.co2) / (300 if self.out["vent"] else 7200) + 0.02 * (1 - sun) - 0.03 * sun); self.co2 = max(380, self.co2)
        self._flow = (0.2 * dt) if self.out["irrigation"] else 0.0      # 12 L/min valve

    def read(self) -> dict:
        _, sun = self._outside(self.t); n = self.rng.gauss
        v = {"air_temp": self.temp + n(0, .05), "humidity": self.rh + n(0, .3), "soil_moisture": self.soil + n(0, .2),
             "light": max(0, 45000 * sun + (9000 if self.out["lights"] else 0) + n(0, 50)), "co2": self.co2 + n(0, 5),
             "water_flow": getattr(self, "_flow", 0.0)}
        self._flow = 0.0
        return v

    def write(self, kind: str, on: bool): self.out[kind] = bool(on)
    def all_off(self):
        for k in self.out: self.out[k] = False


# ----------------------------------------------------------------------------- real hardware (Canopy GH-1 board)
def crc8_sensirion(b: bytes) -> int:
    c = 0xFF
    for x in b:
        c ^= x
        for _ in range(8): c = ((c << 1) ^ 0x31) & 0xFF if c & 0x80 else (c << 1) & 0xFF
    return c


def modbus_crc(b: bytes) -> bytes:
    c = 0xFFFF
    for x in b:
        c ^= x
        for _ in range(8): c = (c >> 1) ^ 0xA001 if c & 1 else c >> 1
    return struct.pack("<H", c)


def modbus_read_request(unit: int, reg: int, count: int = 1, fn: int = 3) -> bytes:
    p = struct.pack(">BBHH", unit, fn, reg, count); return p + modbus_crc(p)


def modbus_parse(resp: bytes, unit: int, fn: int = 3) -> list[int]:
    if len(resp) < 5 or resp[0] != unit or resp[1] != fn or modbus_crc(resp[:-2]) != resp[-2:]:
        raise IOError("bad Modbus response")
    return list(struct.unpack(">" + "H" * (resp[2] // 2), resp[3:3 + resp[2]]))


class Board:
    """Canopy GH-1: SCD41 (CO2/T/RH) and BH1750 (lux) on I2C-1, ADS1115 ch0 soil probe, flow meter on GPIO17,
    relays via MCP23017 port A -> ULN2803A.  Optional SHT4x fallback and DS18B20 soil temperature."""
    MCP, ADS, SCD, BH, SHT = 0x20, 0x48, 0x62, 0x23, 0x44

    def __init__(self, cfg: dict):
        from smbus2 import SMBus, i2c_msg                          # imported lazily: not needed in simulation
        self.i2c_msg, self.bus, self.lock = i2c_msg, SMBus(cfg["hardware"].get("i2c_bus", 1)), threading.Lock()
        hw = cfg["hardware"]
        self.soil_dry_v, self.soil_wet_v = hw.get("soil_dry_v", 2.6), hw.get("soil_wet_v", 1.2)
        self.pulses_per_l = hw.get("flow_pulses_per_l", 450.0)
        self.bus.write_byte_data(self.MCP, 0x14, 0x00)             # OLATA = all off before making pins outputs
        self.bus.write_byte_data(self.MCP, 0x00, 0x00)             # IODIRA = outputs (relays)
        self.bus.write_byte_data(self.MCP, 0x01, 0xF1)             # IODIRB: GPB0 button + GPB4-7 inputs, GPB1-3 LEDs
        self.bus.write_byte_data(self.MCP, 0x0D, 0x01)             # pull-up on the button
        self.olat = 0
        self.present = {n: self._probe(a) for n, a in (("scd", self.SCD), ("bh", self.BH), ("sht", self.SHT), ("ads", self.ADS))}
        if self.present["scd"]: self._cmd(self.SCD, 0x21B1)        # start periodic measurement (5 s)
        if self.present["bh"]: self.bus.write_byte(self.BH, 0x10)   # continuous high-resolution mode
        self.last = {}; self._pulses = 0; self._start_flow_counter(hw.get("flow_gpio", 17))

    def _probe(self, addr):
        try: self.bus.read_byte(addr); return True
        except OSError: return False

    def _cmd(self, addr, cmd): self.bus.i2c_rdwr(self.i2c_msg.write(addr, [cmd >> 8, cmd & 0xFF]))

    def _words(self, addr, n):
        rd = self.i2c_msg.read(addr, n * 3); self.bus.i2c_rdwr(rd); b = bytes(rd); out = []
        for i in range(n):
            if crc8_sensirion(b[i * 3:i * 3 + 2]) != b[i * 3 + 2]: raise IOError("Sensirion CRC error")
            out.append(b[i * 3] << 8 | b[i * 3 + 1])
        return out

    def _start_flow_counter(self, line):
        try:
            import gpiod
            from gpiod.line import Edge, Bias
            req = gpiod.request_lines("/dev/gpiochip0", consumer="canopy-flow",
                                      config={line: gpiod.LineSettings(edge_detection=Edge.FALLING, bias=Bias.DISABLED)})
            def run():
                while True:
                    for _ in req.read_edge_events(): self._pulses += 1
            threading.Thread(target=run, daemon=True).start()
        except Exception as e:                                       # flow metering is optional
            self.flow_error = str(e)

    def read(self) -> dict:
        v = {}
        with self.lock:
            try:
                if self.present["scd"]:
                    self._cmd(self.SCD, 0xE4B8); time.sleep(0.002)
                    if self._words(self.SCD, 1)[0] & 0x07FF:          # data ready
                        self._cmd(self.SCD, 0xEC05); time.sleep(0.002); c, t, h = self._words(self.SCD, 3)
                        self.last.update(co2=float(c), air_temp=-45 + 175 * t / 65535, humidity=100 * h / 65535)
                    v.update({k: self.last[k] for k in ("co2", "air_temp", "humidity") if k in self.last})
                elif self.present["sht"]:
                    self.bus.write_byte(self.SHT, 0xFD); time.sleep(0.01); t, h = self._words(self.SHT, 2)
                    v.update(air_temp=-45 + 175 * t / 65535, humidity=min(100, max(0, -6 + 125 * h / 65535)))
            except OSError: pass
            try:
                if self.present["bh"]:
                    rd = self.i2c_msg.read(self.BH, 2); self.bus.i2c_rdwr(rd); b = bytes(rd); v["light"] = (b[0] << 8 | b[1]) / 1.2
            except OSError: pass
            try:
                if self.present["ads"]:
                    volts = self.adc(0); span = self.soil_dry_v - self.soil_wet_v
                    v["soil_moisture"] = min(100.0, max(0.0, (self.soil_dry_v - volts) / span * 100))
            except OSError: pass
        p, self._pulses = self._pulses, 0
        v["water_flow"] = p / self.pulses_per_l
        for path in glob.glob("/sys/bus/w1/devices/28-*/temperature")[:1]:
            try: v["soil_temp"] = int(open(path).read()) / 1000
            except (OSError, ValueError): pass
        return v

    def adc(self, ch: int) -> float:
        cfg = 0x8000 | (0x4 + ch) << 12 | 0x1 << 9 | 0x1 << 8 | 0x4 << 5 | 0x3     # single-shot, +/-4.096 V, 128 SPS
        self.bus.write_i2c_block_data(self.ADS, 0x01, [cfg >> 8, cfg & 0xFF]); time.sleep(0.01)
        hi, lo = self.bus.read_i2c_block_data(self.ADS, 0x00, 2)
        return struct.unpack(">h", bytes([hi, lo]))[0] * 4.096 / 32768

    def write(self, kind: str, on: bool):
        bit = 1 << RELAY_CHANNEL[kind]
        with self.lock:
            self.olat = self.olat | bit if on else self.olat & ~bit
            self.bus.write_byte_data(self.MCP, 0x14, self.olat)

    def all_off(self):
        with self.lock:
            self.olat = 0; self.bus.write_byte_data(self.MCP, 0x14, 0)

    def led(self, r=False, g=False, b=False):
        with self.lock: self.bus.write_byte_data(self.MCP, 0x15, (r << 1) | (g << 2) | (b << 3))

    def button(self) -> bool:
        with self.lock: return not self.bus.read_byte_data(self.MCP, 0x13) & 1


def make(cfg: dict):
    return SimGreenhouse() if cfg["hardware"]["mode"] == "sim" else Board(cfg)
