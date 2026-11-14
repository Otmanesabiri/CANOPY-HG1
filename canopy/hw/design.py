"""Canopy GH-1 greenhouse controller - hardware design database.

Single source of truth: every component, its library symbol/footprint, MPN and
pin->net assignment.  build_sch.py turns this into KiCad schematics, build_pcb.py
into the board.  Pins are addressed by NAME (as in the KiCad symbol) or by NUMBER
(string of digits / connector designator) - number wins when both could match.
"""
import json, os
HERE = os.path.dirname(os.path.abspath(__file__))
PARTS = []          # list of dicts
_cnt = {}

def P(prefix, sheet, sym, value, fp, nets, mpn='', mfr='', desc='', dnp=False):
    _cnt[prefix] = _cnt.get(prefix, 0) + 1
    ref = f'{prefix}{_cnt[prefix]}'
    PARTS.append(dict(ref=ref, sheet=sheet, sym=sym, value=value, fp=fp, nets=nets,
                      mpn=mpn, mfr=mfr, desc=desc, dnp=dnp))
    return ref

E96 = {'0R': 'RC0603JR-070RL'}
def R(sheet, val, a, b, desc=''):
    if '.' in val:
        i_, f_ = val[:-1].split('.'); code = i_ + val[-1].upper() + f_
    else:
        code = val.upper()
    mpn = f'RC0603FR-07{code}L'
    return P('R', sheet, 'Device:R', val, 'Resistor_SMD:R_0603_1608Metric', {'1': a, '2': b}, mpn, 'Yageo', desc or 'Resistor 1% 0603')

CAPS = {  # value: (footprint, mpn, mfr, description)
    '100n': ('Capacitor_SMD:C_0603_1608Metric', 'GRM188R71H104KA93D', 'Murata', '100nF 50V X7R 0603'),
    '1u':   ('Capacitor_SMD:C_0603_1608Metric', 'CL10A105KB8NNNC', 'Samsung', '1uF 50V X5R 0603'),
    '10u':  ('Capacitor_SMD:C_0603_1608Metric', 'GRM188R61A106KE69D', 'Murata', '10uF 10V X5R 0603'),
    '22u':  ('Capacitor_SMD:C_0805_2012Metric', 'GRM21BR61A226ME44L', 'Murata', '22uF 10V X5R 0805'),
    '10u/35V': ('Capacitor_SMD:C_1206_3216Metric', 'GRM31CR6YA106KA12L', 'Murata', '10uF 35V X5R 1206'),
    '18p':  ('Capacitor_SMD:C_0603_1608Metric', 'GRM1885C1H180JA01D', 'Murata', '18pF 50V C0G 0603'),
    '1n':   ('Capacitor_SMD:C_0603_1608Metric', 'GRM188R71H102KA01D', 'Murata', '1nF 50V X7R 0603'),
    '1n/2kV': ('Capacitor_SMD:C_1206_3216Metric', 'C1206C102KGRACTU', 'KEMET', '1nF 2kV X7R 1206'),
}
def C(sheet, val, a, b='GND'):
    fp, mpn, mfr, d = CAPS[val]
    return P('C', sheet, 'Device:C', val, fp, {'1': a, '2': b}, mpn, mfr, d)

def LED(sheet, color, a, k):
    mpn = {'green': 'LTST-C191KGKT', 'red': 'LTST-C191KRKT', 'blue': 'LTST-C191TBKT', 'yellow': 'LTST-C191KSKT'}[color]
    return P('D', sheet, 'Device:LED', color, 'LED_SMD:LED_0603_1608Metric', {'A': a, 'K': k}, mpn, 'Lite-On', f'LED {color} 0603')

def TB(sheet, n, nets, label):
    pn = {2: '1984617', 3: '1984620', 4: '1984633', 6: '1984659', 8: '1984675'}[n]
    return P('J', sheet, f'Connector:Screw_Terminal_01x{n:02d}', label,
             f'TerminalBlock_Phoenix:TerminalBlock_Phoenix_PT-1,5-{n}-3.5-H_1x{n:02d}_P3.50mm_Horizontal',
             {str(i + 1): v for i, v in enumerate(nets)}, f'PT 1,5/{n}-3,5-H ({pn})', 'Phoenix Contact',
             f'Screw terminal {n}-pos 3.5mm')

