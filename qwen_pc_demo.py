#!/usr/bin/env python3
"""Computer-side GLM-4-Flash voice/chat demo with STM32 push-to-talk + on-screen reply bitmap.

Protocol is defined in SPEC.md (V1, @CMD text line) and SPEC_V2.md
(@BTN button events, @DEV resolution handshake, @IMG binary bitmap frame).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Optional

try:
    from local_api_config import FIXED_API_KEY
except ImportError:
    FIXED_API_KEY = ""


API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
VALID_ACTIONS = {"NONE", "FORWARD", "BACK", "LEFT", "RIGHT", "STOP"}
# STM32 side's USART_REC_LEN is 200 bytes for a whole "@CMD:...;TEXT:...\r\n"
# line (see SPEC.md). Leave headroom for the "@CMD:FORWARD;TEXT:" prefix
# and the \r\n terminator; the rest is the GBK-encoded reply budget.
MAX_REPLY_GBK_BYTES = 120

# Must match SPEC_V2.md's STM32-side MAX_IMG_WIDTH / MAX_IMG_BYTES exactly,
# otherwise the firmware silently discards every frame as oversized.
MAX_IMG_WIDTH = 480
MAX_IMG_BYTES = 6144
IMG_AREA_HEIGHT = 80
IMG_MARGIN = 10
DEFAULT_DEV_WIDTH = 320
DEFAULT_DEV_HEIGHT = 240

RECORD_RATE = 16000
RECORD_CHANNELS = 1
RECORD_CHUNK = 1024
MIN_RECORDING_BYTES = 4000  # ~125ms at 16kHz/16-bit mono; shorter is treated as noise

SYSTEM_PROMPT = """你是一个嵌入式设备的语音助手。
请根据用户输入判断是否包含设备动作，并且只返回严格 JSON，不要 Markdown，不要额外文字：
{"action":"NONE|FORWARD|BACK|LEFT|RIGHT|STOP","reply":"给用户看的简短中文回答"}

动作规则：
- 往前、前进、向前走 -> FORWARD
- 往后、后退、倒车 -> BACK
- 向左、左转 -> LEFT
- 向右、右转 -> RIGHT
- 停止、停下、别动 -> STOP
- 没有明确动作的普通聊天 -> NONE

即使用户只说了一个简短的词（如"向前"、"后退"），也要直接当作动作指令执行，
直接返回对应 action 和一句简短确认（如"已经开始向前走了"），
禁止反问、禁止解释这句话是什么意思、禁止输出示例或格式说明。

