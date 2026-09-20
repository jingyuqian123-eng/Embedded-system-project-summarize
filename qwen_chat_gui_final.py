import queue
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageTk

from qwen_pc_demo import (
    AiClient, AiResult, SerialLink, PushToTalkRecorder,
    recognize_from_microphone, recognize_recorded_audio,
)
from local_api_config import FIXED_API_KEY
from local_queries import local_answer

# 1bpp payload must stay within STM32 MAX_IMG_BYTES=6144.
# 320 * 152 / 8 = 6080 bytes.
WIDTH, HEIGHT = 320, 152


def load_font(size=18):
    windir = Path(__import__("os").environ.get("WINDIR", "C:/Windows"))
    candidates = [
        windir / "Fonts" / "msyh.ttc",
        windir / "Fonts" / "msyh.ttf",
        windir / "Fonts" / "simhei.ttf",
        windir / "Fonts" / "simsun.ttc",
    ]
    for path in candidates:
        if path.exists():
            try:
                return ImageFont.truetype(str(path), size)
            except OSError:
                pass
    raise RuntimeError("未找到中文字体，请确认 Windows 已安装微软雅黑、黑体或宋体")


def render_dialog(question, answer, action, width=WIDTH, height=HEIGHT):
    image = Image.new("1", (width, height), 0)
    draw = ImageDraw.Draw(image)
    font = load_font(18)

    lines, line = [], ""
    for ch in "我：" + question + "\n助手：" + answer:
        if ch == "\n":
            if line: lines.append(line)
            line = ""
        elif draw.textlength(line + ch, font=font) > width - 16 and line:
            lines.append(line); line = ch
        else:
            line += ch
    if line: lines.append(line)

    arrow_actions = {"FORWARD", "BACK", "LEFT", "RIGHT"}
    if action in arrow_actions:
        # Reserve a real bottom band for the icon.  The old fixed-size icon
        # could reach up into the second text line on short displays (for
        # example a 320x90 panel), so its size and text area are calculated
        # together.
        arrow_target_height = min(72, max(30, height // 3))
        max_lines = max(1, min(len(lines), (height - arrow_target_height - 9) // 23))
    else:
        max_lines = max(1, min(len(lines), (height - 5) // 23))
    for i, value in enumerate(lines[:max_lines]):
        draw.text((8, 5 + i * 23), value, fill=1, font=font)

    if action in arrow_actions:
        text_bottom = 5 + max_lines * 23
        arrow_top = max(text_bottom + 4, height - arrow_target_height - 4)
        arrow_bottom = height - 4
        arrow_height = arrow_bottom - arrow_top
        # A very short image cannot fit both text and an icon. In that case
        # keep the text clean instead of drawing an icon over it.
        if arrow_height >= 12:
            arrow_width = min(96, max(24, width - 16))
            left = (width - arrow_width) // 2
            right = left + arrow_width - 1
            top, bottom = arrow_top, arrow_bottom
            cx, cy = (left + right) // 2, (top + bottom) // 2

            if action in {"FORWARD", "BACK"}:
                head = max(4, min(16, arrow_height // 3))
                half = max(4, min(28, (arrow_height - head) // 2))
                shaft = max(2, min(6, half // 4))
                if action == "FORWARD":
                    draw.rectangle((cx - shaft, top + head, cx + shaft, bottom), fill=1)
                    draw.polygon((cx, top, cx - half, top + head, cx + half, top + head), fill=1)
                else:
                    draw.rectangle((cx - shaft, top, cx + shaft, bottom - head), fill=1)
                    draw.polygon((cx, bottom, cx - half, bottom - head, cx + half, bottom - head), fill=1)
            else:
                half = max(4, min(28, arrow_height // 2))
                head = max(4, min(16, arrow_width // 5))
                shaft = max(2, min(6, half // 4))
                if action == "LEFT":
                    draw.rectangle((left + head, cy - shaft, right, cy + shaft), fill=1)
                    draw.polygon((left, cy, left + head, cy - half, left + head, cy + half), fill=1)
                else:
                    draw.rectangle((left, cy - shaft, right - head, cy + shaft), fill=1)
                    draw.polygon((right, cy, right - head, cy - half, right - head, cy + half), fill=1)
    return image


def find_port():
    try:
        from serial.tools import list_ports
        ports = list(list_ports.comports())
        if not ports:
            return None
        hints = ("stm", "ch340", "cp210", "ftdi", "usb serial", "uart", "jlink", "st-link")
        ranked = sorted(ports, key=lambda p: (
            not any(h in ((p.description or "") + " " + (p.manufacturer or "")).lower()
                    for h in hints), p.device))
        return ranked[0].device
    except ImportError:
        return None


class App:
    def __init__(self, root):
        self.root = root
        root.title("STM32 语音对话上位机")
        root.geometry("900x620")
        self.events = queue.Queue()
        self.client = AiClient(FIXED_API_KEY, "glm-4-flash")
        self.recorder = PushToTalkRecorder()
        self.recording = False
        self.busy = False
        self.link = None

        body = ttk.Frame(root, padding=10); body.pack(fill="both", expand=True)
        self.log = scrolledtext.ScrolledText(body, width=50, state="disabled")
        self.log.pack(side="left", fill="both", expand=True)
        right = ttk.Frame(body, padding=(12, 0, 0, 0)); right.pack(side="right", fill="y")
        ttk.Label(right, text="STM32 屏幕预览").pack()
        self.preview = ttk.Label(right); self.preview.pack(pady=12)
        self.status = ttk.Label(right, text="正在寻找 STM32 串口..."); self.status.pack()
        bottom = ttk.Frame(root, padding=10); bottom.pack(fill="x")
        self.entry = ttk.Entry(bottom); self.entry.pack(side="left", fill="x", expand=True)
        self.entry.bind("<Return>", lambda _: self.send_text())
        ttk.Button(bottom, text="发送文字", command=self.send_text).pack(side="left", padx=5)
        ttk.Button(bottom, text="电脑麦克风", command=self.voice).pack(side="left")

        self.connect_serial()
        self.poll()

    def write(self, value):
        self.log.configure(state="normal"); self.log.insert("end", value + "\n")
        self.log.see("end"); self.log.configure(state="disabled")

    def connect_serial(self):
        port = find_port()
        if not port:
            self.status.configure(text="未找到 STM32 串口"); return
        try:
            self.link = SerialLink(port, 115200)
            self.link.on_btn_down = self.on_down
            self.link.on_btn_up = self.on_up
            self.link.request_dev()
            self.status.configure(text=f"已连接 {port}，等待 KEY0")
            self.write(f"串口已连接：{port}")
        except Exception as exc:
            self.status.configure(text="串口连接失败")
            self.write("串口错误：" + str(exc))

    def on_down(self):
        if self.recording or self.busy: return
        self.recording = True; self.status.configure(text="KEY0 按下，正在录音...")
        try: self.recorder.start()
        except Exception as exc:
            self.recording = False; self.write("录音错误：" + str(exc))

    def on_up(self):
        if not self.recording: return
        self.recording = False; raw = self.recorder.stop()
        self.status.configure(text="录音结束，正在识别...")
        threading.Thread(target=self.process_audio, args=(raw,), daemon=True).start()

    def process_audio(self, raw):
        try:
            question = recognize_recorded_audio(raw)
            self.events.put(("question", question))
            self.ask(question)
        except Exception as exc: self.events.put(("error", str(exc)))

    def voice(self):
        if self.busy: return
        threading.Thread(target=self.voice_worker, daemon=True).start()

    def voice_worker(self):
        try:
            question = recognize_from_microphone()
            self.events.put(("question", question))
            self.ask(question)
        except Exception as exc: self.events.put(("error", str(exc)))

    def send_text(self):
        question = self.entry.get().strip()
        if question and not self.busy:
            self.entry.delete(0, "end")
            self.write("我：" + question)
            threading.Thread(target=self.ask, args=(question,), daemon=True).start()

    def ask(self, question):
        self.busy = True
        try:
            answer = local_answer(question)
            result = AiResult("NONE", answer) if answer else self.client.ask(question)
            screen_width = self.link.width if self.link and self.link.width else WIDTH
            screen_height = self.link.height if self.link and self.link.height else HEIGHT
            image_width = min(screen_width, 480)
            image_height = min(screen_height, (6144 * 8) // image_width)
            image = render_dialog(question, result.reply, result.action,
                                  image_width, image_height)
            self.events.put(("result", question, result, image))
            if self.link:
                self.link.send_image(image.tobytes(), image_width, image_height, 0, 0)
        except Exception as exc: self.events.put(("error", str(exc)))

    def poll(self):
        try:
            while True:
                event = self.events.get_nowait()
                if event[0] == "question": self.write("我：" + event[1])
                elif event[0] == "result":
                    _, question, result, image = event
                    self.write("助手：" + result.reply); self.write("动作：" + result.action)
                    rgb = image.convert("RGB"); rgb.thumbnail((420, 420))
                    self.photo = ImageTk.PhotoImage(rgb); self.preview.configure(image=self.photo)
                    self.status.configure(text="已发送到 STM32" if self.link else "未连接 STM32")
                    self.busy = False
                elif event[0] == "error": self.write("错误：" + event[1]); self.busy = False
        except queue.Empty: pass
        self.root.after(100, self.poll)


if __name__ == "__main__":
    root = tk.Tk(); App(root); root.mainloop()
