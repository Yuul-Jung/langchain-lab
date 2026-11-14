#!/usr/bin/env python3
"""부품 분류 체계(우리 것)를 만든다: 도메인(L1) → 기능(L2) → KiCad 라이브러리(L3) → 일반 분류의 이름 규칙(L4).

입력(이 PC 전용): data/digikey/kicad_mapping_approved_r2.jsonl(위임 합의된 대응), data/digikey/taxonomy_raw.json(분류 경로),
                  static_data/parts_taxonomy.json 의 generic(일반 분류 이름 규칙 — 이 파일이 원본, 다시 만들 때 그대로 가져옴)
출력:
  static_data/parts_taxonomy.json  — DigiKey 이름·번호가 없는 우리 분류 체계(커밋 가능)
  data/parts_tree/digikey_ref.json — 우리 노드 ↔ DigiKey 분류 번호(이 PC 전용 참고, 지워도 분류 체계는 그대로)
기능(L2) 이름은 아래 FUNCTIONS 표에 우리 말로 적었다. DigiKey 경로 → 기능 연결은 PATH_RULES(첫 일치)로 이 스크립트 안에서만 쓴다.
상태: confirmed(위임 2단계 합의) · proposed(검토 필요) · rule(이름 규칙, 한 번 검토) · schematic_only · unmapped.
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import parts_taxonomy as pt  # noqa: E402

OUT = ROOT / "static_data" / "parts_taxonomy.json"
REF = ROOT / "data" / "parts_tree" / "digikey_ref.json"

DOMAINS = [
    ("processor", "처리기 (MCU·CPU·FPGA)", "Processors", "프로그램이나 논리를 실행하는 칩(마이크로컨트롤러·프로세서·DSP·FPGA·PLD)과 그것을 담은 모듈."),
    ("power", "전원", "Power", "전력을 변환·공급·구동하는 소자(레귤레이터·컨버터·배터리 관리·LED/모터/게이트 드라이버·전력 계측)."),
    ("analog", "아날로그·신호 처리", "Analog & signal", "연속 신호를 증폭·변환·비교·기준·감시하는 소자(증폭기·ADC/DAC·비교기·전압 기준·전원 감시·아날로그 스위치)."),
    ("logic", "디지털 로직·타이밍", "Logic & timing", "디지털 신호를 처리하고 시간 기준을 만드는 소자(게이트·카운터·레벨 변환·클록·타이머·발진기·크리스탈)."),
    ("memory", "메모리", "Memory", "데이터를 저장하는 칩(EEPROM·플래시·RAM·ROM 등)."),
    ("interface", "통신·인터페이스", "Interface", "칩·기기 사이의 통신 규격(UART·CAN·RS-485·USB·이더넷)을 처리하거나 신호를 절연·확장하는 소자."),
    ("rf", "RF·무선", "RF & wireless", "무선 신호를 보내고 받는 소자와 모듈(RF 증폭·믹서·트랜시버·RFID·안테나·RF 필터)."),
    ("sensor", "센서", "Sensors", "물리량(온도·전류·가스·위치·빛·압력)을 전기 신호로 바꾸는 소자."),
    ("discrete", "개별 반도체", "Discrete semiconductors", "단일 기능 반도체(다이오드·트랜지스터·사이리스터·IGBT)."),
    ("opto", "광·표시", "Optoelectronics & display", "빛을 내거나 보여 주는 소자(LED·레이저·LCD·OLED·광섬유)."),
    ("electromech", "전기기계 (릴레이·스위치·모터)", "Electromechanical", "움직이는 부분이 있는 소자(릴레이·스위치·모터·엔코더·냉각 팬)."),
    ("protection", "보호·필터", "Protection & filters", "서지·노이즈·과전류에서 회로를 지키는 소자(TVS·퓨즈·EMI 필터·페라이트)."),
    ("passive", "수동 소자", "Passives", "저항·커패시터·인덕터·변압기처럼 전원 없이 동작하는 기본 소자."),
    ("connect", "연결·기구", "Connectors & mechanical", "연결하고 고정하는 기구 부품(커넥터·헤더·방열판)."),
    ("boards", "개발 보드·키트", "Boards & kits", "개발 보드·평가 키트·프로그래머."),
    ("other", "기타", "Other", "위 어디에도 맞지 않는 특수 IC와 회로도 전용 기호."),
]
# (id, 도메인, 한국어, English)
FUNCTIONS = [
    ("mcu", "processor", "마이크로컨트롤러", "Microcontrollers"), ("mpu_soc", "processor", "마이크로프로세서·SoC", "Microprocessors & SoC"),
    ("dsp", "processor", "DSP", "DSP"), ("fpga", "processor", "FPGA", "FPGA"), ("pld", "processor", "CPLD·PLD", "CPLD & PLD"),
    ("module", "processor", "마이컴·컴퓨터 모듈", "Embedded modules"),
    ("opamp", "analog", "OP앰프·증폭기", "Amplifiers"), ("audio_amp", "analog", "오디오 증폭기", "Audio amplifiers"),
    ("audio_codec", "analog", "오디오 처리·코덱", "Audio processing"), ("microphone", "analog", "마이크·스피커·부저", "Microphones, speakers, buzzers"),
    ("video", "analog", "비디오 증폭·처리", "Video"), ("comparator", "analog", "비교기", "Comparators"),
    ("adc", "analog", "AD 변환기", "ADC"), ("dac", "analog", "DA 변환기", "DAC"), ("digipot", "analog", "디지털 가변저항", "Digital potentiometers"),
    ("ldo", "power", "선형 레귤레이터(LDO)", "Linear regulators"), ("switching_reg", "power", "스위칭 레귤레이터", "Switching regulators"),
    ("reg_controller", "power", "레귤레이터 컨트롤러", "Regulator controllers"), ("dcdc_module", "power", "DC-DC 모듈", "DC-DC modules"),
    ("acdc", "power", "AC-DC 전원", "AC-DC converters"), ("battery_mgmt", "power", "배터리 관리·충전", "Battery management"),
    ("supervisor", "analog", "전원 감시·리셋", "Supervisors"), ("reference", "analog", "전압 기준", "Voltage references"),
    ("led_driver", "power", "LED 드라이버", "LED drivers"), ("motor_driver", "power", "모터 드라이버", "Motor drivers"),
    ("gate_driver", "power", "게이트 드라이버", "Gate drivers"), ("display_driver", "power", "디스플레이 드라이버", "Display drivers"),
    ("current_reg", "power", "전류 조절·관리", "Current regulation"), ("metering", "power", "전력 계측", "Energy metering"),
    ("vf_conv", "power", "V/F·F/V 변환", "V/F converters"), ("battery_cell", "power", "배터리·전지", "Batteries & cells"), ("solar", "power", "태양전지", "Solar cells"),
    ("gates", "logic", "게이트·인버터", "Gates & inverters"), ("logic_buffer", "logic", "로직 버퍼·트랜시버", "Logic buffers & transceivers"),
    ("counters", "logic", "카운터·분주기", "Counters & dividers"), ("level_shifter", "logic", "레벨 변환", "Level translators"),
    ("clock_gen", "logic", "클록 발생·PLL", "Clock generators & PLL"), ("clock_buffer", "logic", "클록 버퍼·팬아웃", "Clock buffers & fanout"), ("timer_ic", "logic", "타이머 IC", "Timer ICs"),
    ("rtc", "logic", "실시간 시계(RTC)", "Real-time clocks"), ("oscillator", "logic", "발진기", "Oscillators"),
    ("crystal", "logic", "크리스탈·공진자", "Crystals & resonators"), ("delay", "logic", "지연선", "Delay lines"),
    ("memory_ic", "memory", "메모리", "Memory"),
    ("line_transceiver", "interface", "통신 트랜시버(UART·CAN·RS-485·USB)", "Line transceivers"), ("uart", "interface", "UART", "UART"),
    ("if_controller", "interface", "인터페이스 컨트롤러", "Interface controllers"), ("io_expander", "interface", "I/O 확장", "I/O expanders"),
    ("analog_switch", "analog", "아날로그 스위치·멀티플렉서", "Analog switches & mux"),
    ("sensor_if", "interface", "센서 인터페이스", "Sensor interfaces"), ("touch", "interface", "정전식 터치", "Capacitive touch"),
    ("signal_buffer", "interface", "신호 버퍼·리피터", "Signal buffers & repeaters"), ("telecom", "interface", "통신선 인터페이스", "Telecom interfaces"),
    ("isolator", "interface", "절연기·포토커플러", "Isolators & optocouplers"), ("if_special", "interface", "특수 인터페이스", "Specialized interfaces"),
    ("rf_amp", "rf", "RF 증폭기", "RF amplifiers"), ("rf_mixer", "rf", "RF 믹서", "RF mixers"), ("rf_switch", "rf", "RF 스위치", "RF switches"),
    ("rf_receiver", "rf", "RF 수신기", "RF receivers"), ("rf_transceiver", "rf", "RF 트랜시버 IC", "RF transceiver ICs"),
    ("rf_module", "rf", "무선 모듈·모뎀", "Wireless modules & modems"), ("rfid", "rf", "RFID·NFC", "RFID & NFC"),
    ("rf_misc", "rf", "기타 RF", "Other RF"), ("antenna", "rf", "안테나", "Antennas"), ("rf_filter", "rf", "RF 필터", "RF filters"),
    ("current_sensor", "sensor", "전류 센서", "Current sensors"), ("gas_sensor", "sensor", "가스 센서", "Gas sensors"),
    ("humidity_sensor", "sensor", "습도 센서", "Humidity sensors"), ("imu", "sensor", "관성·모션 센서", "Motion sensors & IMU"),
    ("multi_sensor", "sensor", "복합 센서", "Multifunction sensors"), ("light_sensor", "sensor", "광 센서", "Optical sensors"),
    ("distance_sensor", "sensor", "거리·근접 센서", "Distance & proximity sensors"), ("ir_receiver", "sensor", "적외선 수신", "IR receivers"),
    ("position_sensor", "sensor", "위치·자기 센서", "Position & magnetic sensors"), ("pressure_sensor", "sensor", "압력 센서", "Pressure sensors"),
    ("temp_sensor", "sensor", "온도 센서", "Temperature sensors"), ("thermistor", "sensor", "서미스터·열전대", "Thermistors & thermocouples"),
    ("diode", "discrete", "다이오드", "Diodes"), ("bridge", "discrete", "브리지 정류기", "Bridge rectifiers"),
    ("thyristor", "discrete", "사이리스터·TRIAC", "Thyristors & TRIACs"), ("bjt", "discrete", "바이폴라 트랜지스터", "Bipolar transistors"),
    ("bjt_array", "discrete", "트랜지스터 어레이", "Transistor arrays"), ("transistor", "discrete", "트랜지스터(일반)", "Transistors (general)"), ("fet", "discrete", "FET·MOSFET", "FETs & MOSFETs"),
    ("igbt", "discrete", "IGBT", "IGBT"), ("current_diode", "discrete", "정전류 소자", "Current-regulating devices"),
    ("led", "opto", "LED", "LEDs"), ("laser", "opto", "레이저 다이오드", "Laser diodes"), ("fiber", "opto", "광섬유 모듈", "Fiber-optic modules"),
    ("lcd_char", "opto", "문자 LCD·OLED", "Character displays"), ("lcd_graphic", "opto", "그래픽 LCD·OLED", "Graphic displays"),
    ("lamp", "opto", "램프·표시등", "Lamps"),
    ("relay", "electromech", "릴레이", "Relays"), ("ssr", "electromech", "반도체 릴레이(SSR)", "Solid-state relays"),
    ("switch", "electromech", "스위치", "Switches"), ("motor", "electromech", "모터·액추에이터", "Motors & actuators"),
    ("thermal", "electromech", "열 관리", "Thermal management"), ("encoder", "electromech", "엔코더", "Encoders"),
    ("tvs", "protection", "TVS·서지 보호", "TVS & surge protection"), ("emi_filter", "protection", "EMI·노이즈 필터", "EMI filters"),
    ("fuse", "protection", "퓨즈·차단기", "Fuses & breakers"), ("varistor", "protection", "배리스터·방전관", "Varistors & arresters"),
    ("ferrite", "protection", "페라이트 비드", "Ferrite beads"),
    ("resistor", "passive", "저항", "Resistors"), ("capacitor", "passive", "커패시터", "Capacitors"), ("inductor", "passive", "인덕터", "Inductors"),
    ("transformer", "passive", "변압기", "Transformers"), ("passive_misc", "passive", "기타 수동 소자", "Other passives"),
    ("connector", "connect", "커넥터", "Connectors"), ("header", "connect", "헤더·점퍼", "Headers & jumpers"),
    ("mechanical", "connect", "기구·방열", "Mechanical"),
    ("dev_board", "boards", "개발 보드·키트", "Boards & kits"),
    ("specialized_ic", "other", "특수 IC", "Specialized ICs"), ("vacuum_tube", "other", "진공관", "Vacuum tubes"), ("schematic_symbol", "other", "회로도 전용 기호", "Schematic-only symbols"),
]
FUNC = {f[0]: f for f in FUNCTIONS}

# DigiKey 경로(소문자) → 기능. 첫 일치가 이긴다. 이 표는 이 스크립트 안에서만 쓰고 결과 파일에는 남지 않는다.
PATH_RULES = [
    (r"embedded computers", "module"), (r"fpgas", "fpga"), (r"cplds|plds", "pld"), (r"> dsp", "dsp"),
    (r"microprocessors|system on chip", "mpu_soc"), (r"embedded > microcontrollers", "mcu"),
    (r"> memory", "memory_ic"), (r"audio amplifiers", "audio_amp"), (r"audio special purpose", "audio_codec"),
    (r"microphones", "microphone"), (r"video", "video"), (r"comparators", "comparator"),
    (r"analog to digital", "adc"), (r"digital to analog", "dac"), (r"digital potentiometers", "digipot"),
    (r"> amplifiers", "opamp"),
    (r"linear regulator controllers", "reg_controller"), (r"low drop out|\(ldo\)", "ldo"), (r"switching regulators", "switching_reg"),
    (r"dc dc converters", "dcdc_module"), (r"ac dc converters", "acdc"), (r"battery management", "battery_mgmt"),
    (r"supervisors", "supervisor"), (r"voltage reference", "reference"), (r"led drivers", "led_driver"),
    (r"motor drivers", "motor_driver"), (r"gate drivers", "gate_driver"), (r"display drivers", "display_driver"),
    (r"current regulation/management", "current_reg"), (r"energy metering", "metering"), (r"v/f and f/v", "vf_conv"),
    (r"battery products", "battery_cell"),
    (r"gates and inverters", "gates"), (r"logic > buffers", "logic_buffer"), (r"counters", "counters"), (r"translators", "level_shifter"),
    (r"clock generators", "clock_gen"), (r"programmable timers", "timer_ic"), (r"real time clocks", "rtc"),
    (r"> oscillators", "oscillator"), (r"crystals|resonators", "crystal"),
    (r"uarts", "uart"), (r"drivers, receivers, transceivers", "line_transceiver"), (r"> interface > controllers", "if_controller"),
    (r"i/o expanders", "io_expander"), (r"analog switches", "analog_switch"), (r"sensor and detector interfaces", "sensor_if"),
    (r"capacitive touch", "touch"), (r"signal buffers", "signal_buffer"), (r"> telecom", "telecom"), (r"isolators", "isolator"),
    (r"interface > specialized", "if_special"),
    (r"rf amplifiers", "rf_amp"), (r"rf mixers", "rf_mixer"), (r"rf switches", "rf_switch"), (r"rf receivers", "rf_receiver"),
    (r"transceiver ics", "rf_transceiver"), (r"transceiver modules|modems", "rf_module"), (r"rfid", "rfid"), (r"rf misc", "rf_misc"),
    (r"rf antennas", "antenna"), (r"rf filters", "rf_filter"),
    (r"current sensors", "current_sensor"), (r"gas sensors", "gas_sensor"), (r"humidity", "humidity_sensor"),
    (r"motion sensors|imus", "imu"), (r"multifunction", "multi_sensor"), (r"ambient light", "light_sensor"),
    (r"distance measuring|proximity", "distance_sensor"), (r"remote receiver", "ir_receiver"),
    (r"position sensors|angle, linear", "position_sensor"), (r"pressure", "pressure_sensor"),
    (r"temperature sensors", "temp_sensor"), (r"encoders", "encoder"),
    (r"bridge rectifiers", "bridge"), (r"single diodes|> diodes", "diode"), (r"thyristors|triacs", "thyristor"),
    (r"transistor arrays", "bjt_array"), (r"bipolar", "bjt"), (r"fets|mosfets", "fet"), (r"igbt", "igbt"),
    (r"current regulation - diodes", "current_diode"),
    (r"led emitters|led indication", "led"), (r"laser", "laser"), (r"fiber optic", "fiber"), (r"character and numeric", "lcd_char"),
    (r"lcd, oled, graphic", "lcd_graphic"), (r"optoelectronics$", "lamp"),
    (r"power relays", "relay"), (r"solid state relays", "ssr"), (r"pushbutton|> switches|^switches", "switch"),
    (r"motors|actuators|solenoids", "motor"), (r"thermal management", "thermal"),
    (r"tvs|transient voltage", "tvs"), (r"emi/rfi", "emi_filter"), (r"circuit protection > fuses|circuit breakers|ptc", "fuse"),
    (r"varistors|gas discharge|arresters|circuit protection$", "varistor"), (r"ferrite", "ferrite"), (r"^filters$", "emi_filter"),
    (r"resistors", "resistor"), (r"capacitors", "capacitor"), (r"inductors", "inductor"), (r"transformers", "transformer"),
    (r"connectors|barrel", "connector"), (r"shunts, jumpers", "header"), (r"hardware, fasteners", "mechanical"),
    (r"specialized ics", "specialized_ic"),
]
SCHEMATIC_ONLY = ["Auxiliary_Items", "Simulation_SPICE", "power", "Graphic"]


def function_for(path: str):
    p = path.lower()
    for rx, f in PATH_RULES:
        if re.search(rx, p):
            return f
    return None


def main():
    if OUT.exists() and "--force" not in sys.argv:
        sys.exit(f"{OUT.name} 가 이미 있습니다. 이 파일이 원본입니다(검토 수정·혼합 표시·부분 규칙이 들어 있음). 처음부터 다시 만들려면 --force (수정이 사라집니다).")
    import importlib.util
    spec = importlib.util.spec_from_file_location("mapdk", ROOT / "scripts" / "map-digikey-kicad.py")
    mapdk = importlib.util.module_from_spec(spec); spec.loader.exec_module(mapdk)
    cats = mapdk.categories()
    rows = [json.loads(l) for l in (ROOT / "data" / "digikey" / "kicad_mapping_approved_r2.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    existing = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    generic_out = existing.get("generic", {})     # 일반 분류 이름 규칙은 이 파일이 원본이다(사람이 고쳐 쓴다). 다시 만들 때 그대로 가져온다
    libs_out, ref_libs, ref_fn, unmapped, unmatched = {}, {}, {}, [], []
    generic_libs = set(generic_out)
    for r in rows:
        lib = r["kicad"]
        if lib in generic_libs:
            continue
        if lib in SCHEMATIC_ONLY:
            libs_out[lib] = {"function": "schematic_symbol", "status": "schematic_only", "source": "회로도 전용(구매 부품 아님)", "approver": "-", "also_ok": []}
            continue
        if not r.get("digikey_id"):
            unmapped.append(lib); continue
        path = cats[r["digikey_id"]]["path"]
        fn = function_for(path)
        if fn is None:
            unmatched.append((lib, path)); continue
        status = {"approved": "confirmed", "proposed": "proposed"}.get(r["decision"], "proposed")
        src = ("DigiKey 실제 부품 증거(2차)" if r.get("round") == 2 and r["decision"] == "approved"
               else "독립 검토 + 이름 유사도(1차)" if r["decision"] == "approved" else "독립 검토 답, 근거 보강 전")
        libs_out[lib] = {"function": fn, "status": status, "source": src,
                         "approver": r.get("approver", "-") if status == "confirmed" else "-", "also_ok": []}
        ref_libs[lib] = r["digikey_id"]
        ref_fn.setdefault(fn, set()).add(r["digikey_id"])
    if unmatched:
        print("규칙에 맞지 않는 경로:", unmatched); sys.exit(1)
    data = {"version": 1, "_note": "부품 분류 체계(우리 것, DigiKey 이름·번호 없음). 검토 전 초안. 만든 도구: scripts/build-parts-taxonomy.py",
            "domains": [{"id": i, "ko": k, "en": e, "definition": d} for i, k, e, d in DOMAINS],
            "functions": [{"id": i, "domain": d, "ko": k, "en": e, "kind": pt.default_kind(i, d)} for i, d, k, e in FUNCTIONS],
            "libraries": dict(sorted(libs_out.items())), "generic": generic_out, "unmapped": sorted(unmapped)}
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    REF.parent.mkdir(parents=True, exist_ok=True)
    REF.write_text(json.dumps({"_note": "이 PC 전용 참고(DigiKey 분류 번호). 우리 분류 체계는 이 파일 없이 동작한다.",
                               "libraries": ref_libs, "functions": {k: sorted(v) for k, v in ref_fn.items()}},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    cnt = Counter(v["status"] for v in libs_out.values())
    print("라이브러리", len(libs_out), dict(cnt), "| 일반 분류", {k: len(v) for k, v in generic_out.items()}, "| 미분류", len(unmapped))


if __name__ == "__main__":
    main()
