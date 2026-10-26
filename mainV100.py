import threading
import tkinter as tk
from collections import deque
from tkinter import ttk, messagebox

import numpy as np
import sounddevice as sd

CANDIDATE_RATES = [48000, 44100]
BLOCKSIZE = 0
LATENCY = 0.05
PREFILL_MS = 60
MAX_BUFFER_MS = 150

BG = "#0f1115"
CARD = "#171a21"
BORDER = "#252a34"
TEXT = "#e6e8ee"
MUTED = "#7d8596"
ACCENT = "#7c5cff"
ACCENT_HOVER = "#9077ff"
GREEN = "#2ee59d"
YELLOW = "#ffd166"
RED = "#ff5c7a"
FONT = "Segoe UI"


class SampleBuffer:
    def __init__(self, samplerate):
        self.chunks = deque()
        self.n = 0
        self.max = int(samplerate * MAX_BUFFER_MS / 1000)
        self.prefill = int(samplerate * PREFILL_MS / 1000)
        self.playing = False
        self.lock = threading.Lock()

    def push(self, x):
        with self.lock:
            self.chunks.append(x)
            self.n += len(x)
            while self.n > self.max:
                self.n -= len(self.chunks.popleft())

    def pull(self, frames):
        with self.lock:
            if not self.playing:
                if self.n < self.prefill:
                    return None
                self.playing = True
            if self.n < frames:
                self.playing = False
                return None
            out = np.empty(frames, np.float32)
            filled = 0
            while filled < frames:
                c = self.chunks[0]
                take = min(len(c), frames - filled)
                out[filled:filled + take] = c[:take]
                filled += take
                if take == len(c):
                    self.chunks.popleft()
                else:
                    self.chunks[0] = c[take:]
            self.n -= frames
            return out


class Bridge:
    def __init__(self):
        self.sr = CANDIDATE_RATES[0]
        self.buffer = SampleBuffer(self.sr)
        self.gain = 1.0
        self.peak = 0.0
        self.col = 0
        self.in_stream = None
        self.out_stream = None

    def _in_callback(self, indata, frames, time_info, status):
        mono = indata[:, self.col].copy() * self.gain
        self.peak = max(self.peak * 0.9, float(np.max(np.abs(mono))))
        self.buffer.push(mono)

    def _out_callback(self, outdata, frames, time_info, status):
        data = self.buffer.pull(frames)
        if data is None:
            outdata[:] = 0
        else:
            outdata[:, 0] = data
            outdata[:, 1] = data

    @staticmethod
    def _find_rate(in_idx, in_ch, out_idx, extra_in=None):
        for sr in CANDIDATE_RATES:
            try:
                sd.check_input_settings(device=in_idx, channels=in_ch, dtype="float32",
                                        samplerate=sr, extra_settings=extra_in)
                sd.check_output_settings(device=out_idx, channels=2, dtype="float32", samplerate=sr)
                return sr
            except sd.PortAudioError:
                continue
        raise RuntimeError("No common sample rate (48000/44100 Hz) found.")

    def start(self, in_dev, channel, out_dev):
        self.stop()
        if channel >= in_dev["max_in"]:
            raise ValueError(f"Channel {channel + 1} does not exist (device has {in_dev['max_in']}).")

        if in_dev["asio"]:
            nch, self.col = 1, 0
            extra = sd.AsioSettings(channel_selectors=[channel])
            self.sr = self._find_rate(in_dev["index"], 1, out_dev, extra)
        else:
            nch, self.col = channel + 1, channel
            extra = None
            self.sr = self._find_rate(in_dev["index"], nch, out_dev)

        self.buffer = SampleBuffer(self.sr)
        self.in_stream = sd.InputStream(
            device=in_dev["index"], channels=nch, samplerate=self.sr,
            blocksize=BLOCKSIZE, dtype="float32", latency=LATENCY,
            extra_settings=extra, callback=self._in_callback,
        )
        self.out_stream = sd.OutputStream(
            device=out_dev, channels=2, samplerate=self.sr,
            blocksize=BLOCKSIZE, dtype="float32", latency=LATENCY,
            callback=self._out_callback,
        )
        self.out_stream.start()
        self.in_stream.start()

    def stop(self):
        for s in (self.in_stream, self.out_stream):
            if s is not None:
                s.stop()
                s.close()
        self.in_stream = self.out_stream = None
        self.buffer = SampleBuffer(self.sr)
        self.peak = 0.0


def list_inputs():
    hostapis = sd.query_hostapis()
    result = []
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] <= 0:
            continue
        api = hostapis[d["hostapi"]]["name"]
        result.append({
            "index": i,
            "name": d["name"],
            "api": api,
            "asio": "ASIO" in api,
            "max_in": d["max_input_channels"],
        })
    result.sort(key=lambda x: (not x["asio"], x["name"]))
    return result


