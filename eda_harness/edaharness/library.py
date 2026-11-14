"""부품 라이브러리 (심볼 핀 기하 + 전기 파라미터).

이 라이브러리는 '시드 데이터'다. 전기 파라미터는 공개 데이터시트의 대표값을 옮긴 것이며
data_status='UNVERIFIED_SEED'인 부품은 G3에서 WARN을 남긴다. 양산 전에는 실제 구매 부품의
데이터시트로 검증된 값(data_status='VERIFIED', source 기재)으로 교체해야 한다.

좌표계: KiCad 심볼 라이브러리 좌표 (mm, y축 위쪽 +). 핀 (x, y)는 '연결점'이고
angle은 연결점에서 몸체 쪽으로 핀이 뻗는 방향(0=오른쪽, 90=위, 180=왼쪽, 270=아래)이다.
"""
from __future__ import annotations

from dataclasses import dataclass, field

PIN_TYPES = {"passive", "input", "output", "bidirectional", "tri_state",
             "power_in", "power_out", "open_collector", "open_emitter",
             "unspecified", "no_connect"}


@dataclass(frozen=True)
class Pin:
    number: str
    name: str
    etype: str
    x: float
    y: float
    angle: int
    length: float = 2.54

    def __post_init__(self):
        if self.etype not in PIN_TYPES:
            raise ValueError(f"알 수 없는 핀 타입 {self.etype}")
        if self.angle not in (0, 90, 180, 270):
            raise ValueError("핀 각도는 0/90/180/270만 허용")


@dataclass
class PartDef:
    key: str
    ref_prefix: str
    pins: tuple
    body: tuple                      # (x1, y1, x2, y2) 라이브러리 좌표 사각형
    default_footprint: str
    description: str
    params: dict = field(default_factory=dict)
    power_symbol: bool = False
    data_status: str = "UNVERIFIED_SEED"
    source: str = ""
    kicad_symbol: str = ""            # 대응하는 KiCad 공식 심볼 '라이브러리:이름' (G7가 핀 번호를 대조)

    @property
    def lib_id(self) -> str:
        return f"eda:{self.key}"

    def pin(self, number: str) -> Pin:
        for p in self.pins:
            if p.number == number:
                return p
        raise KeyError(f"{self.key}에 핀 {number} 없음")

    @property
    def pin_numbers(self) -> list:
        return [p.number for p in self.pins]


def _two_pin_vertical(key, prefix, fp, desc, params, body_w=1.016, body_h=2.54):
    return PartDef(
        key=key, ref_prefix=prefix,
        pins=(Pin("1", "~", "passive", 0, 3.81, 270, 1.27),
              Pin("2", "~", "passive", 0, -3.81, 90, 1.27)),
        body=(-body_w, -body_h, body_w, body_h),
        default_footprint=fp, description=desc, params=params,
        data_status="GENERIC")


def _diode_like(key, prefix, fp, desc, params, status="UNVERIFIED_SEED", source=""):
    # KiCad 관례: 1=K(왼쪽), 2=A(오른쪽)
    return PartDef(
        key=key, ref_prefix=prefix,
        pins=(Pin("1", "K", "passive", -3.81, 0, 0, 1.27),
              Pin("2", "A", "passive", 3.81, 0, 180, 1.27)),
        body=(-2.54, -1.27, 2.54, 1.27),
        default_footprint=fp, description=desc, params=params,
        data_status=status, source=source)


def _nmos(key, fp, desc, params, source, d_num="2", s_num="3"):
    """N-MOSFET. 핀 번호는 부품(패키지)마다 다르다: G=1 고정, D/S 번호는 인자 (KiCad 공식 심볼 기준)."""
    return PartDef(
        key=key, ref_prefix="Q",
        pins=(Pin("1", "G", "passive", -5.08, 0, 0, 2.54),
              Pin(d_num, "D", "passive", 2.54, 5.08, 270, 2.54),
              Pin(s_num, "S", "passive", 2.54, -5.08, 90, 2.54)),
        body=(-2.54, -2.54, 3.81, 2.54),
        default_footprint=fp, description=desc, params=params, source=source)


def _ldo(vout):
    tag = f"{vout:.1f}"
    return PartDef(
        key=f"AMS1117-{tag}", ref_prefix="U",
        pins=(Pin("1", "GND", "power_in", 0, -7.62, 90, 2.54),
              Pin("2", "VO", "power_out", 7.62, 0, 180, 2.54),
              Pin("3", "VI", "power_in", -7.62, 0, 0, 2.54)),
        body=(-5.08, -5.08, 5.08, 2.54),
        default_footprint="Package_TO_SOT_SMD:SOT-223-3_TabPin2",
        description=f"{tag}V 1A LDO",
        params={"vout_v": vout, "dropout_v": 1.3, "iout_max_a": 1.0,
                "vin_max_v": 15.0, "tj_max_c": 125.0,
                "theta_ja_c_per_w": 90.0, "quiescent_a": 0.01,
                "cin_min_f": 10e-6, "cout_min_f": 22e-6},
        source="AMS1117 datasheet (Advanced Monolithic Systems) 대표값")