reply 最多 60 个汉字，不要换行，不要 Emoji，不要 Markdown。"""


@dataclass
class AiResult:
    action: str
    reply: str


class AiClient:
    def __init__(self, api_key: str, model: str, timeout: int = 60) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    def ask(self, question: str) -> AiResult:
        self.messages.append({"role": "user", "content": question})
        body = {
            "model": self.model,
            "messages": self.messages[-11:],
            "temperature": 0.2,
            "max_tokens": 180,
        }
        request = urllib.request.Request(
            API_URL,
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"GLM API HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"无法连接 GLM API: {exc.reason}") from exc

        try:
            payload = json.loads(raw)
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"GLM 返回格式异常: {raw[:500]}") from exc

        result = parse_ai_content(content)
        self.messages.append({"role": "assistant", "content": content})
        return result


ACTION_CONFIRM = {
    "FORWARD": "已经开始向前走了。",
    "BACK": "已经开始向后退了。",
    "LEFT": "已经开始向左转了。",
    "RIGHT": "已经开始向右转了。",
    "STOP": "已经停下了。",
}


def parse_ai_content(content: str) -> AiResult:
    """Parse strict JSON, while tolerating a fenced or plain-text fallback."""
    cleaned = content.strip()
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.IGNORECASE)
    try:
        obj = json.loads(cleaned)
        action = str(obj.get("action", "NONE")).upper().strip()
        reply = str(obj.get("reply", ""))
    except (json.JSONDecodeError, AttributeError):
        action = infer_action(cleaned)
        # The model ignored the "strict JSON only" instruction and rambled
        # instead (e.g. explaining what the action word means). That rambling
        # text is too long for the small on-screen display, so once we've
        # picked an action out of it, show a short confirmation rather than
        # dumping the raw explanation.
        reply = ACTION_CONFIRM.get(action, cleaned)

    if action not in VALID_ACTIONS:
        action = infer_action(reply)
    reply = clean_reply(reply)
    return AiResult(action=action, reply=reply or "我没有听清楚，请再说一次。")


def infer_action(text: str) -> str:
    rules = [
        ("FORWARD", ("往前", "前进", "向前", "前走")),
        ("BACK", ("往后", "后退", "向后", "倒车")),
        ("LEFT", ("向左", "左转", "左边")),
        ("RIGHT", ("向右", "右转", "右边")),
        ("STOP", ("停止", "停下", "别动", "停住")),
    ]
    for action, keywords in rules:
        if any(keyword in text for keyword in keywords):
            return action
    return "NONE"


def clean_reply(text: str) -> str:
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    # A response cut off mid code block (e.g. by max_tokens) leaves a dangling
    # opening fence with no closing "```" -- the pattern above can't match it,
    # so drop everything from that opening fence onward as well.
    text = re.sub(r"```.*$", "", text, flags=re.DOTALL)
    text = re.sub(r"[\r\n\t;]+", " ", text)
    text = re.sub(r"\s{2,}", " ", text).strip()
    text = text.replace("�", "")
    return text


def _truncate_to_gbk_budget(text: str, max_bytes: int) -> str:
    encoded = text.encode("gbk", errors="replace")
    if len(encoded) <= max_bytes:
        return text
    return encoded[:max_bytes].decode("gbk", errors="ignore")


def compute_image_area(dev_width: int, dev_height: int) -> tuple[int, int, int, int]:
    """Bottom-anchored text band, independent of the arrow icon's geometry.

    Sized to always satisfy the STM32 side's MAX_IMG_WIDTH / MAX_IMG_BYTES
    caps (see SPEC_V2.md) for any width in the 240..480px range typical of
    the TFTLCD modules these experiments target.
    """
    width = max(16, min(dev_width - 2 * IMG_MARGIN, MAX_IMG_WIDTH))
    height = IMG_AREA_HEIGHT
    x = IMG_MARGIN
    y = max(0, dev_height - IMG_MARGIN - height)
    return width, height, x, y


def _chinese_font_candidates():
    windir = os.environ.get("WINDIR")
    if not windir:
        return []
    fonts_dir = os.path.join(windir, "Fonts")
    return [os.path.join(fonts_dir, "msyh.ttc"), os.path.join(fonts_dir, "simhei.ttf"),
            os.path.join(fonts_dir, "simsun.ttc")]


def _load_chinese_font(size: int):
    from PIL import ImageFont

    for path in _chinese_font_candidates():
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    raise RuntimeError(
        "找不到可用的中文字体（试过 msyh.ttc/simhei.ttf/simsun.ttc）。"
        "屏幕位图会显示成方块或空白，可以用 --font 指定一个 ttf/ttc 路径。"
    )


def _wrap_text(text: str, font, max_width: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for ch in text:
        candidate = current + ch
        if font.getlength(candidate) > max_width and current:
            lines.append(current)
            current = ch
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def render_reply_bitmap(text: str, width: int, height: int, font_path: Optional[str] = None,
                         font_size: int = 18) -> bytes:
    """Render text into a 1bpp packed bitmap (MSB-first, row-padded to a byte).

    This exact packing is what Image.convert("1").tobytes() already
    produces, so the STM32 side's unpacking code in SPEC_V2.md section 4
    can treat it as a raw byte stream with no extra framing needed.
    """
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("1", (width, height), color=0)
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype(font_path, font_size) if font_path else _load_chinese_font(font_size)

    lines = _wrap_text(text, font, width - 4)
    line_height = font_size + 4
    y = 2
    for line in lines:
        if y + line_height > height:
            break
        draw.text((2, y), line, fill=1, font=font)
        y += line_height

    return img.tobytes()


def render_dialog_bitmap(text: str, action: str, width: int, height: int,
                         font_path: Optional[str] = None) -> bytes:
    """Render dialogue at the top and an optional direction arrow below it."""
    from PIL import Image, ImageDraw

    img = Image.new("1", (width, height), color=0)
    draw = ImageDraw.Draw(img)
    font = __import__("PIL.ImageFont", fromlist=["ImageFont"]).ImageFont.truetype(
        font_path, 18) if font_path else _load_chinese_font(18)
    lines = _wrap_text(text, font, width - 12)
    y = 4
    for line in lines[:3]:
        draw.text((6, y), line, fill=1, font=font)
        y += 22

    if action in {"FORWARD", "BACK", "LEFT", "RIGHT"}:
        cx, cy = width // 2, min(height - 28, max(y + 24, height * 3 // 4))
        half, head, shaft = 24, 14, 5
        if action in {"FORWARD", "BACK"}:
            draw.rectangle((cx-shaft, cy-half, cx+shaft, cy+half), fill=1)
            tip = cy-half-head if action == "FORWARD" else cy+half+head
            base = cy-half+head if action == "FORWARD" else cy+half-head
            draw.polygon((cx, tip, cx-half, base, cx+half, base), fill=1)
        else:
            draw.rectangle((cx-half, cy-shaft, cx+half, cy+shaft), fill=1)
            tip = cx-half-head if action == "LEFT" else cx+half+head
            base = cx-half+head if action == "LEFT" else cx+half-head
            draw.polygon((tip, cy, base, cy-half, base, cy+half), fill=1)
    return img.tobytes()


class SerialLink:
    """Owns the serial port: a writer (thread-safe) plus a background reader
    that dispatches @DEV / @BTN lines from the STM32 side. In mock mode
    (no --port) it just prints what would have been sent and reports a
    fallback resolution so the rest of the pipeline stays testable.
    """

    def __init__(self, port: Optional[str], baudrate: int) -> None:
        self.mock = not port
        self.width: Optional[int] = None
        self.height: Optional[int] = None
        self.on_btn_down = None
        self.on_btn_up = None
        self._write_lock = threading.Lock()
        self._ack_event = threading.Event()
        self._last_ack = None
        self._stop = threading.Event()
        self._serial = None
        self._thread: Optional[threading.Thread] = None

        if self.mock:
            return

        try:
            import serial
        except ImportError as exc:
            raise RuntimeError("缺少 pyserial，请执行: python -m pip install pyserial") from exc
        try:
            self._serial = serial.Serial(port, baudrate, timeout=0.2)
        except serial.SerialException as exc:
            raise RuntimeError(f"打开串口 {port} 失败: {exc}") from exc

        self._thread = threading.Thread(target=self._reader_loop, daemon=True)
        self._thread.start()

    def _reader_loop(self) -> None:
        assert self._serial is not None
        while not self._stop.is_set():
            try:
                raw_line = self._serial.readline()
            except Exception:
                break
            if not raw_line:
                continue
            text = raw_line.decode("ascii", errors="ignore").strip()
            if not text:
                continue
            if text.startswith("@DEV:"):
                self._parse_dev(text)
            elif text in {"OK", "ERR"}:
                self._last_ack = text
                self._ack_event.set()
            elif text == "@BTN:DOWN":
                if self.on_btn_down:
                    self.on_btn_down()
            elif text == "@BTN:UP":
                if self.on_btn_up:
                    self.on_btn_up()

    def _parse_dev(self, text: str) -> None:
        try:
            w_str, h_str = text[len("@DEV:"):].split("x", 1)
            self.width, self.height = int(w_str), int(h_str)
            print(f"[串口] 板子屏幕分辨率: {self.width}x{self.height}")
        except (ValueError, IndexError):
            pass

    def request_dev(self, wait_seconds: float = 1.0) -> None:
        self._write(b"@REQ:DEV\r\n")
        if self.mock:
            return
        deadline = time.monotonic() + wait_seconds
        while self.width is None and time.monotonic() < deadline:
            time.sleep(0.05)

    def _write(self, data: bytes) -> None:
        if self.mock:
            print(f"[模拟串口] {data!r}")
            return
        assert self._serial is not None
        with self._write_lock:
            self._serial.write(data)
            self._serial.flush()

    def send_cmd(self, result: AiResult) -> None:
        # One line per command: the STM32 side (see SPEC.md) buffers a
        # single \r\n-terminated line at a time and drops bytes that
        # arrive before main() clears the previous one, so splitting
        # @CMD and @TEXT across two lines risks losing the second line.
        # The action stays ASCII; the text is GBK to match the STM32
        # font/display examples. This TEXT field is now only an optional
        # debug echo -- the real on-screen answer goes through send_image.
        # STM32 side buffers one line at a time in a 200-byte buffer (see
        # SPEC.md), so this (and only this) path must stay within budget --
        # the bitmap shown via send_image is not affected by this cap.
        text = _truncate_to_gbk_budget(result.reply, MAX_REPLY_GBK_BYTES)
        text_bytes = text.encode("gbk", errors="replace")
        packet = b"@CMD:" + result.action.encode("ascii") + b";TEXT:" + text_bytes + b"\r\n"
        self._write(packet)
        print(f"[串口] 已发送动作 {result.action}")

    def send_image(self, bitmap: bytes, width: int, height: int, x: int, y: int) -> None:
        expected = ((width + 7) // 8) * height
        if len(bitmap) != expected or len(bitmap) > MAX_IMG_BYTES:
            raise ValueError(f"图片数据长度无效: {len(bitmap)}，应为 {expected} 且不超过 {MAX_IMG_BYTES}")
        header = f"@IMG:{width}x{height};LEN:{len(bitmap)};X:{x};Y:{y}\r\n".encode("ascii")
        self._ack_event.clear()
        # The STM32 firmware first receives the line in 1-byte line mode and
        # only switches to the fixed-length image receive mode after main()
        # has handled that line.  Sending header+payload in one UART burst
        # races that switch: the payload is consumed as line-mode bytes and
        # the display later times out/clears.  Give the polling loop time to
        # enter RX_MODE_IMG before starting the payload.
        self._write(header)
        if not self.mock:
            time.sleep(0.12)
        self._write(bitmap)
        if not self.mock:
            if not self._ack_event.wait(2.0):
                raise RuntimeError("等待 STM32 图片确认超时")
            if self._last_ack == "ERR":
                raise RuntimeError("STM32 拒绝了图片帧")
        print(f"[串口] 已发送位图 {width}x{height}，{len(bitmap)} 字节，位置 ({x},{y})")

    def close(self) -> None:
        self._stop.set()
        if self._serial is not None:
            self._serial.close()


class PushToTalkRecorder:
    """Streams raw PCM from the microphone between start()/stop() calls,
    i.e. for as long as the physical button is held -- unlike
    speech_recognition's Microphone.listen(), which needs a fixed timeout
    decided in advance.
    """

    def __init__(self) -> None:
        self._pyaudio = None
        self._stream = None
        self._frames: list[bytes] = []

    def start(self) -> None:
        try:
            import pyaudio
        except ImportError as exc:
            raise RuntimeError("缺少 pyaudio，请执行: python -m pip install pyaudio") from exc

        self._frames = []
        self._pyaudio = pyaudio.PyAudio()
        self._stream = self._pyaudio.open(
            format=pyaudio.paInt16,
            channels=RECORD_CHANNELS,
            rate=RECORD_RATE,
            input=True,
            frames_per_buffer=RECORD_CHUNK,
            stream_callback=self._on_audio,
        )
        self._stream.start_stream()

    def _on_audio(self, in_data, frame_count, time_info, status):
        import pyaudio

        self._frames.append(in_data)
        return (None, pyaudio.paContinue)

    def stop(self) -> bytes:
        if self._stream is not None:
            self._stream.stop_stream()
            self._stream.close()
            self._stream = None
        if self._pyaudio is not None:
            self._pyaudio.terminate()
            self._pyaudio = None
        return b"".join(self._frames)


def recognize_recorded_audio(raw_pcm: bytes) -> str:
    import speech_recognition as sr

    audio = sr.AudioData(raw_pcm, RECORD_RATE, 2)
    recognizer = sr.Recognizer()
    try:
        return recognizer.recognize_google(audio, language="zh-CN")
    except sr.UnknownValueError as exc:
        raise RuntimeError("没有识别出清晰的语音") from exc
    except sr.RequestError as exc:
        raise RuntimeError(f"语音识别服务不可用: {exc}") from exc


def recognize_from_microphone() -> str:
    """Keyboard-mode fallback: one-shot fixed-timeout mic capture, used
    when there is no board/button in the loop (e.g. --mic without --port).
    """
    try:
        import speech_recognition as sr
    except ImportError as exc:
        raise RuntimeError("麦克风模式需要额外安装 SpeechRecognition 和 PyAudio。") from exc

    recognizer = sr.Recognizer()
    with sr.Microphone() as source:
        print("请说话，正在录音...")
        recognizer.adjust_for_ambient_noise(source, duration=0.3)
        audio = recognizer.listen(source, timeout=8, phrase_time_limit=10)
    try:
        text = recognizer.recognize_google(audio, language="zh-CN")
    except sr.UnknownValueError as exc:
        raise RuntimeError("没有识别出清晰的语音") from exc
    except sr.RequestError as exc:
        raise RuntimeError(f"语音识别服务不可用: {exc}") from exc
    print(f"[识别结果] {text}")
    return text


def ask_and_display(question: str, client: AiClient, link: SerialLink, font_path: Optional[str]) -> None:
    try:
        result = client.ask(question)
    except RuntimeError as exc:
        print(f"请求失败: {exc}")
        return

    print(f"GLM: {result.reply}")
    print(f"动作: {result.action}")
    screen_width = link.width or DEFAULT_DEV_WIDTH
    screen_height = link.height or DEFAULT_DEV_HEIGHT
    width = min(screen_width, MAX_IMG_WIDTH)
    max_height = max(1, (MAX_IMG_BYTES * 8) // max(1, width))
    height = min(screen_height, max_height)
    x = (screen_width - width) // 2
    y = (screen_height - height) // 2
    try:
        bitmap = render_dialog_bitmap(result.reply, result.action, width, height, font_path)
    except RuntimeError as exc:
        print(f"渲染位图失败: {exc}")
        return
    link.send_image(bitmap, width, height, x, y)

def run_push_to_talk(client: AiClient, link: SerialLink, font_path: Optional[str]) -> None:
    recorder = PushToTalkRecorder()
    recording = threading.Event()

    def handle_turn(raw_pcm: bytes) -> None:
        if len(raw_pcm) < MIN_RECORDING_BYTES:
            print("[按键] 录音太短，忽略。")
            return
        try:
            question = recognize_recorded_audio(raw_pcm)
        except RuntimeError as exc:
            print(f"[按键] 识别失败: {exc}")
            return
        print(f"[识别结果] {question}")
        ask_and_display(question, client, link, font_path)

    def on_down() -> None:
        if recording.is_set():
            return
        recording.set()
        print("\n[按键] KEY0 按下，开始录音...")
        try:
            recorder.start()
        except RuntimeError as exc:
            print(f"[按键] 录音启动失败: {exc}")
            recording.clear()

    def on_up() -> None:
        if not recording.is_set():
            return
        recording.clear()
        print("[按键] KEY0 松开，识别中...")
        raw_pcm = recorder.stop()
        # Runs the network calls (speech recognition + GLM) off the serial
        # reader thread so a quick next press isn't missed while we wait.
        threading.Thread(target=handle_turn, args=(raw_pcm,), daemon=True).start()

    link.on_btn_down = on_down
    link.on_btn_up = on_up

    print("等待按住开发板 KEY0 说话（Ctrl+C 退出）...")
    try:
        while True:
            time.sleep(0.2)
    except KeyboardInterrupt:
        print()


def run_keyboard_loop(client: AiClient, link: SerialLink, font_path: Optional[str], use_mic: bool) -> None:
    print("输入问题后回车；输入 /mic 使用麦克风；输入 /quit 退出。")
    while True:
        try:
            question = recognize_from_microphone() if use_mic else input("\n你: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        except RuntimeError as exc:
            print(f"输入失败: {exc}")
            continue

        if not question:
            continue
        if question.lower() in {"/quit", "/exit", "quit", "exit"}:
            break
        if question.lower() == "/mic":
            try:
                question = recognize_from_microphone()
            except RuntimeError as exc:
                print(f"输入失败: {exc}")
                continue

        ask_and_display(question, client, link, font_path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="电脑端 GLM-4-Flash 对话和 STM32 串口测试程序")
    parser.add_argument("--port", help="串口，例如 COM5；不填则使用模拟串口")
    parser.add_argument("--baud", type=int, default=115200, help="串口波特率，默认 115200")
    parser.add_argument("--mic", action="store_true", help="键盘模式下使用电脑麦克风输入（一次性，非按键触发）")
    parser.add_argument("--keyboard", action="store_true",
                         help="即使连了 --port，也用键盘输入代替开发板按键（调试用）")
    parser.add_argument("--font", help="中文字体文件路径（ttf/ttc），默认自动找 Windows 系统字体")
    parser.add_argument("--model", default=os.getenv("GLM_MODEL", "glm-4-flash"))
    parser.add_argument("--api-key", default=os.getenv("BIGMODEL_API_KEY") or FIXED_API_KEY)
    return parser


def main() -> int:
    # Windows consoles often default stdio to the system codepage (e.g. GBK)
    # instead of UTF-8, which garbles Chinese text and corrupts input().
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                pass

    args = build_parser().parse_args()
    if not args.api_key:
        print("未找到 API Key。请先设置环境变量 BIGMODEL_API_KEY。", file=sys.stderr)
        print("PowerShell 示例: $env:BIGMODEL_API_KEY='你的Key'", file=sys.stderr)
        return 2

    try:
        client = AiClient(args.api_key, args.model)
        link = SerialLink(args.port, args.baud)
    except RuntimeError as exc:
        print(f"启动失败: {exc}", file=sys.stderr)
        return 2

    print(f"GLM 模型: {args.model}")
    print("串口: " + (args.port or "模拟模式"))

    if not link.mock:
        link.request_dev()

    try:
        if args.port and not args.keyboard:
            run_push_to_talk(client, link, args.font)
        else:
            run_keyboard_loop(client, link, args.font, args.mic)
    finally:
        link.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