# ---------------------------------------------------------------- POWER (USB-C PD -> 5V -> 3V3)
S = 'power'
P('J', S, 'Connector:USB_C_Receptacle_USB2.0_16P', 'USB-C PD IN',
  'Connector_USB:USB_C_Receptacle_GCT_USB4105-xx-A_16P_TopMnt_Horizontal',
  {'A4': 'VBUS', 'A9': 'VBUS', 'B4': 'VBUS', 'B9': 'VBUS', 'A1': 'GND', 'A12': 'GND', 'B1': 'GND', 'B12': 'GND',
   'A5': 'CC1', 'B5': 'CC2', 'A6': 'USBC_DP', 'B6': 'USBC_DP', 'A7': 'USBC_DM', 'B7': 'USBC_DM', 'S1': 'GND'},
  'USB4105-GF-A', 'GCT', 'USB Type-C receptacle, USB2.0, 16-pin')                                   # J1
P('D', S, 'Device:D_TVS', 'SMAJ22A', 'Diode_SMD:D_SMA', {'1': 'VBUS', '2': 'GND'}, 'SMAJ22A', 'Littelfuse', 'TVS 22V 400W')
C(S, '10u/35V', 'VBUS')
P('U', S, 'Interface_USB:STUSB4500QTR', 'STUSB4500', 'Package_DFN_QFN:QFN-24-1EP_4x4mm_P0.5mm_EP2.7x2.7mm',
  {'CC1DB': 'CC1', 'CC1': 'CC1', 'CC2': 'CC2', 'CC2DB': 'CC2', 'RESET': 'GND', 'SCL': 'I2C_SCL', 'SDA': 'I2C_SDA',
   'DISCH': 'PD_DISCH', 'GND': 'GND', 'ADDR0': 'GND', 'ADDR1': 'GND', 'VBUS_EN_SNK': 'PD_EN',
   'VBUS_VS_DISCH': 'PD_VS', 'VREG_1V2': 'PD_1V2', 'VSYS': 'GND', 'VREG_2V7': 'PD_2V7', 'VDD': 'VBUS'},
  'STUSB4500QTR', 'STMicroelectronics', 'Standalone USB PD sink controller')                           # U1
R(S, '1k', 'PD_VS', 'VBUS'); R(S, '1k', 'PD_DISCH', 'VIN')
C(S, '1u', 'PD_1V2'); C(S, '1u', 'PD_2V7'); C(S, '1u', 'VBUS')
P('Q', S, 'Transistor_FET:SiS443DN', 'SiS443DN', 'Package_SO:Vishay_PowerPAK_1212-8_Single',
  {'S': 'VBUS', 'G': 'PD_GATE', 'D': 'VIN'}, 'SIS443DN-T1-GE3', 'Vishay', 'P-MOSFET -40V PowerPAK 1212-8 (PD load switch)')
R(S, '100k', 'PD_GATE', 'VBUS'); R(S, '22k', 'PD_GATE', 'PD_EN'); C(S, '100n', 'PD_GATE', 'VBUS')
P('D', S, 'Device:D_Zener', 'BZT52C10', 'Diode_SMD:D_SOD-123', {'K': 'VBUS', 'A': 'PD_GATE'}, 'BZT52C10-7-F', 'Diodes Inc.', 'Zener 10V gate clamp')
# 5V / 4A buck from 5..20V
P('U', S, 'Regulator_Switching:LMR33640ADDA', 'LMR33640A', 'Package_SO:Texas_HSOP-8-1EP_3.9x4.9mm_P1.27mm_ThermalVias',
  {'GND': 'GND', 'VIN': 'VIN', 'EN': 'EN_5V', 'FB': 'FB_5V', 'VCC': 'VCC_5V', 'BOOT': 'BOOT_5V', 'SW': 'SW_5V'},
  'LMR33640ADDAR', 'Texas Instruments', '36V 4A synchronous buck, 400kHz')                          # U2
R(S, '100k', 'EN_5V', 'VIN'); R(S, '100k', '+5V', 'FB_5V'); R(S, '24.9k', 'FB_5V', 'GND')
C(S, '10u/35V', 'VIN'); C(S, '10u/35V', 'VIN'); C(S, '100n', 'VIN'); C(S, '1u', 'VCC_5V'); C(S, '100n', 'BOOT_5V', 'SW_5V')
P('L', S, 'Device:L', '6.8uH', 'Inductor_SMD:L_Bourns_SRP7028A_7.3x6.6mm', {'1': 'SW_5V', '2': '+5V'},
  'SRP7028A-6R8M', 'Bourns', 'Shielded power inductor 6.8uH')