LIBRARY: dict = {}


def _add(p: PartDef):
    if p.key in LIBRARY:
        raise ValueError(f"중복 부품 키 {p.key}")
    LIBRARY[p.key] = p


_add(_two_pin_vertical("R", "R", "Resistor_SMD:R_0603_1608Metric", "Resistor 0603",
                       {"power_w": 0.1, "tolerance": 0.01}))
_add(_two_pin_vertical("C", "C", "Capacitor_SMD:C_0603_1608Metric", "Ceramic capacitor",
                       {}, body_w=2.032, body_h=0.762))
_add(_diode_like("LED", "D", "LED_SMD:LED_0603_1608Metric", "LED 0603",
                 {"if_max_a": 0.02}, status="GENERIC"))
_add(_diode_like("SS34", "D", "Diode_SMD:D_SMA", "Schottky 40V 3A",
                 {"vr_v": 40.0, "if_a": 3.0}, source="SS34 datasheet 대표값"))
_add(_diode_like("SS54", "D", "Diode_SMD:D_SMC", "Schottky 40V 5A",
                 {"vr_v": 40.0, "if_a": 5.0}, source="SS54 datasheet 대표값"))
_add(_nmos("AO3400A", "Package_TO_SOT_SMD:SOT-23",
           "N-MOSFET 30V 5.7A logic-level",
           {"vds_v": 30.0, "id_a": 5.7, "vgs_th_max_v": 1.45,
            "rds_on_ohm": 0.048, "rds_spec_vgs_v": 2.5, "pd_max_w": 0.7},
           "AO3400A datasheet (Alpha & Omega) 대표값, pd_max는 보수적 가정; 핀: SOT-23 1=G 2=S 3=D (KiCad 심볼과 일치)",
           d_num="3", s_num="2"))
_add(_nmos("IRLZ44N", "Package_TO_SOT_THT:TO-220-3_Vertical",
           "N-MOSFET 55V 47A logic-level",
           {"vds_v": 55.0, "id_a": 47.0, "vgs_th_max_v": 2.0,
            "rds_on_ohm": 0.035, "rds_spec_vgs_v": 4.0, "pd_max_w": 1.5},
           "IRLZ44N datasheet (Infineon) 대표값, 방열판 없음 가정"))
for _v in (1.8, 2.5, 3.3, 5.0):
    _add(_ldo(_v))
_add(PartDef(
    key="NE555P", ref_prefix="U",
    pins=(Pin("1", "GND", "power_in", 0, -12.7, 90),
          Pin("2", "TRIG", "input", -10.16, 2.54, 0),
          Pin("3", "OUT", "output", 10.16, 2.54, 180),
          Pin("4", "RST", "input", -10.16, 7.62, 0),
          Pin("5", "CONT", "input", -10.16, -7.62, 0),
          Pin("6", "THRES", "input", -10.16, -2.54, 0),
          Pin("7", "DISCH", "open_collector", 10.16, -2.54, 180),
          Pin("8", "VCC", "power_in", 0, 12.7, 270)),
    body=(-7.62, -10.16, 7.62, 10.16),
    default_footprint="Package_DIP:DIP-8_W7.62mm",
    description="555 timer (bipolar)",
    params={"vcc_min_v": 4.5, "vcc_max_v": 16.0, "iout_max_a": 0.2,
            "icc_a": 0.01},
    source="NE555 datasheet (TI) 대표값"))
_add(PartDef(
    key="Conn_01x02", ref_prefix="J",
    pins=(Pin("1", "Pin_1", "passive", -5.08, 0, 0, 3.81),
          Pin("2", "Pin_2", "passive", -5.08, -2.54, 0, 3.81)),
    body=(-1.27, -3.81, 1.27, 1.27),
    default_footprint="Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical",
    description="2-pin header", params={"current_max_a": 2.0},
    data_status="GENERIC", source="2.54mm 핀헤더 보수적 정격"))
def _header(n, key, desc):
    return PartDef(
        key=key, ref_prefix="J",
        pins=tuple(Pin(str(i + 1), f"Pin_{i + 1}", "passive", -5.08, -2.54 * i, 0, 3.81) for i in range(n)),
        body=(-1.27, -2.54 * (n - 1) - 1.27, 1.27, 1.27),
        default_footprint=f"Connector_PinHeader_2.54mm:PinHeader_1x{n:02d}_P2.54mm_Vertical",
        description=desc, params={"current_max_a": 2.0},
        data_status="GENERIC", source="2.54mm(100mil) 핀헤더 보수적 정격")


