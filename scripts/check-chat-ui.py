#!/usr/bin/env python3
"""채팅 화면을 실제 Chrome(화면 없음)으로 조작해 확인한다 — 읽기 전용, 문서·색인은 바꾸지 않는다.

확인하는 것: 응답 모드 선택 목록(값·기본값), 질문을 보냈을 때 "처리 방식" 표시와 근거 목록이 나오는지, 오류 표시.
출력에는 답 본문을 넣지 않는다(길이만). 질문은 인자로 넘긴다 — 저장소에 문서 내용을 적지 않기 위해서다.

사용: .venv/bin/python scripts/check-chat-ui.py --mode auto --ask "질문1" --ask "질문2"
필요: google-chrome, websockets(.venv 에 있음). 서버(기본 http://127.0.0.1:8000)가 떠 있어야 한다.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

import websockets

PORT = 9333


def http(url: str, method: str = "GET"):
    req = urllib.request.Request(url, method=method)
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode())


class Page:
    def __init__(self, ws):
        self.ws, self.n = ws, 0

    async def call(self, method, **params):
        self.n += 1
        await self.ws.send(json.dumps({"id": self.n, "method": method, "params": params}))
        while True:
            msg = json.loads(await self.ws.recv())
            if msg.get("id") == self.n:
                if "error" in msg:
                    raise RuntimeError(msg["error"])
                return msg["result"]

    async def eval(self, expr: str):
        r = await self.call("Runtime.evaluate", expression=expr, awaitPromise=True, returnByValue=True)
        if "exceptionDetails" in r:
            raise RuntimeError(r["exceptionDetails"].get("text", "js error"))
        return r["result"].get("value")


JS_STATE = """(()=>{const m=document.getElementById('mode');
 return {options:[...m.options].map(o=>o.value+':'+o.text),value:m.value,provider:!!document.getElementById('provider')}})()"""
JS_SEND = """((q,mode)=>{document.getElementById('mode').value=mode;
 document.getElementById('question').value=q;document.getElementById('form').requestSubmit();return true})"""
JS_READ = """(()=>{const c=document.getElementById('chat');
 return [...c.children].map(e=>({cls:e.className,text:e.textContent}))})()"""


async def run(base: str, mode: str, asks: list[str], timeout: int) -> int:
    proc = subprocess.Popen(
        ["google-chrome", "--headless=new", "--no-sandbox", "--disable-gpu", f"--remote-debugging-port={PORT}",
         f"--user-data-dir={tempfile.mkdtemp()}", "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    failed = 0
    try:
        for _ in range(40):
            try:
                tabs = [t for t in http(f"http://127.0.0.1:{PORT}/json/list")
                        if t.get("type") == "page" and not t.get("url", "").startswith("chrome-extension")]
                if tabs:
                    break
            except Exception:
                time.sleep(0.5)
        else:
            print("Chrome 에 연결하지 못했습니다.")
            return 2
        async with websockets.connect(tabs[0]["webSocketDebuggerUrl"], max_size=2**24) as ws:
            page = Page(ws)
            await page.call("Page.enable")
            await page.call("Page.navigate", url=base + "/")
            await asyncio.sleep(2.5)
            state = await page.eval(JS_STATE)
            print("응답 모드 목록:", state["options"], "| 기본값:", state["value"])
            if not state["options"][0].startswith("auto"):
                print("실패: 첫 번째 선택이 자동(auto)이 아닙니다"); failed += 1
            if state["value"] != "auto":
                print("실패: 기본값이 자동(auto)이 아닙니다"); failed += 1
            for q in asks:
                before = len(await page.eval(JS_READ))
                await page.eval(f"({JS_SEND})({json.dumps(q)}, {json.dumps(mode)})")
                deadline = time.time() + timeout
                msgs = []
                while time.time() < deadline:
                    await asyncio.sleep(1.5)
                    msgs = await page.eval(JS_READ)
                    answer = [m for m in msgs[before:] if "assistant" in m["cls"]]
                    if answer and "답변 생성 중" not in answer[-1]["text"] and len(msgs) > before + 1:
                        break
                new = msgs[before:]
                answer = [m for m in new if "assistant" in m["cls"]]
                route = [m["text"] for m in new if "sources" in m["cls"] and m["text"].startswith("처리 방식")]
                shown = [m for m in new if "sources" in m["cls"] and m["text"].startswith("검색 근거")]
                err = bool(answer and answer[-1]["text"].startswith("오류"))
                print(f"질문 {asks.index(q) + 1}: 답 {len(answer[-1]['text']) if answer else 0}자"
                      f" | 처리 방식 줄: {route[0].splitlines()[0] if route else '없음'}"
                      f" | 근거 목록 {('있음 (번호 표기 ' + ('[자료 1]' if '[자료 1]' in shown[0]['text'] else '다름') + ')') if shown else '없음'}"
                      f"{' | 약함 안내 있음' if any('관련이 약합니다' in m['text'] for m in new) else ''}{' | 오류 표시' if err else ''}")
                if err or not route:
                    failed += 1
    finally:
        proc.terminate()
        shutil.rmtree("/tmp/.org.chromium.Chromium.scoped_dir.tmp", ignore_errors=True)
    print("안전: 읽기만 했고 답 본문은 출력하지 않았습니다.")
    return 1 if failed else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="채팅 화면 확인 (읽기 전용)")
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    ap.add_argument("--mode", default="auto", choices=("auto", "rag", "chat"))
    ap.add_argument("--ask", action="append", default=[], help="화면에 입력할 질문 (여러 번 가능)")
    ap.add_argument("--timeout", type=int, default=180)
    args = ap.parse_args()
    return asyncio.run(run(args.base_url, args.mode, args.ask, args.timeout))


if __name__ == "__main__":
    sys.exit(main())