C(S, '22u', '+5V'); C(S, '22u', '+5V'); C(S, '22u', '+5V'); C(S, '100n', '+5V')
# 3V3 / 2.5A peripheral buck, enabled by the CM4's own 3V3 (sequencing)
P('U', S, 'Regulator_Switching:AP62250WU', 'AP62250', 'Package_TO_SOT_SMD:TSOT-23-6',
  {'GND': 'GND', 'SW': 'SW_3V3', 'VIN': '+5V', 'FB': 'FB_3V3', 'EN': 'EN_3V3', 'BST': 'BST_3V3'},
  'AP62250WU-7', 'Diodes Inc.', '18V 2.5A synchronous buck')                                        # U3
R(S, '10k', 'CM4_3V3', 'EN_3V3'); R(S, '100k', 'EN_3V3', 'GND')
R(S, '100k', '+3V3', 'FB_3V3'); R(S, '31.6k', 'FB_3V3', 'GND')
C(S, '10u', '+5V'); C(S, '100n', 'BST_3V3', 'SW_3V3')
P('L', S, 'Device:L', '2.2uH', 'Inductor_SMD:L_Coilcraft_XAL4020-XXX', {'1': 'SW_3V3', '2': '+3V3'},
  'XAL4020-222MEC', 'Coilcraft', 'Shielded power inductor 2.2uH')
C(S, '22u', '+3V3'); C(S, '22u', '+3V3'); C(S, '100n', '+3V3')
r = R(S, '1k', '+3V3', 'LED_PWR_A'); LED(S, 'green', 'LED_PWR_A', 'GND')

# ---------------------------------------------------------------- CM4
S = 'cm4'
cm4 = {int(k): v for k, v in json.load(open(os.path.join(HERE, 'cm4_pins.json'))).items()}
GP = {2: 'I2C_SDA', 3: 'I2C_SCL', 4: 'RS485_TX', 5: 'RS485_RX', 6: 'RS485_DE', 7: 'AMP_SD', 8: 'LORA_NSS',
      9: 'SPI_MISO', 10: 'SPI_MOSI', 11: 'SPI_SCK', 12: 'GPIO12_PWM0', 13: 'GPIO13_PWM1', 14: 'UART_TX',
      15: 'UART_RX', 16: 'GPIO16', 17: 'FLOW1', 18: 'I2S_BCLK', 19: 'I2S_LRCLK', 20: 'I2S_DIN', 21: 'I2S_DOUT',
      22: 'LORA_RST', 23: 'IOX_INT', 24: 'LORA_DIO1', 25: 'LORA_DIO0', 26: 'FLOW2', 27: 'ONEWIRE'}
cm_nets = {}
for n, name in cm4.items():
    if name == 'GND': cm_nets[str(n)] = 'GND'
    elif name == '+5V': cm_nets[str(n)] = '+5V'
    elif name.startswith('CM4_3.3V'): cm_nets[str(n)] = 'CM4_3V3'
    elif name == 'GPIO_VREF': cm_nets[str(n)] = 'CM4_3V3'
    elif name.startswith('GPIO') and name[4:].isdigit() and int(name[4:]) in GP: cm_nets[str(n)] = GP[int(name[4:])]
    elif name.startswith('Ethernet_Pair'): cm_nets[str(n)] = 'ETH' + name[13] + '_' + name[-1]
    elif name.startswith('SD_DAT') and name[-1] in '0123': cm_nets[str(n)] = name
cm_nets.update({'57': 'SD_CLK', '62': 'SD_CMD', '75': 'SD_PWR_ON', '17': 'ETH_LED_LINK', '15': 'ETH_LED_ACT',
                '21': 'LED_ACT_K', '92': 'RUN_PG', '93': 'nRPIBOOT', '100': 'nEXTRST',
                '103': 'CM_USB_N', '105': 'CM_USB_P'})
P('U', S, 'canopy:CM4', 'Raspberry Pi CM4', 'canopy:Raspberry-Pi-4-Compute-Module', cm_nets,
  'CM4102000 (2GB, Wi-Fi/BT, Lite) or CM4102032 (32GB eMMC)', 'Raspberry Pi',
  'Compute Module 4 (BCM2711) on 2x Hirose DF40C-100DS-0.4V(51)')                                   # U4