def list_cable_outputs():
    hostapis = sd.query_hostapis()
    found = []
    for i, d in enumerate(sd.query_devices()):
        if d["max_output_channels"] > 0 and "CABLE Input" in d["name"]:
            found.append((i, hostapis[d["hostapi"]]["name"], d["name"]))
    found.sort(key=lambda x: "WASAPI" not in x[1])
    return found


class FlatButton(tk.Canvas):
    def __init__(self, master, text, command, width=180, height=44, color=ACCENT, hover=ACCENT_HOVER):
        super().__init__(master, width=width, height=height, bg=CARD, highlightthickness=0, bd=0, cursor="hand2")
        self.text, self.command = text, command
        self.w, self.h = width, height
        self.color, self.hover = color, hover
        self.bind("<Enter>", lambda e: self._draw(self.hover))
        self.bind("<Leave>", lambda e: self._draw(self.color))
        self.bind("<Button-1>", lambda e: self.command())
        self._draw(color)

    def _draw(self, color):
        self.delete("all")
        r = self.h // 2
        self.create_oval(0, 0, self.h, self.h, fill=color, outline=color)
        self.create_oval(self.w - self.h, 0, self.w, self.h, fill=color, outline=color)
        self.create_rectangle(r, 0, self.w - r, self.h, fill=color, outline=color)
        self.create_text(self.w / 2, self.h / 2, text=self.text, fill="white",
                         font=(FONT, 11, "bold"))

    def set_text(self, text, color=None):
        self.text = text
        self._draw(color or self.color)
        self.color = color or self.color


class LevelMeter(tk.Canvas):
    SEGMENTS = 32

    def __init__(self, master, width=500, height=22):
        super().__init__(master, width=width, height=height, bg=CARD, highlightthickness=0, bd=0)
        self.w, self.h = width, height
        self.level = 0.0
        self.bind("<Configure>", self._on_resize)

    def _on_resize(self, event):
        self.w = event.width
        self.h = event.height
        self._draw()

    def set_level(self, level):
        self.level = level
        self._draw()

    def _draw(self):
        self.delete("all")
        gap = 3
        seg_w = (self.w - gap * (self.SEGMENTS - 1)) / self.SEGMENTS
        lit = int(round(min(1.0, self.level) * self.SEGMENTS))
        for i in range(self.SEGMENTS):
            x = i * (seg_w + gap)
            if i < lit:
                frac = i / self.SEGMENTS
                color = GREEN if frac < 0.7 else (YELLOW if frac < 0.9 else RED)
            else:
                color = BORDER
            self.create_rectangle(x, 0, x + seg_w, self.h, fill=color, outline="")


