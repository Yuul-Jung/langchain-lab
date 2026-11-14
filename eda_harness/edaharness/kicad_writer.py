"""Design IR -> KiCad 8 스키매틱(.kicad_sch) + 프로젝트 로컬 심볼 라이브러리.

배치 전략 (Stage01): 블록 단위 격자 배치, 모든 핀에 2.54mm 스텁 와이어 + 넷 라벨.
라벨 기반 연결은 사람이 보기에는 덜 예쁘지만, 와이어 교차로 인한 '의도치 않은 연결'이
구조적으로 생기지 않아 라운드트립 검증이 단순하고 확실하다. 미관 개선(배선 라우팅)은
라운드트립 Gate를 유지한 채 Stage02에서 다룬다.
"""
from __future__ import annotations

import json
import uuid

from . import library
from .sexpr import Sym, dumps

GRID = 2.54
STUB = 2.54
CELL_W = 16 * GRID       # 40.64
CELL_H = 20 * GRID       # 50.8 (세로 라벨 두 개가 겹치지 않는 간격)
PER_ROW = 4
GROUP_GAP = 4 * GRID
MARGIN = 10 * GRID
PAPERS = (("A3", 420.0, 297.0), ("A2", 594.0, 420.0), ("A1", 841.0, 594.0), ("A0", 1189.0, 841.0))
KICAD_SCH_VERSION = 20231120   # KiCad 8 포맷


def _uid(project, key) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"eda-harness:{project}:{key}"))


def _font(size=1.27):
    return [Sym("font"), [Sym("size"), size, size]]


def _effects(hide=False, justify=None, size=1.27):
    e = [Sym("effects"), _font(size)]
    if justify:
        e.append([Sym("justify")] + [Sym(j) for j in justify])
    if hide:
        e.append(Sym("hide"))
    return e


def _snap(v):
    return round(round(v / 1.27) * 1.27, 4)


def pin_point(sx, sy, pin):
    """심볼 원점(sx, sy, 회전 0) 기준 핀 연결점의 스키매틱 좌표 (y 아래 +)."""
    return round(sx + pin.x, 4), round(sy - pin.y, 4)


def pin_outward(pin):
    """연결점에서 몸체 반대쪽(바깥) 방향 단위벡터 (스키매틱 좌표)."""
    return {0: (-1, 0), 180: (1, 0), 90: (0, 1), 270: (0, -1)}[pin.angle]


# ------------------------------------------------------------------ 라이브러리 심볼

def lib_symbol(part: library.PartDef, name: str):
    node = [Sym("symbol"), name]
    if part.power_symbol:
        node.append([Sym("power")])
    node.append([Sym("pin_numbers"), Sym("hide")])
    two_pin = len(part.pins) <= 2
    pn = [Sym("pin_names"), [Sym("offset"), 0 if two_pin else 1.016]]
    if two_pin or part.power_symbol:
        pn.append(Sym("hide"))
    node.append(pn)
    on_board = Sym("no") if part.power_symbol else Sym("yes")
    node += [[Sym("exclude_from_sim"), Sym("no")], [Sym("in_bom"), on_board],
             [Sym("on_board"), on_board]]
    x1, y1, x2, y2 = part.body
    node += [
        [Sym("property"), "Reference", part.ref_prefix, [Sym("at"), x2 + 1.27, y2, 0],
         _effects(hide=part.power_symbol, justify=["left"])],
        [Sym("property"), "Value", part.key, [Sym("at"), x2 + 1.27, y1, 0],
         _effects(justify=["left"])],
        [Sym("property"), "Footprint", part.default_footprint, [Sym("at"), 0, 0, 0], _effects(hide=True)],
        [Sym("property"), "Datasheet", "~", [Sym("at"), 0, 0, 0], _effects(hide=True)],
        [Sym("property"), "Description", part.description, [Sym("at"), 0, 0, 0], _effects(hide=True)],
    ]
    short = name.split(":", 1)[-1]
    stroke = [Sym("stroke"), [Sym("width"), 0.254], [Sym("type"), Sym("default")]]
    if part.power_symbol:
        gfx = [Sym("polyline"), [Sym("pts"), [Sym("xy"), 0, 0], [Sym("xy"), 0, 1.27],
                                 [Sym("xy"), -1.016, 1.905], [Sym("xy"), 0, 2.54],
                                 [Sym("xy"), 1.016, 1.905], [Sym("xy"), 0, 1.27]],
               [Sym("stroke"), [Sym("width"), 0], [Sym("type"), Sym("default")]],
               [Sym("fill"), [Sym("type"), Sym("none")]]]
    else:
        fill = Sym("background") if len(part.pins) > 2 else Sym("none")
        gfx = [Sym("rectangle"), [Sym("start"), x1, y1], [Sym("end"), x2, y2], stroke,
               [Sym("fill"), [Sym("type"), fill]]]
    node.append([Sym("symbol"), f"{short}_0_1", gfx])
    pins = [Sym("symbol"), f"{short}_1_1"]
    for p in part.pins:
        pin = [Sym("pin"), Sym(p.etype), Sym("line"), [Sym("at"), p.x, p.y, p.angle],
               [Sym("length"), p.length]]
        if part.power_symbol:
            pin.append(Sym("hide"))
        pin += [[Sym("name"), p.name, _effects()], [Sym("number"), p.number, _effects()]]
        pins.append(pin)
    node.append(pins)
    return node


