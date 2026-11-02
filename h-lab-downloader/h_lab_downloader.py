"""
H Lab Downloader - bulk YouTube downloader for Windows.

Paste any number of video / playlist / channel links, pick a quality and
download everything in the highest quality available, several at a time,
with live progress, speed and ETA for each item.
"""

from __future__ import annotations

import os
import queue
import shutil
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk
import yt_dlp

APP_NAME = "H Lab Downloader"
APP_VERSION = "1.0.0"

# ---------------------------------------------------------------- theme
ACCENT = "#7C5CFF"
ACCENT_HOVER = "#6A48F5"
BG = "#0F1117"
PANEL = "#171A23"
CARD = "#1E2230"
BORDER = "#2A2F40"
TEXT = "#E8EAF2"
MUTED = "#8A90A6"
GREEN = "#2ECC71"
RED = "#FF5C70"
YELLOW = "#F5C451"

QUALITIES = {
    "Best available (up to 8K)": None,
    "4K - 2160p": 2160,
    "1440p": 1440,
    "1080p": 1080,
    "720p": 720,
    "480p": 480,
    "Audio only - MP3 320k": "mp3",
    "Audio only - M4A (original)": "m4a",
}
CONTAINERS = ["MKV (any codec, best)", "MP4"]


# ---------------------------------------------------------------- helpers
def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


def find_ffmpeg() -> str | None:
    """Look for ffmpeg next to the app, then on PATH, then the bundled one."""
    local = app_dir() / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
    if local.exists():
        return str(local)
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def ensure_js_runtime_on_path() -> bool:
    """YouTube needs a JS runtime (Deno) for full-quality formats.
    If deno.exe sits next to the app, put it on PATH so yt-dlp finds it."""
    local = app_dir() / ("deno.exe" if os.name == "nt" else "deno")
    if local.exists():
        os.environ["PATH"] = str(local.parent) + os.pathsep + os.environ.get("PATH", "")
    return shutil.which("deno") is not None


def fmt_bytes(n: float | None) -> str:
    if not n:
        return "-"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}" if unit != "B" else f"{int(n)} B"
        n /= 1024
    return f"{n:.1f} PB"


def fmt_speed(n: float | None) -> str:
    return f"{fmt_bytes(n)}/s" if n else "-"


def fmt_eta(s: float | None) -> str:
    if s is None:
        return "-"
    s = int(s)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m:02d}:{sec:02d}"


class Cancelled(Exception):
    pass


class QuietLogger:
    def __init__(self, sink):
        self.sink = sink

    def debug(self, msg):
        pass

    def info(self, msg):
        pass

    def warning(self, msg):
        self.sink(f"WARN: {msg}")

    def error(self, msg):
        self.sink(msg if msg.startswith("ERROR") else f"ERROR: {msg}")


# ---------------------------------------------------------------- model
@dataclass
class Job:
    url: str
    title: str = "Fetching info..."
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    status: str = "Queued"  # Queued, Downloading, Processing, Done, Failed, Stopped
    progress: float = 0.0
    speed: float | None = None
    eta: float | None = None
    downloaded: float = 0
    total: float | None = None
    error: str = ""


