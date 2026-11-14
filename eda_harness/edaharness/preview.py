"""KiCad 없이 스키매틱을 눈으로 검토하기 위한 SVG 미리보기 (파일만 읽어서 그림)."""
from __future__ import annotations

from html import escape

from .sexpr import find, find_all, loads

S = 4.0  # px per mm


def render_svg(text: str) -> str:
    root = loads(text)
    libs = {str(s[1]): s for s in find_all(find(root, "lib_symbols") or [], "symbol")}
    paper = {"A3": (420, 297), "A2": (594, 420), "A1": (841, 594), "A0": (1189, 841)}.get(
        str(find(root, "paper")[1]), (420, 297))
    W, H = paper[0] * S, paper[1] * S
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W:.0f}" height="{H:.0f}" '
         f'viewBox="0 0 {W:.0f} {H:.0f}" font-family="monospace">',
         f'<rect width="{W:.0f}" height="{H:.0f}" fill="#fffdf6"/>']

    def P(x, y):
        return f"{x * S:.1f}", f"{y * S:.1f}"

    for t in find_all(root, "text"):
        x, y = P(*find(t, "at")[1:3])
        o.append(f'<text x="{x}" y="{y}" font-size="22" fill="#555">{escape(str(t[1]))}</text>')
    for inst in find_all(root, "symbol"):
        lib = libs.get(str(find(inst, "lib_id")[1]))
        at = find(inst, "at")
        sx, sy = float(at[1]), float(at[2])
        props = {str(p[1]): (str(p[2]), p) for p in find_all(inst, "property")}
        if lib is None:
            continue
        for sub in find_all(lib, "symbol"):
            for r in find_all(sub, "rectangle"):
                (x1, y1), (x2, y2) = find(r, "start")[1:3], find(r, "end")[1:3]
                a, b = P(sx + min(x1, x2), sy - max(y1, y2))
                o.append(f'<rect x="{a}" y="{b}" width="{abs(x2 - x1) * S:.1f}" height="{abs(y2 - y1) * S:.1f}" '
                         'fill="#fff3c4" stroke="#8a1c1c" stroke-width="1.5"/>')
            for pl in find_all(sub, "polyline"):
                pts = " ".join(",".join(P(sx + q[1], sy - q[2])) for q in find_all(find(pl, "pts"), "xy"))
                o.append(f'<polyline points="{pts}" fill="none" stroke="#8a1c1c" stroke-width="1.5"/>')
            for pin in find_all(sub, "pin"):
                pa = find(pin, "at")
                ln = float(find(pin, "length")[1])
                dx, dy = {0: (1, 0), 180: (-1, 0), 90: (0, -1), 270: (0, 1)}[int(pa[3])]
                x0, y0 = sx + pa[1], sy - pa[2]
                a, b = P(x0, y0)
                c, d = P(x0 + dx * ln, y0 + dy * ln)
                o.append(f'<line x1="{a}" y1="{b}" x2="{c}" y2="{d}" stroke="#8a1c1c" stroke-width="1.5"/>')
                nm = str(find(pin, "name")[1])
                if nm != "~" and "hide" not in [str(x) for x in (find(lib, "pin_names") or [])]:
                    tx, ty = P(x0 + dx * (ln + 0.6), y0 + dy * (ln + 0.6))
                    anchor = "start" if dx > 0 else "end" if dx < 0 else "middle"
                    o.append(f'<text x="{tx}" y="{ty}" font-size="10" fill="#1b4f8a" text-anchor="{anchor}" '
                             f'dominant-baseline="middle">{escape(nm)}</text>')
        for key, col in (("Reference", "#00666b"), ("Value", "#00666b")):
            if key in props:
                val, node = props[key]
                eff = find(node[1:], "effects") if False else find(node, "effects")
                if eff is not None and "hide" in [str(x) for x in eff]:
                    continue
                a, b = P(*find(node, "at")[1:3])
                o.append(f'<text x="{a}" y="{b}" font-size="13" fill="{col}">{escape(val)}</text>')
    for w in find_all(root, "wire"):
        q = find_all(find(w, "pts"), "xy")
        a, b = P(q[0][1], q[0][2])
        c, d = P(q[-1][1], q[-1][2])
        o.append(f'<line x1="{a}" y1="{b}" x2="{c}" y2="{d}" stroke="#007a00" stroke-width="1.5"/>')
    for lab in find_all(root, "label"):
        at = find(lab, "at")
        a, b = P(at[1], at[2])
        ang = int(at[3])
        anchor = "end" if ang in (180, 270) else "start"
        rot = "" if ang in (0, 180) else f' transform="rotate(-90 {a} {b})"'
        o.append(f'<text x="{a}" y="{b}" font-size="11" fill="#222" text-anchor="{anchor}"{rot}>'
                 f'{escape(str(lab[1]))}</text>')
    for nc in find_all(root, "no_connect"):
        a, b = (float(v) for v in P(*find(nc, "at")[1:3]))
        o.append(f'<path d="M{a - 5},{b - 5}L{a + 5},{b + 5}M{a - 5},{b + 5}L{a + 5},{b - 5}" stroke="#00f"/>')
    o.append("</svg>")
    return "\n".join(o) + "\n"