# ------------------------------------------------------------------ 배치

def layout(ir) -> dict:
    """컴포넌트 id -> (x, y). 블록 순서대로 격자에 놓는다."""
    groups: dict = {}
    for cid, c in ir["components"].items():
        groups.setdefault(c["block"], []).append(cid)
    pos, heads = {}, {}
    x, y, band_h = MARGIN, MARGIN + 2 * GRID, 0.0
    max_w = PAPERS[0][1] - MARGIN
    for blk, cids in groups.items():
        cols = min(len(cids), PER_ROW)
        rows = (len(cids) + PER_ROW - 1) // PER_ROW
        gw, gh = cols * CELL_W, rows * CELL_H
        if x + gw > max_w and x > MARGIN:
            x, y, band_h = MARGIN, y + band_h + GROUP_GAP, 0.0
        heads[blk] = (x, y)
        for i, cid in enumerate(cids):
            r, k = divmod(i, PER_ROW)
            pos[cid] = (_snap(x + k * CELL_W + CELL_W / 2), _snap(y + r * CELL_H + CELL_H / 2))
        x += gw + GROUP_GAP
        band_h = max(band_h, gh)
    total_w = max(px for px, _ in pos.values()) + CELL_W
    total_h = max(py for _, py in pos.values()) + CELL_H
    paper = next((p for p in PAPERS if total_w <= p[1] and total_h <= p[2]), PAPERS[-1])
    return {"pos": pos, "heads": heads, "paper": paper[0]}


# ------------------------------------------------------------------ 스키매틱