C(S, '22u', '+5V'); C(S, '22u', '+5V'); C(S, '100n', '+5V'); C(S, '100n', 'CM4_3V3')
P('JP', S, 'Jumper:Jumper_2_Open', 'USB BOOT', 'Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical',
  {'A': 'nRPIBOOT', 'B': 'GND'}, 'M20-9990245', 'Harwin', 'Fit jumper to flash eMMC over USB-C (rpiboot)')
P('SW', S, 'Switch:SW_Push', 'RESET', 'Button_Switch_SMD:SW_SPST_B3U-1000P', {'1': 'RUN_PG', '2': 'GND'}, 'B3U-1000P', 'Omron', 'Tact switch')
R(S, '1k', '+3V3', 'LED_ACT_A'); LED(S, 'yellow', 'LED_ACT_A', 'LED_ACT_K')
P('J', S, 'Connector_Generic:Conn_01x03', 'DEBUG UART', 'Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical',
  {'1': 'GND', '2': 'UART_TX', '3': 'UART_RX'}, 'M20-9990345', 'Harwin', '3.3V serial console')     # J2
P('J', S, 'Connector_Generic:Conn_02x05_Odd_Even', 'EXPANSION', 'Connector_PinHeader_2.54mm:PinHeader_2x05_P2.54mm_Vertical',
  {'1': '+3V3', '2': '+5V', '3': 'I2C_SDA', '4': 'I2C_SCL', '5': 'GPIO12_PWM0', '6': 'GPIO13_PWM1', '7': 'GPIO16',
   '8': 'IOX_INT', '9': 'GND', '10': 'GND'}, 'M20-9980545', 'Harwin', 'Expansion header (I2C, 2x PWM, GPIO)')  # J3
for i in range(4):
    P('H', S, 'Mechanical:MountingHole', 'M3', 'MountingHole:MountingHole_3.2mm_M3', {}, '', '', 'Board mounting hole', dnp=True)

# ---------------------------------------------------------------- USB (boot mux, hub, ports)
S = 'usb'
P('U', S, 'Interface_USB:FSUSB42MUX', 'FSUSB42', 'Package_SO:MSOP-10_3x3mm_P0.5mm',
  {'VCC': '+3V3', 'SEL': 'nRPIBOOT', 'D+': 'CM_USB_P', 'D-': 'CM_USB_N', 'GND': 'GND', 'HSD1-': 'USBC_DM',
   'HSD1+': 'USBC_DP', 'HSD2-': 'HUB_UP_N', 'HSD2+': 'HUB_UP_P', '~{OE}': 'GND'},
  'FSUSB42MUX', 'onsemi', 'USB2.0 HS 2:1 switch: SEL=0 -> USB-C (rpiboot), SEL=1 -> hub')            # U5
C(S, '100n', '+3V3')
P('U', S, 'Power_Protection:USBLC6-2SC6', 'USBLC6-2', 'Package_TO_SOT_SMD:SOT-23-6',
  {'I/O1': 'USBC_DM', 'I/O2': 'USBC_DP', 'GND': 'GND', 'VBUS': '+3V3'}, 'USBLC6-2SC6', 'STMicroelectronics', 'USB ESD protection')
hub = {'1': 'USB1_DM', '2': 'USB1_DP', '3': 'USB2_DM', '4': 'USB2_DP', '6': 'USB3_DM', '7': 'USB3_DP', '8': '+3V3', '9': '+3V3',
       '5': '+3V3', '10': '+3V3', '15': '+3V3', '23': '+3V3', '29': '+3V3', '36': '+3V3', '11': 'GND',
       '12': 'USB1_EN', '13': 'USB1_FLT', '16': 'USB2_EN', '17': 'USB2_FLT', '19': 'HUB_OCS3', '14': 'HUB_CRFILT',
       '22': 'HUB_NONREM1', '24': 'HUB_CFG0', '25': 'HUB_CFG1', '26': 'HUB_RST', '27': 'HUB_VBUSDET', '28': 'HUB_NONREM0',
       '30': 'HUB_UP_N', '31': 'HUB_UP_P', '32': 'HUB_XO', '33': 'HUB_XI', '34': 'HUB_PLLFILT', '35': 'HUB_RBIAS', '37': 'GND'}
P('U', S, 'canopy:USB2514B', 'USB2514B', 'Package_DFN_QFN:QFN-36-1EP_6x6mm_P0.5mm_EP3.7x3.7mm', hub,
  'USB2514B-I/M2', 'Microchip', 'USB 2.0 HS 4-port hub (port 4 strapped off)')                      # U7