# ---------------------------------------------------------------- engine
class Engine:
    """Runs downloads on worker threads and reports events through a queue."""

    def __init__(self, events: queue.Queue):
        self.events = events
        self.jobs: "queue.Queue[Job | None]" = queue.Queue()
        self.stop_flag = threading.Event()
        self.workers: list[threading.Thread] = []
        self.settings: dict = {}
        self.active = 0
        self.lock = threading.Lock()

    def emit(self, kind, **data):
        self.events.put((kind, data))

    # --- expand playlists / channels into single videos
    def expand(self, urls: list[str]):
        opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": "in_playlist",
            "skip_download": True,
            "ignoreerrors": True,
            "logger": QuietLogger(lambda m: self.emit("log", msg=m)),
        }
        if self.settings.get("cookies"):
            opts["cookiefile"] = self.settings["cookies"]
        seen: set[str] = set()
        with yt_dlp.YoutubeDL(opts) as ydl:
            for url in urls:
                if self.stop_flag.is_set():
                    return
                self.emit("log", msg=f"Reading: {url}")
                try:
                    self._expand_one(ydl, url, seen, depth=0)
                except Exception as e:  # noqa: BLE001
                    self.emit("log", msg=f"ERROR reading {url}: {e}")

    def _expand_one(self, ydl, url, seen, depth):
        info = ydl.extract_info(url, download=False)
        if not info:
            self.emit("log", msg=f"ERROR: could not read {url}")
            return
        entries = info.get("entries")
        if entries is None:
            self._add(info.get("webpage_url") or url, info.get("title"), seen)
            return
        for e in entries:
            if self.stop_flag.is_set():
                return
            if not e:
                continue
            e_url = e.get("url") or e.get("webpage_url")
            if not e_url:
                continue
            # channel pages contain tabs (Videos / Shorts / Live) which are playlists
            if e.get("_type") == "playlist" or (
                e.get("ie_key") == "YoutubeTab" and depth < 2
            ):
                self._expand_one(ydl, e_url, seen, depth + 1)
            else:
                self._add(e_url, e.get("title"), seen)

    def _add(self, url, title, seen):
        if url in seen:
            return
        seen.add(url)
        job = Job(url=url, title=title or url)
        self.emit("added", job=job)
        self.jobs.put(job)

    # --- run
    def start(self, urls: list[str], settings: dict):
        self.stop_flag.clear()
        self.settings = settings
        self.jobs = queue.Queue()

        def runner():
            self.expand(urls)
            n = max(1, int(settings.get("parallel", 3)))
            self.workers = [threading.Thread(target=self._worker, daemon=True) for _ in range(n)]
            for w in self.workers:
                w.start()
            for _ in self.workers:
                self.jobs.put(None)
            for w in self.workers:
                w.join()
            self.emit("finished")

        threading.Thread(target=runner, daemon=True).start()

    def stop(self):
        self.stop_flag.set()

    def _worker(self):
        while True:
            job = self.jobs.get()
            if job is None:
                return
            if self.stop_flag.is_set():
                job.status = "Stopped"
                self.emit("update", job=job)
                continue
            with self.lock:
                self.active += 1
            try:
                self._download(job)
            finally:
                with self.lock:
                    self.active -= 1

    def _build_opts(self, job: Job) -> dict:
        s = self.settings
        q = QUALITIES[s["quality"]]
        out = s["output"]
        tmpl_dir = "%(playlist_title|)s" if s.get("subfolders") else ""
        outtmpl = os.path.join(out, tmpl_dir, "%(title).180B [%(id)s].%(ext)s")

        last = {"t": 0.0}

        def hook(d):
            if self.stop_flag.is_set():
                raise Cancelled()
            st = d.get("status")
            if st == "downloading":
                now = time.monotonic()
                total = d.get("total_bytes") or d.get("total_bytes_estimate")
                done = d.get("downloaded_bytes") or 0
                job.status = "Downloading"
                job.speed = d.get("speed")
                job.eta = d.get("eta")
                job.downloaded = done
                job.total = total
                if total:
                    job.progress = min(done / total, 1.0)
                elif d.get("fragment_count"):
                    job.progress = (d.get("fragment_index") or 0) / d["fragment_count"]
                if now - last["t"] > 0.15:
                    last["t"] = now
                    self.emit("update", job=job)
            elif st == "finished":
                job.progress = 1.0
                job.speed = None
                job.status = "Processing"
                self.emit("update", job=job)

        def pp_hook(d):
            if d.get("status") == "started":
                job.status = "Processing"
                self.emit("update", job=job)

        opts: dict = {
            "outtmpl": outtmpl,
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "logger": QuietLogger(lambda m: self.emit("log", msg=f"[{job.title[:40]}] {m}")),
            "progress_hooks": [hook],
            "postprocessor_hooks": [pp_hook],
            "concurrent_fragment_downloads": int(s.get("fragments", 8)),
            "retries": 15,
            "fragment_retries": 15,
            "continuedl": True,
            "windowsfilenames": True,
            "overwrites": False,
            "noplaylist": True,
            "http_chunk_size": 10 * 1024 * 1024,
        }
        ffmpeg = s.get("ffmpeg")
        if ffmpeg:
            opts["ffmpeg_location"] = ffmpeg
        if s.get("cookies"):
            opts["cookiefile"] = s["cookies"]
        if s.get("archive"):
            opts["download_archive"] = os.path.join(out, "h-lab-archive.txt")

        if q == "mp3":
            opts["format"] = "bestaudio/best"
            opts["postprocessors"] = [
                {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "320"},
                {"key": "FFmpegMetadata"},
            ]
        elif q == "m4a":
            opts["format"] = "bestaudio[ext=m4a]/bestaudio/best"
            opts["postprocessors"] = [
                {"key": "FFmpegExtractAudio", "preferredcodec": "m4a"},
                {"key": "FFmpegMetadata"},
            ]
        else:
            h = f"[height<={q}]" if q else ""
            mp4 = s["container"].startswith("MP4")
            if mp4:
                # prefer formats that play everywhere on Windows, fall back to anything
                opts["format"] = (
                    f"bv*{h}[ext=mp4]+ba[ext=m4a]/bv*{h}+ba/b{h}/bv*+ba/b"
                )
                opts["format_sort"] = ["res", "fps", "vcodec:avc1", "acodec:m4a"]
                opts["merge_output_format"] = "mp4"
            else:
                opts["format"] = f"bv*{h}+ba/b{h}/bv*+ba/b"
                opts["format_sort"] = ["res", "fps", "hdr", "vbr", "abr"]
                opts["merge_output_format"] = "mkv"
            opts["postprocessors"] = [{"key": "FFmpegMetadata"}]
            if s.get("thumbnail"):
                opts["writethumbnail"] = True
                opts["postprocessors"].append({"key": "EmbedThumbnail"})
        return opts

    def _download(self, job: Job):
        job.status = "Downloading"
        self.emit("update", job=job)
        try:
            with yt_dlp.YoutubeDL(self._build_opts(job)) as ydl:
                info = ydl.extract_info(job.url, download=True)
                if info and info.get("title"):
                    job.title = info["title"]
            job.status = "Done"
            job.progress = 1.0
            job.speed = None
            job.eta = 0
        except Cancelled:
            job.status = "Stopped"
            job.speed = None
        except Exception as e:  # noqa: BLE001
            if self.stop_flag.is_set():
                job.status = "Stopped"
            else:
                job.status = "Failed"
                job.error = str(e).replace("ERROR: ", "")[:300]
            job.speed = None
        self.emit("update", job=job)