def write_schematic(ir, date: str = "") -> str:
    project = ir["project"]["name"]
    root = _uid(project, "root")
    lay = layout(ir)
    used = []
    for c in ir["components"].values():
        if c["part"] not in used:
            used.append(c["part"])

    sch = [Sym("kicad_sch"), [Sym("version"), KICAD_SCH_VERSION],
           [Sym("generator"), "eda_harness"], [Sym("generator_version"), "0.1"],
           [Sym("uuid"), root], [Sym("paper"), lay["paper"]],
           [Sym("title_block"), [Sym("title"), project], [Sym("date"), date],
            [Sym("rev"), ir["intent_sha256"][:8]],
            [Sym("comment"), 1, "Generated by eda_harness from Design IR — 직접 편집 금지, IR을 수정하고 재생성"]],
           [Sym("lib_symbols")] + [lib_symbol(library.get(k), f"eda:{k}") for k in used]]

    for blk, (hx, hy) in lay["heads"].items():
        t = ir["blocks"].get(blk, {}).get("type", "power_flags")
        sch.append([Sym("text"), f"{blk}: {t}", [Sym("at"), _snap(hx), _snap(hy), 0],
                    _effects(justify=["left", "bottom"], size=1.524),
                    [Sym("uuid"), _uid(project, f"head:{blk}")]])

    for cid, c in ir["components"].items():
        part = library.get(c["part"])
        sx, sy = lay["pos"][cid]
        x1, y1, x2, y2 = part.body
        if any(p.angle in (90, 270) for p in part.pins):     # 위/아래 핀이 있으면 글자는 오른쪽
            ref_at = (_snap(sx + x2 + 1.27), _snap(sy - y2 - 1.27))
            val_at = (_snap(sx + x2 + 1.27), _snap(sy - y1 + 1.27))
        else:                                                 # 좌우 핀만 있으면 글자는 위쪽
            ref_at = (_snap(sx + x1), _snap(sy - y2 - 3.81))
            val_at = (_snap(sx + x1), _snap(sy - y2 - 1.27))
        inst = [Sym("symbol"), [Sym("lib_id"), f"eda:{c['part']}"], [Sym("at"), sx, sy, 0],
                [Sym("unit"), 1], [Sym("exclude_from_sim"), Sym("no")],
                [Sym("in_bom"), Sym("no") if part.power_symbol else Sym("yes")],
                [Sym("on_board"), Sym("no") if part.power_symbol else Sym("yes")],
                [Sym("dnp"), Sym("no")], [Sym("uuid"), _uid(project, f"sym:{cid}")],
                [Sym("property"), "Reference", c["ref"], [Sym("at"), ref_at[0], ref_at[1], 0],
                 _effects(hide=part.power_symbol, justify=["left"])],
                [Sym("property"), "Value", c["value"], [Sym("at"), val_at[0], val_at[1], 0],
                 _effects(justify=["left"])],
                [Sym("property"), "Footprint", c["footprint"], [Sym("at"), sx, sy, 0], _effects(hide=True)],
                [Sym("property"), "Datasheet", "~", [Sym("at"), sx, sy, 0], _effects(hide=True)],
                [Sym("property"), "EDA_ID", cid, [Sym("at"), sx, sy, 0], _effects(hide=True)]]
        for p in part.pins:
            inst.append([Sym("pin"), p.number, [Sym("uuid"), _uid(project, f"pin:{cid}:{p.number}")]])
        inst.append([Sym("instances"), [Sym("project"), project,
                                        [Sym("path"), f"/{root}", [Sym("reference"), c["ref"]],
                                         [Sym("unit"), 1]]]])
        sch.append(inst)

        for p in part.pins:
            px, py = pin_point(sx, sy, p)
            if p.number in c["no_connect"]:
                sch.append([Sym("no_connect"), [Sym("at"), px, py],
                            [Sym("uuid"), _uid(project, f"nc:{cid}:{p.number}")]])
                continue
            net = c["pins"][p.number]
            dx, dy = pin_outward(p)
            ex, ey = round(px + dx * STUB, 4), round(py + dy * STUB, 4)
            sch.append([Sym("wire"), [Sym("pts"), [Sym("xy"), px, py], [Sym("xy"), ex, ey]],
                        [Sym("stroke"), [Sym("width"), 0], [Sym("type"), Sym("default")]],
                        [Sym("uuid"), _uid(project, f"wire:{cid}:{p.number}")]])
            ang, just = {(-1, 0): (180, "right"), (1, 0): (0, "left"),
                         (0, -1): (90, "left"), (0, 1): (270, "right")}[(dx, dy)]
            sch.append([Sym("label"), net, [Sym("at"), ex, ey, ang],
                        [Sym("fields_autoplaced"), Sym("yes")],
                        _effects(justify=[just, "bottom"]),
                        [Sym("uuid"), _uid(project, f"label:{cid}:{p.number}")]])

    sch.append([Sym("sheet_instances"), [Sym("path"), "/", [Sym("page"), "1"]]])
    return dumps(sch) + "\n"


def write_symbol_library(ir) -> str:
    used = []
    for c in ir["components"].values():
        if c["part"] not in used:
            used.append(c["part"])
    lib = [Sym("kicad_symbol_lib"), [Sym("version"), KICAD_SCH_VERSION],
           [Sym("generator"), "eda_harness"], [Sym("generator_version"), "0.1"]]
    lib += [lib_symbol(library.get(k), k) for k in used]
    return dumps(lib) + "\n"


SYM_LIB_TABLE = """(sym_lib_table
  (version 7)
  (lib (name "eda")(type "KiCad")(uri "${KIPRJMOD}/eda.kicad_sym")(options "")(descr "eda_harness generated symbols"))
)
"""


def write_project(ir) -> str:
    name = ir["project"]["name"]
    return json.dumps({
        "meta": {"filename": f"{name}.kicad_pro", "version": 1},
        "schematic": {"legacy_lib_dir": "", "legacy_lib_list": []},
        "sheets": [[_uid(name, "root"), "Root"]],
        "boards": [], "text_variables": {},
        "libraries": {"pinned_footprint_libs": [], "pinned_symbol_libs": []},
    }, indent=2) + "\n"