for n in range(6): C(S, '100n', '+3V3')
C(S, '10u', '+3V3'); C(S, '1u', 'HUB_CRFILT'); C(S, '100n', 'HUB_PLLFILT'); R(S, '12k', 'HUB_RBIAS', 'GND')
P('Y', S, 'Device:Crystal_GND24', '24MHz', 'Crystal:Crystal_SMD_3225-4Pin_3.2x2.5mm', {'1': 'HUB_XI', '3': 'HUB_XO', '2': 'GND', '4': 'GND'},
  'ABM8-24.000MHZ-B2-T', 'Abracon', 'Crystal 24MHz 18pF 3225')
C(S, '18p', 'HUB_XI'); C(S, '18p', 'HUB_XO')
for n in ('HUB_NONREM1', 'HUB_CFG0', 'HUB_CFG1', 'HUB_NONREM0'): R(S, '10k', n, 'GND')
R(S, '10k', '+3V3', 'HUB_RST'); C(S, '1u', 'HUB_RST'); R(S, '10k', '+3V3', 'HUB_VBUSDET'); R(S, '10k', '+3V3', 'HUB_OCS3')
for i in (1, 2):
    P('U', S, 'Power_Management:TPS2065CDBV', 'TPS2065C', 'Package_TO_SOT_SMD:SOT-23-5',
      {'IN': '+5V', 'EN': f'USB{i}_EN', '~{FLT}': f'USB{i}_FLT', 'OUT': f'USB{i}_VBUS', 'GND': 'GND'},
      'TPS2065CDBVR', 'Texas Instruments', 'USB port power switch 1A, active-high EN')
    R(S, '10k', '+3V3', f'USB{i}_FLT'); C(S, '10u', '+5V')
    P('C', S, 'Device:C_Polarized', '150u', 'Capacitor_Tantalum_SMD:CP_EIA-3528-21_Kemet-B', {'1': f'USB{i}_VBUS', '2': 'GND'},
      'T520B157M006ATE070', 'KEMET', '150uF 6.3V polymer')
    P('U', S, 'Power_Protection:USBLC6-2SC6', 'USBLC6-2', 'Package_TO_SOT_SMD:SOT-23-6',
      {'I/O1': f'USB{i}_DM', 'I/O2': f'USB{i}_DP', 'GND': 'GND', 'VBUS': f'USB{i}_VBUS'}, 'USBLC6-2SC6', 'STMicroelectronics', 'USB ESD protection')
P('J', S, 'Connector:USB_A_Stacked', 'USB-A x2', 'Connector_USB:USB_A_Wuerth_61400826021_Horizontal_Stacked',
  {'VBUS1': 'USB1_VBUS', 'D1-': 'USB1_DM', 'D1+': 'USB1_DP', 'GND1': 'GND', 'VBUS2': 'USB2_VBUS', 'D2-': 'USB2_DM',
   'D2+': 'USB2_DP', 'GND2': 'GND', 'Shield': 'GND'}, '61400826021', 'Wurth Elektronik', 'Dual stacked USB-A')   # J4
P('F', S, 'Device:Polyfuse', '0.75A', 'Fuse:Fuse_1206_3216Metric', {'1': '+5V', '2': 'USB3_VBUS'}, '1206L075THYR', 'Littelfuse', 'PTC 0.75A hold')
C(S, '10u', 'USB3_VBUS')
P('J', S, 'Connector:USB_A', 'USB-A internal (Zigbee)', 'Connector_USB:USB_A_Molex_105057_Vertical',
  {'VBUS': 'USB3_VBUS', 'D-': 'USB3_DM', 'D+': 'USB3_DP', 'GND': 'GND', 'Shield': 'GND'}, '105057-0001', 'Molex',
  'Vertical USB-A, internal port for Zigbee/Thread coordinator stick')                                # J5

# ---------------------------------------------------------------- Ethernet + microSD
S = 'net_sd'
eth = {f'MX{i+1}+': f'ETH{i}_P' for i in range(4)}; eth.update({f'MX{i+1}-': f'ETH{i}_N' for i in range(4)})
eth.update({f'MXCT{i+1}': f'ETH_CT{i+1}' for i in range(4)})
eth.update({'LED1+': 'ETH_LED1_A', 'LED1-': 'ETH_LED_LINK', 'LED2+': 'ETH_LED2_A', 'LED2-': 'ETH_LED_ACT', 'SH': 'CHASSIS'})
P('J', S, 'Connector:RJ45_JK0654219', 'RJ45 GbE', 'Connector_RJ:RJ45_Pulse_JK0654219NL_Horizontal', eth,
  'JK0654219NL', 'Pulse Electronics', 'RJ45 with 1000BASE-T magnetics and LEDs')                    # J6
