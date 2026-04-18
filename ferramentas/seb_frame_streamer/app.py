from __future__ import annotations

import base64
import json
import queue
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from urllib.parse import urlparse

from websocket import WebSocket, WebSocketException


DEFAULT_BASE_URL = "http://redsystems.ddns.net:2580"
DEFAULT_SESSION_ID = "debug-matematica"
DEFAULT_VIEW_ID = "window-1"
DEFAULT_TITLE = "Questao de Matematica"
DEFAULT_URL = "https://debug.local/matematica"
DEFAULT_WIDTH = "1280"
DEFAULT_HEIGHT = "720"
DEFAULT_INTERVAL_MS = "1000"


def seb_ws_url(base_url: str) -> str:
    parsed = urlparse(base_url.strip())
    scheme = "wss" if parsed.scheme == "https" else "ws"
    netloc = parsed.netloc or parsed.path
    return f"{scheme}://{netloc.rstrip('/')}/seb-live"


class SebFrameStreamerApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("RED SEB Debug Streamer")
        self.root.geometry("860x620")
        self.root.minsize(760, 560)

        self.image_path = tk.StringVar()
        self.base_url = tk.StringVar(value=DEFAULT_BASE_URL)
        self.session_id = tk.StringVar(value=DEFAULT_SESSION_ID)
        self.view_id = tk.StringVar(value=DEFAULT_VIEW_ID)
        self.title_var = tk.StringVar(value=DEFAULT_TITLE)
        self.url_var = tk.StringVar(value=DEFAULT_URL)
        self.width_var = tk.StringVar(value=DEFAULT_WIDTH)
        self.height_var = tk.StringVar(value=DEFAULT_HEIGHT)
        self.interval_var = tk.StringVar(value=DEFAULT_INTERVAL_MS)
        self.status_var = tk.StringVar(value="Pronto para simular uma sessao SEB real via WebSocket.")

        self.events: queue.Queue[tuple[str, str]] = queue.Queue()
        self.stop_event = threading.Event()
        self.stream_thread: threading.Thread | None = None
        self.current_socket: WebSocket | None = None

        self._build_ui()
        self.root.after(150, self._pump_events)

    def _build_ui(self) -> None:
        self.root.configure(bg="#130404")

        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TFrame", background="#130404")
        style.configure("TLabel", background="#130404", foreground="#f5dfdb")
        style.configure("Header.TLabel", background="#130404", foreground="#ffffff", font=("Segoe UI", 22, "bold"))
        style.configure("Muted.TLabel", background="#130404", foreground="#d7a59b")
        style.configure("TLabelframe", background="#1b0606", foreground="#ffffff")
        style.configure("TLabelframe.Label", background="#1b0606", foreground="#ee4d31", font=("Segoe UI", 10, "bold"))
        style.configure("TEntry", fieldbackground="#250909", foreground="#ffffff")

        outer = ttk.Frame(self.root, padding=18)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(4, weight=1)

        header = ttk.Frame(outer)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="RED SEB Debug Streamer", style="Header.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            header,
            text="Carregue uma imagem local e envie para /seb-live exatamente como se fosse o navegador SEB.",
            style="Muted.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(6, 0))

        target = ttk.LabelFrame(outer, text="Destino e sessao", padding=14)
        target.grid(row=1, column=0, sticky="ew")
        for col in range(4):
            target.columnconfigure(col, weight=1)

        self._labeled_entry(target, "Base URL do monitor", self.base_url, 0, 0, colspan=4)
        self._labeled_entry(target, "Session ID", self.session_id, 1, 0)
        self._labeled_entry(target, "View ID", self.view_id, 1, 1)
        self._labeled_entry(target, "Titulo", self.title_var, 1, 2)
        self._labeled_entry(target, "URL", self.url_var, 1, 3)
        self._labeled_entry(target, "Largura", self.width_var, 2, 0)
        self._labeled_entry(target, "Altura", self.height_var, 2, 1)
        self._labeled_entry(target, "Intervalo (ms)", self.interval_var, 2, 2)

        frame_box = ttk.LabelFrame(outer, text="Frame", padding=14)
        frame_box.grid(row=2, column=0, sticky="ew", pady=(14, 0))
        frame_box.columnconfigure(0, weight=1)

        row = ttk.Frame(frame_box)
        row.grid(row=0, column=0, sticky="ew")
        row.columnconfigure(0, weight=1)
        ttk.Entry(row, textvariable=self.image_path).grid(row=0, column=0, sticky="ew", padx=(0, 8))
        ttk.Button(row, text="Escolher imagem", command=self.choose_image).grid(row=0, column=1)
        ttk.Label(
            frame_box,
            text="Use JPG ou PNG. Para simular mudancas, basta trocar a imagem e manter o stream ligado.",
            style="Muted.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(8, 0))

        actions = ttk.Frame(outer)
        actions.grid(row=3, column=0, sticky="ew", pady=(14, 0))
        ttk.Button(actions, text="Enviar uma vez", command=self.send_once).grid(row=0, column=0, padx=(0, 8), sticky="w")
        ttk.Button(actions, text="Iniciar stream", command=self.start_stream).grid(row=0, column=1, padx=(0, 8), sticky="w")
        ttk.Button(actions, text="Parar stream", command=self.stop_streaming).grid(row=0, column=2, sticky="w")

        status = ttk.LabelFrame(outer, text="Status", padding=14)
        status.grid(row=4, column=0, sticky="nsew", pady=(14, 0))
        status.columnconfigure(0, weight=1)
        status.rowconfigure(1, weight=1)
        ttk.Label(status, textvariable=self.status_var, wraplength=780).grid(row=0, column=0, sticky="ew")
        self.log_box = tk.Text(
            status,
            height=16,
            bg="#180606",
            fg="#f3ddd6",
            insertbackground="#ffffff",
            relief="flat",
            wrap="word",
            padx=10,
            pady=10,
        )
        self.log_box.grid(row=1, column=0, sticky="nsew", pady=(10, 0))
        self.log_box.configure(state="disabled")

    def _labeled_entry(self, parent: ttk.Widget, label: str, variable: tk.StringVar, row: int, column: int, *, colspan: int = 1) -> None:
        ttk.Label(parent, text=label).grid(row=row * 2, column=column, columnspan=colspan, sticky="w", pady=(0, 4), padx=(0, 8))
        ttk.Entry(parent, textvariable=variable).grid(row=row * 2 + 1, column=column, columnspan=colspan, sticky="ew", padx=(0, 8), pady=(0, 10))

    def choose_image(self) -> None:
        filename = filedialog.askopenfilename(
            title="Escolher frame do SEB",
            filetypes=[
                ("Imagens", "*.jpg *.jpeg *.png"),
                ("Todos os arquivos", "*.*"),
            ],
        )
        if filename:
            self.image_path.set(filename)
            self.status_var.set("Imagem carregada. Pronta para envio.")
            self._log("Imagem selecionada: " + filename)

    def _log(self, text: str) -> None:
        self.log_box.configure(state="normal")
        self.log_box.insert("end", text + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _payload(self) -> dict[str, object]:
        image_path = Path(self.image_path.get().strip())
        if not image_path.is_file():
            raise ValueError("Escolha uma imagem valida antes de enviar.")

        try:
            width = max(1, int(self.width_var.get().strip() or "1280"))
            height = max(1, int(self.height_var.get().strip() or "720"))
        except ValueError as exc:
            raise ValueError("Largura, altura e intervalo precisam ser numericos.") from exc

        return {
            "type": "frame",
            "sessionId": self.session_id.get().strip() or DEFAULT_SESSION_ID,
            "application": "SafeExamBrowser",
            "viewId": self.view_id.get().strip() or DEFAULT_VIEW_ID,
            "windowId": 1,
            "isMainWindow": True,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "title": self.title_var.get().strip() or DEFAULT_TITLE,
            "url": self.url_var.get().strip() or DEFAULT_URL,
            "width": width,
            "height": height,
            "imageBase64": base64.b64encode(image_path.read_bytes()).decode("ascii"),
        }

    def _open_ws(self) -> WebSocket:
        ws = WebSocket()
        ws.connect(seb_ws_url(self.base_url.get()))
        return ws

    def _send_payload(self, ws: WebSocket) -> None:
        payload = self._payload()
        ws.send(json.dumps(payload, ensure_ascii=False))
        self.events.put(("status", f"Frame enviada para {payload['sessionId']} / {payload['viewId']}"))
        self.events.put(("log", f"[{time.strftime('%H:%M:%S')}] frame enviada ({len(str(payload['imageBase64']))} chars base64)"))

    def send_once(self) -> None:
        try:
            self._payload()
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("RED SEB Debug Streamer", str(exc))
            return

        self.status_var.set("Enviando frame unica via WebSocket...")

        def worker() -> None:
            ws: WebSocket | None = None
            try:
                ws = self._open_ws()
                self._send_payload(ws)
            except Exception as exc:  # noqa: BLE001
                self.events.put(("error", str(exc)))
            finally:
                if ws is not None:
                    try:
                        ws.close()
                    except Exception:
                        pass

        threading.Thread(target=worker, daemon=True).start()

    def _stream_loop(self, interval_ms: int) -> None:
        ws: WebSocket | None = None
        try:
            ws = self._open_ws()
            self.current_socket = ws
            self.events.put(("status", "Stream ativo no /seb-live."))
            while not self.stop_event.is_set():
                self._send_payload(ws)
                if self.stop_event.wait(interval_ms / 1000):
                    break
        except Exception as exc:  # noqa: BLE001
            self.events.put(("error", str(exc)))
        finally:
            if ws is not None:
                try:
                    ws.close()
                except Exception:
                    pass
            self.current_socket = None
            self.events.put(("status", "Stream parado."))

    def start_stream(self) -> None:
        if self.stream_thread and self.stream_thread.is_alive():
            self.status_var.set("O stream ja esta ativo.")
            return

        try:
            self._payload()
            interval_ms = max(150, int(self.interval_var.get().strip() or "1000"))
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("RED SEB Debug Streamer", str(exc))
            return

        self.stop_event.clear()
        self.stream_thread = threading.Thread(target=self._stream_loop, args=(interval_ms,), daemon=True)
        self.stream_thread.start()

    def stop_streaming(self) -> None:
        self.stop_event.set()
        socket = self.current_socket
        if socket is not None:
            try:
                socket.close()
            except Exception:
                pass
        self.status_var.set("Parando stream...")

    def _pump_events(self) -> None:
        try:
            while True:
                kind, message = self.events.get_nowait()
                if kind == "status":
                    self.status_var.set(message)
                elif kind == "error":
                    self.status_var.set("Erro: " + message)
                    self._log("[erro] " + message)
                else:
                    self._log(message)
        except queue.Empty:
            pass
        finally:
            self.root.after(150, self._pump_events)


def main() -> int:
    root = tk.Tk()
    app = SebFrameStreamerApp(root)
    root.protocol("WM_DELETE_WINDOW", lambda: (app.stop_streaming(), root.destroy()))
    root.mainloop()
    return 0
