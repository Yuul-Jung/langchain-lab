import copy
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from edaharness.intent import parse_text  # noqa: E402
from edaharness.synth import synthesize  # noqa: E402

TEXTS = {
    "usb_ldo": "USB-C 5V 입력에서 3.3V LDO로 300mA 출력, 전원 LED 초록색",
    "motor": "12V 입력, 12V 모터 2A를 3.3V MCU로 제어",
    "blink": "9V 입력 LED 2Hz 깜빡이",
    "mix": "USB 입력 LED 1Hz 깜빡이고 전원 LED, 3.3V LDO",
}


def intent(key):
    return parse_text(TEXTS[key])


def ir(key):
    return synthesize(intent(key), key)


def by_role(ir_, block, role):
    for c in ir_["components"].values():
        if c["block"] == block and c["role"] == role:
            return c
    raise KeyError((block, role))


def codes(findings, sev="ERROR"):
    return {f["code"] for f in findings if f["severity"] == sev}


def clone(x):
    return copy.deepcopy(x)


def dump(x):
    return json.dumps(x, ensure_ascii=False)