for i in range(4): C(S, '100n', f'ETH_CT{i+1}')
R(S, '330R', '+3V3', 'ETH_LED1_A'); R(S, '330R', '+3V3', 'ETH_LED2_A')
C(S, '1n/2kV', 'CHASSIS'); R(S, '1M', 'CHASSIS', 'GND')
P('J', S, 'Connector:Micro_SD_Card', 'microSD', 'Connector_Card:microSD_HC_Molex_104031-0811',
  {'DAT2': 'SD_DAT2', 'DAT3/CD': 'SD_DAT3', 'CMD': 'SD_CMD', 'VDD': 'SD_VDD', 'CLK': 'SD_CLK', 'VSS': 'GND',
   'DAT0': 'SD_DAT0', 'DAT1': 'SD_DAT1', 'SHIELD': 'GND'}, '104031-0811', 'Molex', 'microSD push-pull socket')   # J7
P('U', S, 'Power_Management:TPS22917DBV', 'TPS22917', 'Package_TO_SOT_SMD:SOT-23-6',
  {'VIN': 'CM4_3V3', 'GND': 'GND', 'ON': 'SD_PWR_ON', 'QOD': 'SD_VDD', 'VOUT': 'SD_VDD'},
  'TPS22917DBVR', 'Texas Instruments', 'SD card power switch (lets CM4 power-cycle the card)')
R(S, '100k', 'SD_PWR_ON', 'GND'); C(S, '10u', 'SD_VDD'); C(S, '100n', 'SD_VDD'); C(S, '1u', 'CM4_3V3')

# ---------------------------------------------------------------- Audio
S = 'audio'
P('U', S, 'Audio:MAX98357A', 'MAX98357A', 'Package_DFN_QFN:TQFN-16-1EP_3x3mm_P0.5mm_EP1.23x1.23mm',
  {'DIN': 'I2S_DOUT', 'GND': 'GND', '~{SD_MODE}': 'AMP_SD', 'VDD': '+5V', 'OUTP': 'SPK_P', 'OUTN': 'SPK_N',
   'LRCLK': 'I2S_LRCLK', 'BCLK': 'I2S_BCLK', 'PAD': 'GND'}, 'MAX98357AETE+T', 'Analog Devices', 'I2S 3W class-D mono amplifier')
R(S, '100k', 'AMP_SD', 'GND'); C(S, '10u', '+5V'); C(S, '100n', '+5V')
P('J', S, 'Connector_Generic:Conn_01x02', 'SPEAKER 4-8R', 'Connector_JST:JST_PH_S2B-PH-K_1x02_P2.00mm_Horizontal',
  {'1': 'SPK_P', '2': 'SPK_N'}, 'S2B-PH-K-S(LF)(SN)', 'JST', 'Speaker connector')                  # J8
for lr in ('GND', '+3V3'):
    P('MK', S, 'Sensor_Audio:ICS-43434', 'ICS-43434', 'Sensor_Audio:InvenSense_ICS-43434-6_3.5x2.65mm',
      {'WS': 'I2S_LRCLK', 'LR': lr, 'GND': 'GND', 'SCK': 'I2S_BCLK', 'VDD': '+3V3', 'SD': 'I2S_DIN'},
      'ICS-43434', 'TDK InvenSense', 'I2S MEMS microphone, bottom port (%s channel)' % ('left' if lr == 'GND' else 'right'))
    C(S, '100n', '+3V3')
R(S, '100k', 'I2S_DIN', 'GND')

# ---------------------------------------------------------------- Radios, field I/O, sensors
S = 'io'
P('U', S, 'RF_Module:RFM95W-915S2', 'RFM95W', 'RF_Module:HOPERF_RFM9XW_SMD',
  {'GND': 'GND', 'MISO': 'SPI_MISO', 'MOSI': 'SPI_MOSI', 'SCK': 'SPI_SCK', 'NSS': 'LORA_NSS', 'RESET': 'LORA_RST',
   'ANT': 'LORA_ANT', '3.3V': '+3V3', 'DIO0': 'LORA_DIO0', 'DIO1': 'LORA_DIO1'}, 'RFM95W-915S2', 'HopeRF',
  'LoRa transceiver module SX1276, 915MHz (868MHz: RFM95W-868S2)')
