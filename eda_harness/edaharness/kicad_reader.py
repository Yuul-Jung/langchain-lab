"""KiCad 스키매틱 리더 + IR 라운드트립 비교 (G5).

writer와 독립적으로 동작한다: 핀 좌표는 파이썬 라이브러리가 아니라
'파일 안에 임베드된 lib_symbols'에서 다시 읽는다. 그래야 writer 버그(좌표 계산,
라벨 위치, 누락 와이어)가 IR과의 불일치로 드러난다.
"""
from __future__ import annotations

from .sexpr import find, find_all, loads

SCALE = 1000  # 좌표를 µm 정수로 비교


def _pt(x, y):
    return (int(round(x * SCALE)), int(round(y * SCALE)))


def _prop(node, name):
    for p in find_all(node, "property"):
        if p[1] == name:
            return str(p[2])
    return None


class _UF:
    def __init__(self):
        self.p = {}

    def find(self, a):
        self.p.setdefault(a, a)
        while self.p[a] != a:
            self.p[a] = self.p[self.p[a]]
            a = self.p[a]
        return a

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[ra] = rb


def _lib_pins(lib_sym):
    pins = []
    for sub in find_all(lib_sym, "symbol"):
        parts = str(sub[1]).rsplit("_", 2)
        unit = int(parts[1]) if len(parts) == 3 and parts[1].isdigit() else 0
        if unit not in (0, 1):
            continue
        for p in find_all(sub, "pin"):
            at = find(p, "at")
            num = find(p, "number")
            pins.append((str(num[1]), float(at[1]), float(at[2])))
    return pins


def _on_segment(p, a, b):
    (px, py), (ax, ay), (bx, by) = p, a, b
    if (bx - ax) * (py - ay) != (by - ay) * (px - ax):
        return False
    return min(ax, bx) <= px <= max(ax, bx) and min(ay, by) <= py <= max(ay, by)


def read_schematic(text: str) -> dict:
    root = loads(text)
    findings = []
    if not root or root[0] != "kicad_sch":
        raise ValueError("kicad_sch 파일이 아님")
    libs = {str(s[1]): _lib_pins(s) for s in find_all(find(root, "lib_symbols") or [], "symbol")}
    uf = _UF()
    comps, nc_points = {}, set()
    pin_nodes = []
    for inst in find_all(root, "symbol"):
        lib_id = str(find(inst, "lib_id")[1])
        at = find(inst, "at")
        sx, sy, rot = float(at[1]), float(at[2]), float(at[3]) if len(at) > 3 else 0.0
        ref = _prop(inst, "Reference")
        if find(inst, "mirror") is not None or rot != 0:
            findings.append({"code": "RT_UNSUPPORTED_TRANSFORM", "severity": "ERROR",
                             "message": f"{ref}: 회전/미러 심볼은 Stage01 리더가 지원하지 않음", "where": ref})
            continue
        if lib_id not in libs:
            findings.append({"code": "RT_LIB_MISSING", "severity": "ERROR",
                             "message": f"{ref}: lib_symbols에 {lib_id} 없음", "where": ref})
            continue
        if ref in comps:
            findings.append({"code": "RT_REF_DUPLICATE", "severity": "ERROR",
                             "message": f"refdes {ref} 중복", "where": ref})
        comps[ref] = {"lib_id": lib_id, "value": _prop(inst, "Value"),
                      "footprint": _prop(inst, "Footprint"), "eda_id": _prop(inst, "EDA_ID")}
        for num, px, py in libs[lib_id]:
            pt = _pt(sx + px, sy - py)
            node = ("pin", ref, num)
            uf.union(node, ("pt", pt))
            pin_nodes.append((node, pt))

    segs = []
    for w in find_all(root, "wire"):
        xys = find_all(find(w, "pts"), "xy")
        a, b = _pt(xys[0][1], xys[0][2]), _pt(xys[-1][1], xys[-1][2])
        uf.union(("pt", a), ("pt", b))
        segs.append((a, b))
    for lab in find_all(root, "label"):
        name = str(lab[1])
        at = find(lab, "at")
        pt = _pt(at[1], at[2])
        uf.union(("label", name), ("pt", pt))
        for a, b in segs:
            if _on_segment(pt, a, b):
                uf.union(("pt", pt), ("pt", a))
    for g in find_all(root, "global_label") + find_all(root, "hierarchical_label"):
        findings.append({"code": "RT_UNSUPPORTED_LABEL", "severity": "ERROR",
                         "message": f"{g[0]} '{g[1]}'은 Stage01 리더 미지원", "where": str(g[1])})
    for nc in find_all(root, "no_connect"):
        at = find(nc, "at")
        nc_points.add(_pt(at[1], at[2]))

    groups: dict = {}
    for key in list(uf.p):
        groups.setdefault(uf.find(key), []).append(key)
    nets, unnamed, nc_pins, unconnected = {}, [], [], []
    for (node, pt) in pin_nodes:
        g = groups[uf.find(node)]
        names = sorted({k[1] for k in g if k[0] == "label"})
        pins_in = [k for k in g if k[0] == "pin"]
        if pt in nc_points:
            if len(pins_in) > 1 or names:
                findings.append({"code": "RT_NC_CONNECTED", "severity": "ERROR",
                                 "message": f"{node[1]}.{node[2]}에 NC 표시가 있는데 연결됨", "where": node[1]})
            nc_pins.append((node[1], node[2]))
            continue
        if not names:
            if len(pins_in) == 1:
                unconnected.append((node[1], node[2]))
            else:
                unnamed.append((node[1], node[2]))
            continue
        if len(names) > 1:
            findings.append({"code": "RT_NET_MULTI_NAME", "severity": "ERROR",
                             "message": f"하나의 넷에 라벨 {names} — 의도치 않은 단락", "where": ",".join(names)})
        nets.setdefault(names[0], set()).add((node[1], node[2]))
    return {"components": comps, "nets": {k: sorted(v) for k, v in nets.items()},
            "nc": sorted(nc_pins), "unconnected": sorted(unconnected),
            "unnamed": sorted(unnamed), "findings": findings}