_add(_header(3, "Conn_01x03", "3-pin header"))
_add(_header(4, "Conn_01x04", "4-pin header"))
for _n in range(5, 21):
    _add(_header(_n, f"Conn_01x{_n:02d}", f"{_n}-pin header"))

_add(PartDef(
    key="TB_1x02", ref_prefix="J",
    pins=(Pin("1", "Pin_1", "passive", -5.08, 0, 0, 3.81),
          Pin("2", "Pin_2", "passive", -5.08, -5.08, 0, 3.81)),
    body=(-1.27, -6.35, 1.27, 1.27),
    default_footprint=("TerminalBlock_Phoenix:"
                       "TerminalBlock_Phoenix_MKDS-1,5-2-5.08_1x02_P5.08mm_Horizontal"),
    description="2-pin terminal block 5.08mm", params={"current_max_a": 10.0},
    data_status="GENERIC", source="MKDS 1,5 계열 보수적 정격"))
_add(PartDef(
    key="USB_C_Power_6P", ref_prefix="J",
    pins=(Pin("A9", "VBUS", "passive", 10.16, 5.08, 180),
          Pin("B9", "VBUS", "passive", 10.16, 2.54, 180),
          Pin("A5", "CC1", "bidirectional", 10.16, -2.54, 180),
          Pin("B5", "CC2", "bidirectional", 10.16, -5.08, 180),
          Pin("A12", "GND", "passive", -2.54, -10.16, 90),
          Pin("B12", "GND", "passive", 0, -10.16, 90),
          Pin("SH", "SHIELD", "passive", 2.54, -10.16, 90)),
    body=(-7.62, -7.62, 7.62, 7.62),
    default_footprint=("Connector_USB:"
                       "USB_C_Receptacle_GCT_USB4125-xx-x_6P_TopMnt_Horizontal"),
    description="USB-C power-only receptacle (sink)",
    params={"current_max_a": 3.0, "default_power_a": 0.5},
    source="USB Type-C spec: 싱크는 CC1/CC2 각각 5.1k Rd, 협상 없으면 기본 USB 전력"))
_add(PartDef(
    key="PWR_FLAG", ref_prefix="#FLG",
    pins=(Pin("1", "pwr", "power_out", 0, 0, 90, 0.0),),
    body=(-1.016, 0, 1.016, 2.54),
    default_footprint="", description="ERC power flag",
    power_symbol=True, data_status="GENERIC"))


def pin_number(key: str, pin_name: str) -> str:
    """핀 이름(D, S 등) -> 핀 번호. 이름이 없거나 중복이면 오류 (번호가 identity라 이름 검색은 부품 안에서만)."""
    hits = [p.number for p in get(key).pins if p.name == pin_name]
    if len(hits) != 1:
        raise KeyError(f"{key}에서 핀 이름 {pin_name!r}이 {len(hits)}개")
    return hits[0]


def get(key: str) -> PartDef:
    try:
        return LIBRARY[key]
    except KeyError:
        raise KeyError(f"라이브러리에 없는 부품: {key}") from None


# 하네스 부품 -> KiCad 공식 심볼 대응. G7가 핀 번호 집합이 같은지 실제 라이브러리와 대조한다.
KICAD_SYMBOL = {
    "R": "Device:R", "C": "Device:C", "LED": "Device:LED",
    "SS34": "Diode:SS34", "SS54": "Device:D_Schottky",
    "AO3400A": "Transistor_FET:AO3400A", "IRLZ44N": "Transistor_FET:IRLZ44N",
    "AMS1117-1.8": "Regulator_Linear:AMS1117-1.8", "AMS1117-2.5": "Regulator_Linear:AMS1117-2.5",
    "AMS1117-3.3": "Regulator_Linear:AMS1117-3.3", "AMS1117-5.0": "Regulator_Linear:AMS1117-5.0",
    "NE555P": "Timer:NE555P",
    "Conn_01x02": "Connector_Generic:Conn_01x02", "Conn_01x03": "Connector_Generic:Conn_01x03",
    "Conn_01x04": "Connector_Generic:Conn_01x04",
    "TB_1x02": "Connector:Screw_Terminal_01x02",
    "USB_C_Power_6P": "Connector:USB_C_Receptacle_PowerOnly_6P",
    "PWR_FLAG": "power:PWR_FLAG",
}
for _n in range(5, 21):
    KICAD_SYMBOL[f"Conn_01x{_n:02d}"] = f"Connector_Generic:Conn_01x{_n:02d}"
for _k, _sym in KICAD_SYMBOL.items():
    LIBRARY[_k].kicad_symbol = _sym