C(S, '10u', '+3V3'); C(S, '100n', '+3V3')
P('J', S, 'Connector:Conn_Coaxial', 'LoRa ANT', 'Connector_Coaxial:U.FL_Hirose_U.FL-R-SMT-1_Vertical', {'In': 'LORA_ANT', 'Ext': 'GND'},
  'U.FL-R-SMT-1(10)', 'Hirose', 'U.FL antenna connector')                                            # J9
iox = {'VDD': '+3V3', 'VSS': 'GND', 'SCK': 'I2C_SCL', 'SDA': 'I2C_SDA', 'A0': 'GND', 'A1': 'GND', 'A2': 'GND',
       '~{RESET}': 'nEXTRST', 'INTB': 'IOX_INT', 'GPB0': 'BTN', 'GPB1': 'LED_R', 'GPB2': 'LED_G', 'GPB3': 'LED_B'}
iox.update({f'GPA{i}': f'RLY{i+1}' for i in range(8)}); iox.update({f'GPB{i+4}': f'DI{i+1}' for i in range(4)})
P('U', S, 'Interface_Expansion:MCP23017_SS', 'MCP23017', 'Package_SO:SSOP-28_5.3x10.2mm_P0.65mm', iox,
  'MCP23017-E/SS', 'Microchip', 'I2C 16-bit I/O expander @0x20; held in reset by CM4 nEXTRST')
C(S, '100n', '+3V3'); R(S, '10k', 'nEXTRST', 'GND')
uln = {f'I{i+1}': f'RLY{i+1}' for i in range(8)}; uln.update({f'O{i+1}': f'OUT{i+1}' for i in range(8)})
uln.update({'GND': 'GND', 'COM': 'V_FIELD'})
P('U', S, 'Transistor_Array:ULN2803A', 'ULN2803A', 'Package_SO:SOIC-18W_7.5x11.6mm_P1.27mm', uln,
  'ULN2803ADWR', 'Texas Instruments', '8x Darlington sink driver 50V/500mA with clamp diodes')
TB(S, 8, [f'OUT{i+1}' for i in range(8)], 'OUT1-8 (sink)')                                        # J10
TB(S, 4, ['V_FIELD', 'V_FIELD', 'GND', 'GND'], 'V_FIELD / GND')                                   # J11
C(S, '100n', 'V_FIELD')
P('SW', S, 'Switch:SW_Push', 'USER / TALK', 'Button_Switch_SMD:SW_SPST_B3U-1000P', {'1': 'BTN', '2': 'GND'}, 'B3U-1000P', 'Omron', 'Tact switch')
for c, n in (('red', 'LED_R'), ('green', 'LED_G'), ('blue', 'LED_B')):
    R(S, '1k', n, n + '_A'); LED(S, c, n + '_A', 'GND')
for i in range(1, 5):
    R(S, '1k', f'DI{i}_IN', f'DI{i}'); R(S, '10k', '+3V3', f'DI{i}')
# analog inputs
P('U', S, 'Analog_ADC:ADS1115IDGS', 'ADS1115', 'Package_SO:TSSOP-10_3x3mm_P0.5mm',
  {'ADDR': 'GND', 'GND': 'GND', 'AIN0': 'AIN0', 'AIN1': 'AIN1', 'AIN2': 'AIN2', 'AIN3': 'AIN3', 'VDD': '+3V3',
   'SDA': 'I2C_SDA', 'SCL': 'I2C_SCL'}, 'ADS1115IDGSR', 'Texas Instruments', '16-bit 4-ch I2C ADC @0x48')
C(S, '100n', '+3V3')
for i in (0, 1):   # 0-3.3V inputs (capacitive soil probes)
    R(S, '1k', f'AIN{i}_IN', f'AIN{i}'); C(S, '100n', f'AIN{i}')
for i in (2, 3):   # 0-10V inputs (industrial transmitters), divide by 3
    R(S, '20k', f'AIN{i}_IN', f'AIN{i}'); R(S, '10k', f'AIN{i}', 'GND'); C(S, '100n', f'AIN{i}')
