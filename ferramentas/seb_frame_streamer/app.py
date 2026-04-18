from __future__ import annotations

import base64
import queue
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

import requests


DEFAULT_BASE_URL = "http://redsystems.ddns.net:2580"
DEFAULT_SESSION_ID = "debug-matematica"
DEFAULT_VIEW_ID = "main-window"
DEFAULT_TITLE = "Questao de Matematica"
DEFAULT_URL = "https://debug.local/matematica"
DEFAULT_WIDTH = "1280"
DEFAULT_HEIGHT = "720"
DEFAULT_INTERVAL_MS = "1000"


class SebFrameStreamerApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("RED SEB Debug Streamer")
        self.root.geometry("860x640")
        self.root.minsize(760, 560)

        self.image_path = tk.StringVar()
        self.base_url = tk.StringVar(value=DEFAULT_BASE_URL)
        self.debug_token = tk.StringVar()
        self.session_id = tk.StringVar(value=DEFAULT_SESSION_ID)
        self.view_id = tk.StringVar(value=DEFAULT_VIEW_ID)
        self.title_var = tk.StringVar(value=DEFAULT_TITLE)
        self.url_var = tk.StringVar(value=DEFAULT_URL)
        self.width_var = tk.StringVar(value=DEFAULT_WIDTH)
        self.height_var = tk.StringVar(value=DEFAULT_HEIGHT)
        self.interval_var = tk.StringVar(value=DEFAULT_INTERVAL_MS)
        self.status_var = tk.StringVar(value="Pronto para enviar uma sessao fake ao SEB Monitor.")

        self.events: queue.Queue[tuple[str, str]] = queue.Queue()
        self.stream_thread: threading.Thread | None = None
        self.stop_event = threading.Event()

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
        style.configure("Accent.TButton", background="#db2315", foreground="#ffffff")

        outer = ttk.Frame(self.root, padding=18)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)

        header = ttk.Frame(outer)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="RED SEB Debug Streamer", style="Header.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            header,
            text="Carregue uma JPG do seu PC e publique a frame no monitor como uma sessao SEB de teste.",
            style="Muted.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(6, 0))

        top = ttk.LabelFrame(outer, text="Destino e sessao", padding=14)
        top.grid(row=1, column=0, sticky="ew")
        for col in range(4):
            top.columnconfigure(col, weight=1)

        self._labeled_entry(top, "Base URL do SEB", self.base_url, 0, 0, colspan=3)
        self._labeled_entry(top, "Token debug", self.debug_token, 0, 3, show="*")
        self._labeled_entry(top, "Session ID", self.session_id, 1, 0)
        self._labeled_entry(top, "View ID", self.view_id, 1, 1)
        self._labeled_entry(top, "Titulo", self.title_var, 1, 2)
        self._labeled_entry(top, "URL", self.url_var, 1, 3)
        self._labeled_entry(top, "Largura", self.width_var, 2, 0)
        self._labeled_entry(top, "Altura", self.height_var, 2, 1)
        self._labeled_entry(top, "Intervalo (ms)", self.interval_var, 2, 2)

        image_box = ttk.LabelFrame(outer, text="Frame", padding=14)
        image_box.grid(row=2, column=0, sticky="ew", pady=(14, 0))
        image_box.columnconfigure(0, weight=1)

        image_row = ttk.Frame(image_box)
        image_row.grid(row=0, column=0, sticky="ew")
        image_row.columnconfigure(0, weight=1)
        image_entry = ttk.Entry(image_row, textvariable=self.image_path)
        image_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        ttk.Button(image_row, text="Escolher JPG", command=self.choose_image).grid(row=0, column=1)
        ttk.Label(
            image_box,
            text="Dica: voce pode reaproveitar a mesma sessao e trocar a imagem quantas vezes quiser.",
            style="Muted.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(8, 0))

        actions = ttk.Frame(outer)
        actions.grid(row=3, column=0, sticky="ew", pady=(14, 0))
        actions.columnconfigure(0, weight=1)
        ttk.Button(actions, text="Enviar uma vez", command=self.send_once).grid(row=0, column=0, padx=(0, 8), sticky="w")
        ttk.Button(actions, text="Iniciar stream", command=self.start_stream).grid(row=0, column=1, padx=(0, 8), sticky="w")
        ttk.Button(actions, text="Parar stream", command=self.stop_streaming).grid(row=0, column=2, padx=(0, 8), sticky="w")
        ttk.Button(actions, text="Limpar sessao fake", command=self.clear_session).grid(row=0, column=3, sticky="w")

        status = ttk.LabelFrame(outer, text="Status", padding=14)
        status.grid(row=4, column=0, sticky="nsew", pady=(14, 0))
        outer.rowconfigure(4, weight=1)
        status.columnconfigure(0, weight=1)
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
        status.rowconfigure(1, weight=1)
        self.log_box.configure(state="disabled")

    def _labeled_entry(
        self,
        parent: ttk.Widget,
        label: str,
        variable: tk.StringVar,
        row: int,
        column: int,
        *,
        colspan: int = 1,
        show: str | None = None,
    ) -> None:
        ttk.Label(parent, text=label).grid(row=row * 2, column=column, columnspan=colspan, sticky="w", pady=(0, 4), padx=(0, 8))
        entry = ttk.Entry(parent, textvariable=variable, show=show or "")
        entry.grid(row=row * 2 + 1, column=column, columnspan=colspan, sticky="ew", padx=(0, 8), pady=(0, 10))

    def choose_image(self) -> None:
        filename = filedialog.askopenfilename(
            title="Escolher frame do SEB",
            filetypes=[
                ("Imagens JPEG", "*.jpg *.jpeg"),
                ("Imagens PNG", "*.png"),
                ("Todos os arquivos", "*.*"),
            ],
        )
        if filename:
            self.image_path.set(filename)
            self.status_var.set("Imagem carregada. Pode enviar uma vez ou iniciar o stream.")
            self._log("Imagem selecionada: " + filename)

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        token = self.debug_token.get().strip()
        if token:
            headers["x-red-seb-debug-token"] = token
        return headers

    def _payload(self) -> dict[str, Any]:
        image_path = Path(self.image_path.get().strip())
        if not image_path.is_file():
            raise ValueError("Escolha uma imagem valida antes de enviar.")

        try:
            width = max(1, int(self.width_var.get().strip() or "1280"))
            height = max(1, int(self.height_var.get().strip() or "720"))
        except ValueError as exc:
            raise ValueError("Largura, altura e intervalo precisam ser numericos.") from exc

        image_bytes = image_path.read_bytes()
        image_base64 = base64.b64encode(image_bytes).decode("ascii")

        return {
            "sessionId": self.session_id.get().strip() or DEFAULT_SESSION_ID,
            "viewId": self.view_id.get().strip() or DEFAULT_VIEW_ID,
            "title": self.title_var.get().strip() or DEFAULT_TITLE,
            "url": self.url_var.get().strip() or DEFAULT_URL,
            "width": width,
            "height": height,
            "imageBase64": image_base64,
            "isMainWindow": True,
            "windowId": 1,
        }

    def _endpoint(self, suffix: str) -> str:
        return self.base_url.get().strip().rstrip("/") + suffix

    def _push_frame(self) -> None:
        payload = self._payload()
        response = requests.post(
            self._endpoint("/api/debug/fake-frame"),
            json=payload,
            headers=self._headers(),
            timeout=45,
        )
        response.raise_for_status()
        data = response.json()
        self.events.put(("status", f"Frame enviada para {data.get('sessionId')} / {data.get('viewId')}"))
        self.events.put(("log", f"[{time.strftime('%H:%M:%S')}] frame enviada ({len(payload['imageBase64'])} chars base64)"))

    def _stream_loop(self, interval_ms: int) -> None:
        self.events.put(("status", "Stream ativo. O monitor deve enxergar a sessao fake em tempo real."))
        while not self.stop_event.is_set():
            try:
                self._push_frame()
            except Exception as exc:  # noqa: BLE001
                self.events.put(("error", str(exc)))
            if self.stop_event.wait(interval_ms / 1000):
                break
        self.events.put(("status", "Stream parado."))

    def _run_async(self, target, *args) -> None:
        thread = threading.Thread(target=target, args=args, daemon=True)
        thread.start()

    def send_once(self) -> None:
        try:
            self._payload()
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("RED SEB Debug Streamer", str(exc))
            return

        self.status_var.set("Enviando frame unica...")

        def worker() -> None:
            try:
                self._push_frame()
            except Exception as exc:  # noqa: BLE001
                self.events.put(("error", str(exc)))

        self._run_async(worker)

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
        self.status_var.set("Parando stream...")

    def clear_session(self) -> None:
        session_id = self.session_id.get().strip() or DEFAULT_SESSION_ID
        self.status_var.set("Limpando a sessao fake...")

        def worker() -> None:
            try:
                response = requests.post(
                    self._endpoint("/api/debug/session/clear"),
                    json={"sessionId": session_id},
                    headers=self._headers(),
                    timeout=30,
                )
                response.raise_for_status()
                data = response.json()
                removed = bool(data.get("removed"))
                self.events.put(("status", f"Sessao {session_id} limpa ({'removida' if removed else 'ja nao existia'})."))
                self.events.put(("log", f"[{time.strftime('%H:%M:%S')}] sessao limpa: {session_id}"))
            except Exception as exc:  # noqa: BLE001
                self.events.put(("error", str(exc)))

        self._run_async(worker)

    def _log(self, text: str) -> None:
        self.log_box.configure(state="normal")
        self.log_box.insert("end", text + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

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