# ---------------------------------------------------------------- UI pieces
class JobRow(ctk.CTkFrame):
    def __init__(self, master, job: Job):
        super().__init__(master, fg_color=CARD, corner_radius=12, border_width=1, border_color=BORDER)
        self.grid_columnconfigure(0, weight=1)

        self.title = ctk.CTkLabel(self, text=job.title, anchor="w", font=ctk.CTkFont(size=13, weight="bold"), text_color=TEXT)
        self.title.grid(row=0, column=0, sticky="ew", padx=14, pady=(10, 2))
        self.badge = ctk.CTkLabel(self, text=job.status, width=96, corner_radius=8, fg_color=BORDER, text_color=MUTED, font=ctk.CTkFont(size=11, weight="bold"))
        self.badge.grid(row=0, column=1, padx=(6, 14), pady=(10, 2))

        self.bar = ctk.CTkProgressBar(self, height=8, corner_radius=4, progress_color=ACCENT, fg_color=BORDER)
        self.bar.set(0)
        self.bar.grid(row=1, column=0, columnspan=2, sticky="ew", padx=14, pady=4)

        self.info = ctk.CTkLabel(self, text="", anchor="w", text_color=MUTED, font=ctk.CTkFont(size=11))
        self.info.grid(row=2, column=0, columnspan=2, sticky="ew", padx=14, pady=(0, 10))

    def refresh(self, job: Job):
        t = job.title if len(job.title) <= 90 else job.title[:87] + "..."
        self.title.configure(text=t)
        colors = {
            "Downloading": (ACCENT, "#FFFFFF"),
            "Processing": (YELLOW, "#1A1A1A"),
            "Done": (GREEN, "#0B1A10"),
            "Failed": (RED, "#FFFFFF"),
            "Stopped": (BORDER, MUTED),
            "Queued": (BORDER, MUTED),
        }
        bg, fg = colors.get(job.status, (BORDER, MUTED))
        self.badge.configure(text=job.status, fg_color=bg, text_color=fg)
        self.bar.set(job.progress)
        self.bar.configure(progress_color=GREEN if job.status == "Done" else RED if job.status == "Failed" else ACCENT)
        if job.status == "Failed":
            self.info.configure(text=job.error, text_color=RED)
        elif job.status == "Done":
            self.info.configure(text=f"Completed  •  {fmt_bytes(job.total or job.downloaded)}", text_color=GREEN)
        elif job.status == "Processing":
            self.info.configure(text="Merging audio + video / converting...", text_color=YELLOW)
        else:
            self.info.configure(
                text=f"{job.progress*100:5.1f}%   •   {fmt_bytes(job.downloaded)} / {fmt_bytes(job.total)}"
                f"   •   ⚡ {fmt_speed(job.speed)}   •   ETA {fmt_eta(job.eta)}",
                text_color=MUTED,
            )


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        self.title(f"{APP_NAME}  v{APP_VERSION}")
        self.geometry("1180x780")
        self.minsize(960, 640)
        self.configure(fg_color=BG)
        try:
            ico = app_dir() / "assets" / "icon.ico"
            if ico.exists() and os.name == "nt":
                self.iconbitmap(str(ico))
        except Exception:
            pass

        self.events: queue.Queue = queue.Queue()
        self.engine = Engine(self.events)
        self.jobs: dict[str, Job] = {}
        self.rows: dict[str, JobRow] = {}
        self.running = False
        self.ffmpeg = find_ffmpeg()
        self.has_js = ensure_js_runtime_on_path()
        self.output = str(Path.home() / "Downloads" / "H Lab Downloader")
        self.cookies: str | None = None

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._build_sidebar()
        self._build_main()
        self.after(100, self._poll)
        self._startup_checks()

    # ---------------- layout
    def _build_sidebar(self):
        sb = ctk.CTkFrame(self, width=330, fg_color=PANEL, corner_radius=0)
        sb.grid(row=0, column=0, sticky="nsw")
        sb.grid_propagate(False)
        sb.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(sb, text="H LAB", font=ctk.CTkFont(size=30, weight="bold"), text_color=ACCENT).grid(row=0, column=0, sticky="w", padx=22, pady=(24, 0))
        ctk.CTkLabel(sb, text="Bulk Downloader", font=ctk.CTkFont(size=15), text_color=MUTED).grid(row=1, column=0, sticky="w", padx=22, pady=(0, 18))

        def label(r, txt):
            ctk.CTkLabel(sb, text=txt, font=ctk.CTkFont(size=12, weight="bold"), text_color=MUTED).grid(row=r, column=0, sticky="w", padx=22, pady=(10, 4))

        label(2, "QUALITY")
        self.quality = ctk.CTkOptionMenu(sb, values=list(QUALITIES), fg_color=CARD, button_color=ACCENT, button_hover_color=ACCENT_HOVER, dropdown_fg_color=CARD)
        self.quality.grid(row=3, column=0, sticky="ew", padx=22)

        label(4, "CONTAINER")
        self.container = ctk.CTkSegmentedButton(sb, values=CONTAINERS, selected_color=ACCENT, selected_hover_color=ACCENT_HOVER)
        self.container.set(CONTAINERS[0])
        self.container.grid(row=5, column=0, sticky="ew", padx=22)

        label(6, "PARALLEL DOWNLOADS")
        pf = ctk.CTkFrame(sb, fg_color="transparent")
        pf.grid(row=7, column=0, sticky="ew", padx=22)
        pf.grid_columnconfigure(0, weight=1)
        self.parallel_val = ctk.CTkLabel(pf, text="3", width=30, text_color=TEXT)
        self.parallel = ctk.CTkSlider(pf, from_=1, to=10, number_of_steps=9, button_color=ACCENT, progress_color=ACCENT,
                                      command=lambda v: self.parallel_val.configure(text=str(int(v))))
        self.parallel.set(3)
        self.parallel.grid(row=0, column=0, sticky="ew")
        self.parallel_val.grid(row=0, column=1)

        label(8, "SPEED BOOST (connections per video)")
        ff = ctk.CTkFrame(sb, fg_color="transparent")
        ff.grid(row=9, column=0, sticky="ew", padx=22)
        ff.grid_columnconfigure(0, weight=1)
        self.frag_val = ctk.CTkLabel(ff, text="8", width=30, text_color=TEXT)
        self.frags = ctk.CTkSlider(ff, from_=1, to=32, number_of_steps=31, button_color=ACCENT, progress_color=ACCENT,
                                   command=lambda v: self.frag_val.configure(text=str(int(v))))
        self.frags.set(8)
        self.frags.grid(row=0, column=0, sticky="ew")
        self.frag_val.grid(row=0, column=1)

        label(10, "SAVE TO")
        self.out_btn = ctk.CTkButton(sb, text=self._short(self.output), anchor="w", fg_color=CARD, hover_color=BORDER, command=self._pick_folder)
        self.out_btn.grid(row=11, column=0, sticky="ew", padx=22)

        label(12, "OPTIONS")
        self.subfolders = ctk.CTkSwitch(sb, text="Playlist subfolders", progress_color=ACCENT)
        self.subfolders.select()
        self.subfolders.grid(row=13, column=0, sticky="w", padx=22, pady=3)
        self.archive = ctk.CTkSwitch(sb, text="Skip already downloaded", progress_color=ACCENT)
        self.archive.select()
        self.archive.grid(row=14, column=0, sticky="w", padx=22, pady=3)
        self.thumb = ctk.CTkSwitch(sb, text="Embed thumbnail", progress_color=ACCENT)
        self.thumb.grid(row=15, column=0, sticky="w", padx=22, pady=3)

        self.cookie_btn = ctk.CTkButton(sb, text="Cookies.txt (optional)", fg_color=CARD, hover_color=BORDER, command=self._pick_cookies)
        self.cookie_btn.grid(row=16, column=0, sticky="ew", padx=22, pady=(10, 0))

        sb.grid_rowconfigure(17, weight=1)
        self.status_lbl = ctk.CTkLabel(sb, text="", justify="left", anchor="w", font=ctk.CTkFont(size=11), text_color=MUTED, wraplength=290)
        self.status_lbl.grid(row=18, column=0, sticky="ew", padx=22, pady=(0, 18))

    def _build_main(self):
        main = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        main.grid(row=0, column=1, sticky="nsew", padx=20, pady=20)
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(3, weight=1)

        # URL input card
        top = ctk.CTkFrame(main, fg_color=PANEL, corner_radius=14)
        top.grid(row=0, column=0, sticky="ew")
        top.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(top, text="Paste links  —  videos, playlists, channels, Shorts (one per line)",
                     text_color=MUTED, font=ctk.CTkFont(size=12)).grid(row=0, column=0, sticky="w", padx=16, pady=(12, 4))
        self.urls = ctk.CTkTextbox(top, height=130, fg_color=CARD, border_color=BORDER, border_width=1, corner_radius=10, font=ctk.CTkFont(family="Consolas", size=12))
        self.urls.grid(row=1, column=0, sticky="ew", padx=16)

        btns = ctk.CTkFrame(top, fg_color="transparent")
        btns.grid(row=2, column=0, sticky="ew", padx=16, pady=12)
        btns.grid_columnconfigure(3, weight=1)
        ctk.CTkButton(btns, text="Paste", width=90, fg_color=CARD, hover_color=BORDER, command=self._paste).grid(row=0, column=0, padx=(0, 8))
        ctk.CTkButton(btns, text="Import .txt", width=110, fg_color=CARD, hover_color=BORDER, command=self._import).grid(row=0, column=1, padx=(0, 8))
        ctk.CTkButton(btns, text="Clear", width=80, fg_color=CARD, hover_color=BORDER, command=lambda: self.urls.delete("1.0", "end")).grid(row=0, column=2)
        self.stop_btn = ctk.CTkButton(btns, text="■  Stop", width=110, height=38, fg_color=RED, hover_color="#E04A5D", state="disabled", command=self._stop)
        self.stop_btn.grid(row=0, column=4, padx=(0, 8))
        self.start_btn = ctk.CTkButton(btns, text="⬇  Download All", width=170, height=38, fg_color=ACCENT, hover_color=ACCENT_HOVER,
                                       font=ctk.CTkFont(size=14, weight="bold"), command=self._start)
        self.start_btn.grid(row=0, column=5)

        # stats strip
        stats = ctk.CTkFrame(main, fg_color="transparent")
        stats.grid(row=1, column=0, sticky="ew", pady=(16, 8))
        for i in range(4):
            stats.grid_columnconfigure(i, weight=1)
        self.stat_speed = self._stat(stats, 0, "TOTAL SPEED", "0 B/s")
        self.stat_active = self._stat(stats, 1, "ACTIVE", "0")
        self.stat_done = self._stat(stats, 2, "COMPLETED", "0 / 0")
        self.stat_failed = self._stat(stats, 3, "FAILED", "0")

        self.overall = ctk.CTkProgressBar(main, height=6, progress_color=ACCENT, fg_color=BORDER)
        self.overall.set(0)
        self.overall.grid(row=2, column=0, sticky="ew", pady=(0, 10))

        # queue
        self.list = ctk.CTkScrollableFrame(main, fg_color=PANEL, corner_radius=14, label_text="  Download queue", label_anchor="w",
                                           label_fg_color=PANEL, label_text_color=MUTED)
        self.list.grid(row=3, column=0, sticky="nsew")
        self.list.grid_columnconfigure(0, weight=1)
        self.empty = ctk.CTkLabel(self.list, text="No downloads yet — paste some links and hit Download All.", text_color=MUTED)
        self.empty.grid(row=0, column=0, pady=40)

        # log
        bottom = ctk.CTkFrame(main, fg_color="transparent")
        bottom.grid(row=4, column=0, sticky="ew", pady=(10, 0))
        bottom.grid_columnconfigure(0, weight=1)
        self.log = ctk.CTkTextbox(bottom, height=80, fg_color=PANEL, corner_radius=10, text_color=MUTED, font=ctk.CTkFont(family="Consolas", size=11))
        self.log.grid(row=0, column=0, sticky="ew")
        side = ctk.CTkFrame(bottom, fg_color="transparent")
        side.grid(row=0, column=1, padx=(10, 0), sticky="ns")
        ctk.CTkButton(side, text="Open folder", width=120, fg_color=CARD, hover_color=BORDER, command=self._open_folder).pack(pady=(0, 6))
        ctk.CTkButton(side, text="Clear finished", width=120, fg_color=CARD, hover_color=BORDER, command=self._clear_finished).pack(pady=(0, 6))
        ctk.CTkButton(side, text="Retry failed", width=120, fg_color=CARD, hover_color=BORDER, command=self._retry_failed).pack()

    def _stat(self, parent, col, title, value):
        f = ctk.CTkFrame(parent, fg_color=PANEL, corner_radius=12)
        f.grid(row=0, column=col, sticky="ew", padx=(0 if col == 0 else 6, 0 if col == 3 else 6))
        ctk.CTkLabel(f, text=title, text_color=MUTED, font=ctk.CTkFont(size=11, weight="bold")).pack(anchor="w", padx=14, pady=(10, 0))
        v = ctk.CTkLabel(f, text=value, text_color=TEXT, font=ctk.CTkFont(size=22, weight="bold"))
        v.pack(anchor="w", padx=14, pady=(0, 10))
        return v

    # ---------------- actions
    @staticmethod
    def _short(p: str, n: int = 34) -> str:
        return p if len(p) <= n else "..." + p[-(n - 3):]

    def _startup_checks(self):
        msgs = []
        msgs.append("✔ FFmpeg ready" if self.ffmpeg else "✖ FFmpeg not found — 1080p+ merging needs ffmpeg.exe next to the app")
        msgs.append("✔ JS runtime ready" if self.has_js else "⚠ Deno not found — install it (winget install DenoLand.Deno) for all 4K/8K formats")
        msgs.append(f"Engine: yt-dlp {yt_dlp.version.__version__}")
        self.status_lbl.configure(text="\n".join(msgs))

    def _log(self, msg):
        self.log.insert("end", time.strftime("[%H:%M:%S] ") + msg + "\n")
        self.log.see("end")

    def _paste(self):
        try:
            self.urls.insert("end", self.clipboard_get().strip() + "\n")
        except Exception:
            pass

    def _import(self):
        p = filedialog.askopenfilename(filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
        if p:
            self.urls.insert("end", Path(p).read_text(encoding="utf-8", errors="ignore").strip() + "\n")

    def _pick_folder(self):
        p = filedialog.askdirectory(initialdir=self.output)
        if p:
            self.output = p
            self.out_btn.configure(text=self._short(p))

    def _pick_cookies(self):
        p = filedialog.askopenfilename(filetypes=[("Cookies", "*.txt"), ("All files", "*.*")])
        self.cookies = p or None
        self.cookie_btn.configure(text=("Cookies: " + Path(p).name) if p else "Cookies.txt (optional)")

    def _open_folder(self):
        os.makedirs(self.output, exist_ok=True)
        if os.name == "nt":
            os.startfile(self.output)  # type: ignore[attr-defined]
        else:
            import subprocess
            subprocess.Popen(["xdg-open", self.output])

    def _settings(self) -> dict:
        return {
            "quality": self.quality.get(),
            "container": self.container.get(),
            "parallel": int(self.parallel.get()),
            "fragments": int(self.frags.get()),
            "output": self.output,
            "subfolders": bool(self.subfolders.get()),
            "archive": bool(self.archive.get()),
            "thumbnail": bool(self.thumb.get()),
            "cookies": self.cookies,
            "ffmpeg": self.ffmpeg,
        }

    def _start(self, urls: list[str] | None = None):
        if self.running:
            return
        if urls is None:
            raw = self.urls.get("1.0", "end")
            urls = [u.strip() for u in raw.replace(",", "\n").split() if u.strip().startswith(("http", "www", "youtu"))]
        if not urls:
            messagebox.showinfo(APP_NAME, "Paste at least one YouTube link first.")
            return
        os.makedirs(self.output, exist_ok=True)
        self.running = True
        self.start_btn.configure(state="disabled", text="Working...")
        self.stop_btn.configure(state="normal")
        self._log(f"Starting {len(urls)} link(s) → {self.output}")
        self.engine.start(urls, self._settings())

    def _stop(self):
        self.engine.stop()
        self.stop_btn.configure(state="disabled")
        self._log("Stopping... (partial files resume next time)")

    def _clear_finished(self):
        for jid in [j for j, job in self.jobs.items() if job.status in ("Done", "Stopped")]:
            self.rows.pop(jid).destroy()
            self.jobs.pop(jid)
        self._regrid()
        self._update_stats()

    def _retry_failed(self):
        failed = [j for j in self.jobs.values() if j.status in ("Failed", "Stopped")]
        if not failed or self.running:
            return
        urls = [j.url for j in failed]
        for j in failed:
            self.rows.pop(j.id).destroy()
            self.jobs.pop(j.id)
        self._regrid()
        self._start(urls)

    def _regrid(self):
        for i, row in enumerate(self.rows.values()):
            row.grid(row=i, column=0, sticky="ew", padx=8, pady=5)
        if not self.rows:
            self.empty.grid(row=0, column=0, pady=40)

    # ---------------- event loop
    def _poll(self):
        changed = False
        try:
            for _ in range(500):
                kind, data = self.events.get_nowait()
                changed = True
                if kind == "added":
                    job = data["job"]
                    self.empty.grid_forget()
                    self.jobs[job.id] = job
                    row = JobRow(self.list, job)
                    row.grid(row=len(self.rows), column=0, sticky="ew", padx=8, pady=5)
                    self.rows[job.id] = row
                elif kind == "update":
                    job = data["job"]
                    if job.id in self.rows:
                        self.rows[job.id].refresh(job)
                        if job.status == "Failed":
                            self._log(f"Failed: {job.title[:60]} — {job.error}")
                elif kind == "log":
                    self._log(data["msg"])
                elif kind == "finished":
                    self.running = False
                    self.start_btn.configure(state="normal", text="⬇  Download All")
                    self.stop_btn.configure(state="disabled")
                    done = sum(j.status == "Done" for j in self.jobs.values())
                    self._log(f"All finished — {done} completed.")
                    self.bell()
        except queue.Empty:
            pass
        if changed or self.running:
            self._update_stats()
        self.after(200, self._poll)

    def _update_stats(self):
        jobs = list(self.jobs.values())
        speed = sum(j.speed or 0 for j in jobs if j.status == "Downloading")
        active = sum(j.status in ("Downloading", "Processing") for j in jobs)
        done = sum(j.status == "Done" for j in jobs)
        failed = sum(j.status == "Failed" for j in jobs)
        self.stat_speed.configure(text=fmt_speed(speed) if speed else "0 B/s")
        self.stat_active.configure(text=str(active))
        self.stat_done.configure(text=f"{done} / {len(jobs)}")
        self.stat_failed.configure(text=str(failed), text_color=RED if failed else TEXT)
        self.overall.set((sum(j.progress for j in jobs) / len(jobs)) if jobs else 0)


def main():
    if os.name == "nt":
        try:  # crisp text on high-DPI screens
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            pass
    App().mainloop()


if __name__ == "__main__":
    main()