def compare_with_ir(ir, sch: dict) -> list:
    out = list(sch["findings"])

    def err(code, msg, where=""):
        out.append({"code": code, "severity": "ERROR", "message": msg, "where": where})

    ir_by_ref = {c["ref"]: c for c in ir["components"].values()}
    for ref, c in ir_by_ref.items():
        s = sch["components"].get(ref)
        if s is None:
            err("RT_COMPONENT_MISSING", f"IR의 {ref}가 스키매틱에 없음", ref)
            continue
        if s["lib_id"] != f"eda:{c['part']}":
            err("RT_LIB_ID", f"{ref}: {s['lib_id']} ≠ eda:{c['part']}", ref)
        if s["value"] != c["value"]:
            err("RT_VALUE", f"{ref}: 값 {s['value']} ≠ {c['value']}", ref)
        if (s["footprint"] or "") != c["footprint"]:
            err("RT_FOOTPRINT", f"{ref}: 풋프린트 불일치", ref)
        if s["eda_id"] != c["id"]:
            err("RT_IDENTITY", f"{ref}: EDA_ID {s['eda_id']} ≠ {c['id']}", ref)
    for ref in sch["components"]:
        if ref not in ir_by_ref:
            err("RT_COMPONENT_EXTRA", f"스키매틱에만 있는 {ref}", ref)

    ir_nets: dict = {}
    ir_nc = []
    for c in ir["components"].values():
        for num, net in c["pins"].items():
            ir_nets.setdefault(net, set()).add((c["ref"], num))
        for num in c["no_connect"]:
            ir_nc.append((c["ref"], num))
    for name in sorted(set(ir_nets) | set(sch["nets"])):
        a, b = ir_nets.get(name, set()), set(map(tuple, sch["nets"].get(name, [])))
        if a != b:
            err("RT_NET_MISMATCH",
                f"넷 {name}: IR에만 {sorted(a - b)}, 스키매틱에만 {sorted(b - a)}", name)
    if sorted(ir_nc) != sorted(map(tuple, sch["nc"])):
        err("RT_NC_MISMATCH", f"NC 핀 불일치 IR={sorted(ir_nc)} SCH={sch['nc']}")
    for r, n in sch["unconnected"]:
        err("RT_UNCONNECTED", f"{r}.{n} 스키매틱에서 미연결", r)
    for r, n in sch["unnamed"]:
        err("RT_UNNAMED_NET", f"{r}.{n}가 라벨 없는 넷에 있음", r)
    return out
