"""LibrePCB 라이브러리(.lplib 폴더들)를 읽어 부품 카탈로그(장치 단위)로 만든다.

LibrePCB 라이브러리는 CC0-1.0 이다. 이 모듈은 파일을 '읽기만' 한다 — 원본 폴더를 바꾸지 않는다.
KiCad 카탈로그(kicad_parts.py)와 섞지 않는다: 결과는 별도 파일이고, 모든 항목은 review_status = proposed 이다
(사람이 승인하기 전에는 설계 규칙·부품 추천에 쓰지 않는다).

구조 (LibrePCB 파일 형식, S-표현식이라 kicad_parts._parse_sexpr 로 읽는다 — 특정 도구의 표기에 맞춘 정규식이 아니다)
  dev/<uuid>/device.lp     장치: 이름·설명·키워드·분류·데이터시트 링크·제조사 부품 번호(part)·
                           component(컴포넌트 uuid)·package(패키지 uuid)·pad(패키지 패드 uuid → 컴포넌트 신호 uuid)
  cmp/<uuid>/component.lp  컴포넌트: 신호(uuid · 이름 · 전기 역할)
  pkg/<uuid>/package.lp    패키지: 패드(uuid · 이름 = 핀 번호)
  cmpcat/<uuid>/component_category.lp  분류(이름 · 부모 uuid)
장치는 다른 라이브러리에 있는 컴포넌트·패키지를 참조할 수 있으므로, 모든 라이브러리를 합쳐 uuid 로 찾는다.
"""
from __future__ import annotations

import re
from pathlib import Path

import kicad_parts

REVIEW_STATUS = "proposed"
NO_SIGNAL = "none"      # 패드를 어떤 신호에도 연결하지 않음을 뜻하는 LibrePCB 의 값


def _node_text(node: list, tag: str) -> str:
    """(tag "값") 꼴의 첫 자식. (tag (locale "de") "값") 같은 번역 항목은 건너뛴다. 없으면 빈 문자열."""
    for child in node[1:]:
        if isinstance(child, list) and child and child[0] == tag:
            if len(child) == 2 and isinstance(child[1], str):
                return child[1]
    return ""


def _children(node: list, tag: str) -> list[list]:
    return [c for c in node[1:] if isinstance(c, list) and c and c[0] == tag]


def _first_atom(node: list, tag: str) -> str:
    """(tag 값) 의 첫 값 (예: (component <uuid>))."""
    for child in _children(node, tag):
        if len(child) >= 2 and isinstance(child[1], str):
            return child[1]
    return ""


def _read(path: Path) -> list:
    tree = kicad_parts._parse_sexpr(path.read_text(encoding="utf-8"))
    if not tree or not isinstance(tree[0], list):
        raise ValueError(f"빈 파일 또는 알 수 없는 형식: {path.name}")
    return tree[0]


def _natural_key(value: str):
    return [int(p) if p.isdigit() else p.lower() for p in re.split(r"(\d+)", value)]