TB(S, 6, ['AIN0_IN', 'AIN1_IN', 'AIN2_IN', 'AIN3_IN', '+3V3', 'GND'], 'AIN0-1 3V3 / AIN2-3 10V')  # J12
# RS-485 (Modbus RTU sensors)
P('U', S, 'Interface_UART:THVD1420D', 'THVD1420', 'Package_SO:SOIC-8_3.9x4.9mm_P1.27mm',
  {'RO': 'RS485_RX', '~{RE}': 'RS485_DE', 'DE': 'RS485_DE', 'DI': 'RS485_TX', 'GND': 'GND', 'A': 'RS485_A', 'B': 'RS485_B', 'VCC': '+3V3'},
  'THVD1420DR', 'Texas Instruments', '3.3V half-duplex RS-485 transceiver')
C(S, '100n', '+3V3'); R(S, '10k', 'RS485_DE', 'GND'); R(S, '10k', '+3V3', 'RS485_RX')
P('D', S, 'Diode:SM712_SOT23', 'SM712', 'Package_TO_SOT_SMD:SOT-23', {'A1': 'RS485_A', 'A2': 'RS485_B', 'common': 'GND'}, 'SM712.TCT', 'Semtech', 'RS-485 TVS')
R(S, '120R', 'RS485_A', 'RS485_TERM')
P('JP', S, 'Jumper:Jumper_2_Open', 'RS485 TERM', 'Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical',
  {'A': 'RS485_TERM', 'B': 'RS485_B'}, 'M20-9990245', 'Harwin', 'Fit jumper for 120R bus termination')
TB(S, 3, ['RS485_A', 'RS485_B', 'GND'], 'RS485 A/B/GND')                                           # J13
# RTC
P('U', S, 'Timer_RTC:DS3231MZ', 'DS3231M', 'Package_SO:SOIC-8_3.9x4.9mm_P1.27mm',
  {'VCC': '+3V3', 'GND': 'GND', 'VBAT': 'VBAT', 'SDA': 'I2C_SDA', 'SCL': 'I2C_SCL'}, 'DS3231MZ+TRL', 'Analog Devices', 'I2C RTC +/-5ppm @0x68')
C(S, '100n', '+3V3')
P('BT', S, 'Device:Battery_Cell', 'CR1220', 'Battery:BatteryHolder_Keystone_3000_1x12mm', {'+': 'VBAT', '-': 'GND'}, '3000', 'Keystone', 'CR1220 coin cell holder')
# Qwiic / STEMMA QT I2C sensor ports
for i in range(2):
    P('J', S, 'Connector_Generic_MountingPin:Conn_01x04_MountingPin', 'I2C (Qwiic)', 'Connector_JST:JST_SH_SM04B-SRSS-TB_1x04-1MP_P1.00mm_Horizontal',
      {'1': 'GND', '2': '+3V3', '3': 'I2C_SDA', '4': 'I2C_SCL', 'MP': 'GND'}, 'SM04B-SRSS-TB(LF)(SN)', 'JST', 'Qwiic / STEMMA QT I2C sensor port')
# pulse (flow meter) and 1-Wire inputs, 5V sensor supply
P('F', S, 'Device:Polyfuse', '0.5A', 'Fuse:Fuse_1206_3216Metric', {'1': '+5V', '2': '+5V_SENS'}, '0ZCJ0050FF2G', 'Bel Fuse', 'PTC 0.5A hold')
C(S, '10u', '+5V_SENS')
for i in (1, 2):
    R(S, '4.7k', '+5V_SENS', f'FLOW{i}_IN'); R(S, '22k', f'FLOW{i}_IN', f'FLOW{i}'); R(S, '33k', f'FLOW{i}', 'GND'); C(S, '1n', f'FLOW{i}')
R(S, '4.7k', '+3V3', 'ONEWIRE'); R(S, '100R', 'ONEWIRE_IN', 'ONEWIRE')
TB(S, 8, ['+5V_SENS', 'GND', 'FLOW1_IN', 'FLOW2_IN', 'ONEWIRE_IN', '+3V3', 'GND', 'GND'], '5V/FLOW1/FLOW2/1W/3V3')  # J16
TB(S, 6, ['DI1_IN', 'DI2_IN', 'DI3_IN', 'DI4_IN', 'GND', '+5V_SENS'], 'DI1-4 (dry contact)')      # J17

SHEETS = [('power', 'USB-C PD input, 5V and 3V3 rails'), ('cm4', 'Compute Module 4, boot, debug, expansion'),
          ('usb', 'USB boot mux, hub, ports'), ('net_sd', 'Gigabit Ethernet, microSD'),
          ('audio', 'I2S microphones and speaker amplifier'), ('io', 'LoRa, relay drivers, analog/digital field I/O, RS-485, RTC')]