class App:
    def __init__(self, root):
        self.root = root
        self.bridge = Bridge()
        self.inputs = list_inputs()
        self.outputs = list_cable_outputs()
        self.running = False

        root.title("UAB")
        root.configure(bg=BG)
        root.geometry("600x560")
        root.minsize(520, 520)
        root.resizable(True, True)

        self._style()

        header = tk.Frame(root, bg=BG)
        header.pack(fill="x", padx=28, pady=(24, 8))
        tk.Label(header, text="Universal Audio Bridge by Thilo C.", bg=BG, fg=TEXT,
                 font=(FONT, 18, "bold")).pack(anchor="w")
        tk.Label(header, text="Route your ASIO or WASAPI microphone into a virtual mic for games",
                 bg=BG, fg=MUTED, font=(FONT, 10)).pack(anchor="w", pady=(2, 0))

        card = tk.Frame(root, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
        card.pack(fill="both", expand=True, padx=28, pady=12)
        inner = tk.Frame(card, bg=CARD)
        inner.pack(fill="both", expand=True, padx=22, pady=20)

        self._label(inner, "INPUT DEVICE")
        self.in_box = self._combo(inner, [
            f"{d['name']}   ·   {d['api']}   ·   {d['max_in']} ch" for d in self.inputs])
        if self.inputs:
            self.in_box.current(0)

        row = tk.Frame(inner, bg=CARD)
        row.pack(fill="x", pady=(14, 0))
        left = tk.Frame(row, bg=CARD)
        left.pack(side="left", fill="x", expand=True)
        self._label(left, "CHANNEL")
        self.ch_var = tk.StringVar(value="1")
        spin = ttk.Spinbox(left, from_=1, to=64, textvariable=self.ch_var, width=8, style="Dark.TSpinbox")
        spin.pack(anchor="w", pady=(4, 0), ipady=4)

        self._label(inner, "OUTPUT (VB-CABLE)", top=14)
        self.out_box = self._combo(inner, [f"{name}   ·   {api}" for i, api, name in self.outputs])
        if self.outputs:
            self.out_box.current(0)

        self._label(inner, "VOLUME", top=14)
        vol_row = tk.Frame(inner, bg=CARD)
        vol_row.pack(fill="x", pady=(4, 0))
        self.gain_var = tk.DoubleVar(value=1.0)
        ttk.Scale(vol_row, from_=0.0, to=3.0, variable=self.gain_var, style="Dark.Horizontal.TScale",
                  command=lambda _: self._set_gain()).pack(side="left", fill="x", expand=True)
        self.gain_label = tk.Label(vol_row, text="100%", bg=CARD, fg=TEXT, width=6,
                                   font=(FONT, 10, "bold"))
        self.gain_label.pack(side="left", padx=(12, 0))

        self._label(inner, "LEVEL", top=14)
        self.meter = LevelMeter(inner, width=520)
        self.meter.pack(fill="x", pady=(6, 0))

        footer = tk.Frame(root, bg=BG)
        footer.pack(fill="x", padx=28, pady=(0, 24))
        self.status_dot = tk.Canvas(footer, width=12, height=12, bg=BG, highlightthickness=0)
        self.status_dot.pack(side="left")
        self.dot = self.status_dot.create_oval(1, 1, 11, 11, fill=MUTED, outline="")
        self.status = tk.Label(footer, text="Stopped", bg=BG, fg=MUTED, font=(FONT, 10))
        self.status.pack(side="left", padx=8)
        self.btn = FlatButton(footer, "Start", self.toggle, width=150, height=42)
        self.btn.pack(side="right")

        if not self.inputs:
            messagebox.showwarning("No inputs", "No input devices found.")
        if not self.outputs:
            messagebox.showwarning("VB-CABLE missing",
                                   "VB-CABLE not found. Install it and restart Windows.")

        root.protocol("WM_DELETE_WINDOW", self.on_close)
        self._update_meter()

    def _style(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("Dark.TCombobox", fieldbackground=BG, background=BG, foreground=TEXT,
                        arrowcolor=TEXT, bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER,
                        padding=8)
        style.map("Dark.TCombobox", fieldbackground=[("readonly", BG)], foreground=[("readonly", TEXT)],
                  selectbackground=[("readonly", BG)], selectforeground=[("readonly", TEXT)])
        style.configure("Dark.TSpinbox", fieldbackground=BG, foreground=TEXT, background=BG,
                        arrowcolor=TEXT, bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER,
                        padding=6)
        style.configure("Dark.Horizontal.TScale", background=CARD, troughcolor=BORDER,
                        bordercolor=CARD, lightcolor=ACCENT, darkcolor=ACCENT)
        self.root.option_add("*TCombobox*Listbox.background", BG)
        self.root.option_add("*TCombobox*Listbox.foreground", TEXT)
        self.root.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
        self.root.option_add("*TCombobox*Listbox.font", (FONT, 10))

    def _label(self, parent, text, top=0):
        tk.Label(parent, text=text, bg=CARD, fg=MUTED, font=(FONT, 8, "bold")).pack(
            anchor="w", pady=(top, 4))

    def _combo(self, parent, values):
        box = ttk.Combobox(parent, state="readonly", values=values, style="Dark.TCombobox",
                           font=(FONT, 10))
        box.pack(fill="x", ipady=3)
        return box

    def _set_gain(self):
        g = self.gain_var.get()
        self.bridge.gain = g
        self.gain_label.config(text=f"{int(g * 100)}%")

    def _update_meter(self):
        level = self.bridge.peak
        self.meter.set_level(level)
        self.root.after(30, self._update_meter)

    def _set_state(self, running):
        self.running = running
        if running:
            self.btn.set_text("Stop", color=RED)
            self.status_dot.itemconfig(self.dot, fill=GREEN)
            self.status.config(text=f"Running at {self.bridge.sr} Hz  ·  select “CABLE Output” in-game",
                               fg=TEXT)
        else:
            self.btn.set_text("Start", color=ACCENT)
            self.status_dot.itemconfig(self.dot, fill=MUTED)
            self.status.config(text="Stopped", fg=MUTED)

    def toggle(self):
        if self.running:
            self.bridge.stop()
            self._set_state(False)
            return
        try:
            if not self.inputs or not self.outputs:
                raise RuntimeError("Input device or VB-CABLE is missing.")
            in_dev = self.inputs[self.in_box.current()]
            channel = int(self.ch_var.get()) - 1
            out_idx = self.outputs[self.out_box.current()][0]
            self.bridge.start(in_dev, channel, out_idx)
            self._set_state(True)
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def on_close(self):
        self.bridge.stop()
        self.root.destroy()


if __name__ == "__main__":
    import os
    import sys

    root = tk.Tk()
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    icon_path = os.path.join(base, "icon.ico")
    if os.path.exists(icon_path):
        root.iconbitmap(icon_path)
    App(root)
    root.mainloop()