class Library:
    """여러 .lplib 폴더를 합친 색인. 읽지 못한 파일은 errors 에 기록하고 건너뛴다(조용히 빠뜨리지 않는다)."""

    def __init__(self):
        self.components: dict[str, dict] = {}
        self.packages: dict[str, dict] = {}
        self.categories: dict[str, dict] = {}
        self.devices: list[dict] = []
        self.errors: list[str] = []

    def add_library(self, root: Path, name: str | None = None, commit: str = "") -> None:
        lib = name or root.name.removesuffix(".lplib")
        self._scan(root, "cmp", "component.lp", lib, self._component)
        self._scan(root, "pkg", "package.lp", lib, self._package)
        self._scan(root, "cmpcat", "component_category.lp", lib, self._category)
        self._scan(root, "dev", "device.lp", lib, lambda node, lib=lib: self._device(node, lib, commit))

    def _scan(self, root: Path, folder: str, filename: str, lib: str, handler) -> None:
        base = root / folder
        if not base.is_dir():
            return
        for path in sorted(base.glob(f"*/{filename}")):
            try:
                handler(_read(path))
            except Exception as exc:          # 한 파일의 문제로 전체를 멈추지 않되, 목록에 남긴다
                self.errors.append(f"{lib}/{folder}/{path.parent.name}: {type(exc).__name__}: {str(exc)[:80]}")

    def _component(self, node: list) -> None:
        uid = node[1]
        signals = {}
        for sig in _children(node, "signal"):
            signals[sig[1]] = {"name": _node_text(sig, "name"), "role": _first_atom(sig, "role") or "passive"}
        self.components[uid] = {"name": _node_text(node, "name"), "description": _node_text(node, "description"),
                                "category": _first_atom(node, "category"), "signals": signals}

    def _package(self, node: list) -> None:
        uid = node[1]
        self.packages[uid] = {"name": _node_text(node, "name"),
                              "pads": {p[1]: _node_text(p, "name") for p in _children(node, "pad")}}

    def _category(self, node: list) -> None:
        self.categories[node[1]] = {"name": _node_text(node, "name"), "parent": _first_atom(node, "parent")}

    def _device(self, node: list, lib: str, commit: str) -> None:
        self.devices.append({"node": node, "library": lib, "commit": commit})

    def category_path(self, uid: str) -> str:
        parts, seen = [], set()
        while uid and uid in self.categories and uid not in seen:
            seen.add(uid)
            parts.append(self.categories[uid]["name"])
            uid = self.categories[uid]["parent"]
        return " > ".join(reversed([p for p in parts if p]))

    def build(self) -> tuple[list[dict], dict]:
        """장치마다 부품 항목을 만든다. 돌려주는 값: (항목 목록, 연결 점검 결과)."""
        entries = []
        report = {"devices": 0, "missing_component": 0, "missing_package": 0, "pads_without_signal_ref": 0,
                  "pads_unresolved": 0, "no_pins": 0, "deprecated": 0, "read_errors": len(self.errors)}
        for item in self.devices:
            node, lib = item["node"], item["library"]
            report["devices"] += 1
            comp = self.components.get(_first_atom(node, "component"))
            pkg = self.packages.get(_first_atom(node, "package"))
            if comp is None:
                report["missing_component"] += 1
            if pkg is None:
                report["missing_package"] += 1
            pins = []
            for pad in _children(node, "pad"):
                pad_name = (pkg or {}).get("pads", {}).get(pad[1])
                sig_uid = _first_atom(pad, "signal")
                if sig_uid == NO_SIGNAL:
                    sig_uid = ""                           # (signal none): 이 패드는 연결 없음으로 명시된 것이다
                signal = (comp or {}).get("signals", {}).get(sig_uid) if sig_uid else None
                if pad_name is None or (sig_uid and signal is None):
                    report["pads_unresolved"] += 1          # 참조한 패드·신호를 찾지 못함: 핀 이름 없이 표시
                if not sig_uid:
                    report["pads_without_signal_ref"] += 1
                pins.append({"number": pad_name if pad_name is not None else "?",
                             "name": signal["name"] if signal else "",
                             "role": signal["role"] if signal else "unconnected"})
            if not pins:
                report["no_pins"] += 1
            pins.sort(key=lambda p: _natural_key(p["number"]))
            parts = _children(node, "part")
            deprecated = _first_atom(node, "deprecated") == "true"
            report["deprecated"] += deprecated
            datasheets = [_first_url(r) for r in _children(node, "resource")]
            category = self.category_path(_first_atom(node, "category")) or (
                self.category_path(comp["category"]) if comp else "")        # 장치에 분류가 없으면 컴포넌트의 분류
            entries.append({
                "id": f"librepcb:{lib}:{node[1]}",
                "source": "librepcb", "library": lib,
                "name": _node_text(node, "name"), "description": _node_text(node, "description"),
                "keywords": [k.strip() for k in _node_text(node, "keywords").split(",") if k.strip()],
                "category": category,
                "component": (comp or {}).get("name", ""), "package": (pkg or {}).get("name", ""),
                "manufacturers": sorted({_first_value(_children(p, "manufacturer")) for p in parts} - {""}),
                "mpns": [p[1] for p in parts if len(p) > 1 and isinstance(p[1], str)],
                "datasheets": [u for u in datasheets if u],
                "pin_count": len(pins), "pins": pins,
                "deprecated": deprecated, "review_status": REVIEW_STATUS, "license": "CC0-1.0",
                "repo_commit": item["commit"],
            })
        return entries, report


def _first_url(resource: list) -> str:
    for child in _children(resource, "url"):
        if len(child) >= 2 and isinstance(child[1], str):
            return child[1]
    return ""


def _first_value(nodes: list[list]) -> str:
    for n in nodes:
        if len(n) >= 2 and isinstance(n[1], str):
            return n[1]
    return ""
