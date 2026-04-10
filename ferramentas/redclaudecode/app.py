from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QSettings, QSize, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ferramentas.red_model_studio.client import ModelInfo, RedProxyClient, format_model_capabilities, normalize_base_url


APP_NAME = "RED Claude Code"
ORG_NAME = "RED Systems"
DEFAULT_BASE_URL = "http://redsystems.ddns.net/proxy"
WINDOW_SIZE = QSize(1280, 820)
PING_INTERVAL_MS = 5000


class PingWorker(QThread):
    succeeded = Signal(float)
    failed = Signal(str)

    def __init__(self, base_url: str) -> None:
        super().__init__()
        self.base_url = base_url

    def run(self) -> None:
        try:
            client = RedProxyClient(self.base_url)
            self.succeeded.emit(client.ping_latency_ms())
        except Exception as exc:
            self.failed.emit(str(exc))


class CatalogWorker(QThread):
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, base_url: str) -> None:
        super().__init__()
        self.base_url = base_url

    def run(self) -> None:
        try:
            client = RedProxyClient(self.base_url)
            models = [
                model
                for model in client.fetch_models()
                if model.supports_chat or model.supports_vision
            ]
            self.succeeded.emit(models)
        except Exception as exc:
            self.failed.emit(str(exc))


class InfoCard(QFrame):
    def __init__(self, title: str, value: str = "-", subtitle: str = "") -> None:
        super().__init__()
        self.setObjectName("infoCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(4)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("cardTitle")
        self.value_label = QLabel(value)
        self.value_label.setObjectName("cardValue")
        self.subtitle_label = QLabel(subtitle)
        self.subtitle_label.setObjectName("cardSubtitle")
        self.subtitle_label.setWordWrap(True)

        layout.addWidget(self.title_label)
        layout.addWidget(self.value_label)
        layout.addWidget(self.subtitle_label)

    def set_content(self, value: str, subtitle: str = "") -> None:
        self.value_label.setText(value)
        self.subtitle_label.setText(subtitle)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.settings = QSettings(ORG_NAME, APP_NAME)
        self.models: list[ModelInfo] = []
        self.filtered_models: list[ModelInfo] = []
        self.selected_model: ModelInfo | None = None
        self.catalog_worker: CatalogWorker | None = None
        self.ping_worker: PingWorker | None = None

        self.setWindowTitle(APP_NAME)
        self.resize(WINDOW_SIZE)
        self.setMinimumSize(1120, 740)

        self._build_ui()
        self._apply_styles()
        self._restore_state()
        self._start_ping()
        QTimer.singleShot(100, self.refresh_models)

    def _build_ui(self) -> None:
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)
        self.setCentralWidget(root)

        hero = QFrame()
        hero.setObjectName("hero")
        hero_layout = QHBoxLayout(hero)
        hero_layout.setContentsMargins(18, 18, 18, 18)
        hero_layout.setSpacing(16)

        title_box = QVBoxLayout()
        title_box.setSpacing(4)
        eyebrow = QLabel("RED Systems")
        eyebrow.setObjectName("eyebrow")
        title = QLabel("Claude Code Launcher")
        title.setObjectName("heroTitle")
        subtitle = QLabel("Escolha o melhor modelo do proxy, a pasta de trabalho e abra o Claude já no contexto certo.")
        subtitle.setObjectName("heroSubtitle")
        subtitle.setWordWrap(True)
        title_box.addWidget(eyebrow)
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        hero_layout.addLayout(title_box, 1)

        right_box = QVBoxLayout()
        right_box.setSpacing(10)

        url_row = QHBoxLayout()
        self.base_url_input = QLineEdit()
        self.base_url_input.setPlaceholderText(DEFAULT_BASE_URL)
        self.base_url_input.returnPressed.connect(self.refresh_models)
        self.refresh_button = QPushButton("Atualizar modelos")
        self.refresh_button.clicked.connect(self.refresh_models)
        url_row.addWidget(self.base_url_input, 1)
        url_row.addWidget(self.refresh_button)
        right_box.addLayout(url_row)

        pills = QHBoxLayout()
        self.connection_pill = QLabel("Conectando...")
        self.connection_pill.setObjectName("pill")
        self.connection_pill.setProperty("tone", "warn")
        self.ping_pill = QLabel("Ping --")
        self.ping_pill.setObjectName("pill")
        self.ping_pill.setProperty("tone", "neutral")
        self.catalog_pill = QLabel("Modelos --")
        self.catalog_pill.setObjectName("pill")
        self.catalog_pill.setProperty("tone", "neutral")
        pills.addWidget(self.connection_pill)
        pills.addWidget(self.ping_pill)
        pills.addWidget(self.catalog_pill)
        pills.addStretch(1)
        right_box.addLayout(pills)

        hero_layout.addLayout(right_box, 1)
        layout.addWidget(hero)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)

        left = QFrame()
        left.setObjectName("panel")
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(14, 14, 14, 14)
        left_layout.setSpacing(10)

        search_title = QLabel("Modelos")
        search_title.setObjectName("sectionTitle")
        left_layout.addWidget(search_title)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Buscar por modelo, provider, capability...")
        self.search_input.textChanged.connect(self.apply_filter)
        left_layout.addWidget(self.search_input)

        self.model_list = QListWidget()
        self.model_list.currentRowChanged.connect(self._on_model_row_changed)
        left_layout.addWidget(self.model_list, 1)

        splitter.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(12)

        details = QFrame()
        details.setObjectName("panel")
        details_layout = QVBoxLayout(details)
        details_layout.setContentsMargins(14, 14, 14, 14)
        details_layout.setSpacing(10)
        details_layout.addWidget(self._section_label("Modelo selecionado"))

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)
        self.cards = {
            "model": InfoCard("Modelo", "-", "nome exposto pelo proxy"),
            "provider": InfoCard("Provider", "-", ""),
            "kind": InfoCard("Tipo", "-", ""),
            "caps": InfoCard("Capabilities", "-", ""),
            "route": InfoCard("Route model", "-", ""),
            "note": InfoCard("Nota", "-", ""),
        }
        order = ["model", "provider", "kind", "caps", "route", "note"]
        for index, key in enumerate(order):
            grid.addWidget(self.cards[key], index // 2, index % 2)
        details_layout.addLayout(grid)
        right_layout.addWidget(details)

        workspace = QFrame()
        workspace.setObjectName("panel")
        workspace_layout = QVBoxLayout(workspace)
        workspace_layout.setContentsMargins(14, 14, 14, 14)
        workspace_layout.setSpacing(10)
        workspace_layout.addWidget(self._section_label("Pasta de trabalho"))

        self.folder_path = QLineEdit()
        self.folder_path.setReadOnly(True)
        workspace_layout.addWidget(self.folder_path)

        folder_actions = QHBoxLayout()
        self.choose_folder_button = QPushButton("Escolher pasta")
        self.choose_folder_button.clicked.connect(self.choose_folder)
        self.launch_button = QPushButton("Abrir Claude Code")
        self.launch_button.setObjectName("primaryButton")
        self.launch_button.clicked.connect(self.launch_claude)
        self.launch_button.setEnabled(False)
        folder_actions.addWidget(self.choose_folder_button)
        folder_actions.addStretch(1)
        folder_actions.addWidget(self.launch_button)
        workspace_layout.addLayout(folder_actions)

        self.workspace_hint = QLabel("Escolha uma pasta e um modelo. O launcher abre o Claude em uma nova janela de terminal.")
        self.workspace_hint.setObjectName("muted")
        self.workspace_hint.setWordWrap(True)
        workspace_layout.addWidget(self.workspace_hint)
        right_layout.addWidget(workspace)

        footer = QFrame()
        footer.setObjectName("panel")
        footer_layout = QVBoxLayout(footer)
        footer_layout.setContentsMargins(14, 14, 14, 14)
        footer_layout.setSpacing(8)
        footer_layout.addWidget(self._section_label("Resumo"))
        self.summary_label = QLabel("Sem modelo selecionado.")
        self.summary_label.setWordWrap(True)
        self.summary_label.setObjectName("muted")
        footer_layout.addWidget(self.summary_label)
        right_layout.addWidget(footer)
        right_layout.addStretch(1)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 4)
        layout.addWidget(splitter, 1)

    def _section_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("sectionTitle")
        return label

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QWidget {
                background: #090d14;
                color: #f4f7fb;
                font-family: Segoe UI, Inter, Arial, sans-serif;
                font-size: 13px;
            }
            QFrame#hero, QFrame#panel, QFrame#infoCard {
                background: #111722;
                border: 1px solid #222b3b;
                border-radius: 8px;
            }
            QFrame#hero {
                border-color: #3a1b1f;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #141922, stop:1 #170f18);
            }
            QLabel#eyebrow {
                color: #ff6b6b;
                font-size: 12px;
                font-weight: 700;
            }
            QLabel#heroTitle {
                color: #ffffff;
                font-size: 30px;
                font-weight: 700;
            }
            QLabel#heroSubtitle, QLabel#muted, QLabel#cardSubtitle {
                color: #9ba8be;
            }
            QLabel#sectionTitle {
                color: #ffffff;
                font-size: 16px;
                font-weight: 700;
            }
            QLabel#pill {
                padding: 7px 12px;
                border-radius: 8px;
                border: 1px solid #2d3646;
                background: #101621;
                font-weight: 600;
            }
            QLabel#pill[tone="ok"] {
                border-color: #1f6b4f;
                background: #0f1f19;
                color: #8fe0b7;
            }
            QLabel#pill[tone="warn"] {
                border-color: #8b5f18;
                background: #20170d;
                color: #f7cb7a;
            }
            QLabel#pill[tone="error"] {
                border-color: #7f2532;
                background: #220f14;
                color: #ff9ca8;
            }
            QLineEdit, QListWidget {
                background: #0d131d;
                border: 1px solid #293345;
                border-radius: 8px;
                padding: 8px 10px;
                selection-background-color: #a62028;
            }
            QListWidget::item {
                padding: 10px 8px;
                border-bottom: 1px solid #1f2634;
            }
            QListWidget::item:selected {
                background: #1a202c;
                border-left: 3px solid #c42d36;
            }
            QPushButton {
                background: #161d29;
                border: 1px solid #293345;
                border-radius: 8px;
                padding: 9px 14px;
                font-weight: 600;
            }
            QPushButton:hover {
                border-color: #42516b;
            }
            QPushButton#primaryButton {
                background: #a62028;
                border-color: #c42d36;
                color: #ffffff;
            }
            QPushButton:disabled {
                color: #6f819d;
                background: #101621;
                border-color: #1f2632;
            }
            QLabel#cardTitle {
                color: #9ba8be;
                font-size: 12px;
            }
            QLabel#cardValue {
                color: #ffffff;
                font-size: 18px;
                font-weight: 700;
            }
            """
        )

    def _restore_state(self) -> None:
        self.base_url_input.setText(str(self.settings.value("base_url", DEFAULT_BASE_URL)))
        self.folder_path.setText(str(self.settings.value("working_folder", "")))

    def closeEvent(self, event) -> None:
        self.settings.setValue("base_url", self.base_url_input.text().strip())
        self.settings.setValue("working_folder", self.folder_path.text().strip())
        if hasattr(self, "ping_timer"):
            self.ping_timer.stop()
        for worker_name in ("ping_worker", "catalog_worker"):
            worker = getattr(self, worker_name, None)
            if worker and worker.isRunning():
                worker.wait(3000)
        super().closeEvent(event)

    def current_base_url(self) -> str:
        return normalize_base_url(self.base_url_input.text().strip() or DEFAULT_BASE_URL)

    def _start_ping(self) -> None:
        self.ping_timer = QTimer(self)
        self.ping_timer.timeout.connect(self.refresh_ping)
        self.ping_timer.start(PING_INTERVAL_MS)
        self.refresh_ping()

    def refresh_ping(self) -> None:
        if self.ping_worker and self.ping_worker.isRunning():
            return
        self.ping_worker = PingWorker(self.current_base_url())
        self.ping_worker.succeeded.connect(self._on_ping_success)
        self.ping_worker.failed.connect(self._on_ping_error)
        self.ping_worker.finished.connect(self.ping_worker.deleteLater)
        self.ping_worker.start()

    def _on_ping_success(self, latency_ms: float) -> None:
        self._set_pill(self.ping_pill, f"Ping {latency_ms:.0f} ms", "ok" if latency_ms < 150 else "warn")
        self.ping_worker = None

    def _on_ping_error(self, error: str) -> None:
        self._set_pill(self.ping_pill, f"Ping offline ({error[:40]})", "error")
        self.ping_worker = None

    def refresh_models(self) -> None:
        if self.catalog_worker and self.catalog_worker.isRunning():
            return
        self.refresh_button.setEnabled(False)
        self._set_pill(self.connection_pill, "Carregando catalogo...", "warn")
        self.catalog_worker = CatalogWorker(self.current_base_url())
        self.catalog_worker.succeeded.connect(self._on_catalog_loaded)
        self.catalog_worker.failed.connect(self._on_catalog_error)
        self.catalog_worker.finished.connect(self.catalog_worker.deleteLater)
        self.catalog_worker.start()

    def _on_catalog_loaded(self, models: list[ModelInfo]) -> None:
        self.models = list(models or [])
        self.apply_filter()
        self._set_pill(self.connection_pill, "Proxy conectado", "ok")
        self._set_pill(self.catalog_pill, f"Modelos {len(self.models)}", "ok")
        self.refresh_button.setEnabled(True)
        self.catalog_worker = None
        self.refresh_ping()

    def _on_catalog_error(self, error: str) -> None:
        self._set_pill(self.connection_pill, f"Falha no catalogo ({error[:48]})", "error")
        self._set_pill(self.catalog_pill, "Modelos indisponiveis", "error")
        self.refresh_button.setEnabled(True)
        self.catalog_worker = None

    def apply_filter(self) -> None:
        query = self.search_input.text().strip().lower()
        self.filtered_models = [
            model
            for model in self.models
            if not query
            or query in (
                " ".join(
                    [
                        model.id,
                        model.provider,
                        model.kind,
                        format_model_capabilities(model),
                        model.route_model,
                        model.note,
                    ]
                ).lower()
            )
        ]
        self.model_list.clear()
        for model in self.filtered_models:
            item = QListWidgetItem(f"{model.id}\n{model.provider or 'provider n/d'} | {format_model_capabilities(model)}")
            item.setData(Qt.UserRole, model.id)
            self.model_list.addItem(item)
        if self.filtered_models:
            self.model_list.setCurrentRow(0)
        else:
            self.selected_model = None
            self._render_selected_model()

    def _on_model_row_changed(self, row: int) -> None:
        self.selected_model = self.filtered_models[row] if 0 <= row < len(self.filtered_models) else None
        self._render_selected_model()

    def _render_selected_model(self) -> None:
        model = self.selected_model
        if not model:
            self.cards["model"].set_content("-", "nenhum modelo selecionado")
            self.cards["provider"].set_content("-")
            self.cards["kind"].set_content("-")
            self.cards["caps"].set_content("-")
            self.cards["route"].set_content("-")
            self.cards["note"].set_content("-")
            self.summary_label.setText("Sem modelo selecionado.")
            self._update_launch_state()
            return

        self.cards["model"].set_content(model.id, "nome exposto pelo proxy")
        self.cards["provider"].set_content(model.provider or model.owned_by or "-")
        self.cards["kind"].set_content(model.kind or "-")
        self.cards["caps"].set_content(format_model_capabilities(model))
        self.cards["route"].set_content(model.route_model or "-", "upstream final")
        self.cards["note"].set_content(model.note or "-", "observacao do catalogo")
        self.summary_label.setText(
            f"Selecionado: {model.id}\n"
            f"Provider: {model.provider or model.owned_by or 'n/d'} | "
            f"Tipo: {model.kind or 'chat'} | Capabilities: {format_model_capabilities(model)}"
        )
        self._update_launch_state()

    def choose_folder(self) -> None:
        initial = self.folder_path.text().strip() or str(Path.cwd())
        target = QFileDialog.getExistingDirectory(self, "Escolha a pasta de trabalho", initial)
        if not target:
            return
        self.folder_path.setText(target)
        self.workspace_hint.setText("Pasta pronta. Quando clicar em abrir, o Claude sobe em uma nova janela de terminal.")
        self._update_launch_state()

    def _update_launch_state(self) -> None:
        ready = bool(self.selected_model and self.folder_path.text().strip())
        self.launch_button.setEnabled(ready)

    def launch_claude(self) -> None:
        if not self.selected_model:
            QMessageBox.information(self, APP_NAME, "Escolha um modelo primeiro.")
            return
        folder = self.folder_path.text().strip()
        if not folder:
            QMessageBox.information(self, APP_NAME, "Escolha uma pasta de trabalho.")
            return
        normalized_folder = str(Path(folder).resolve())
        if not Path(normalized_folder).exists():
            QMessageBox.warning(self, APP_NAME, "A pasta escolhida nao existe mais.")
            return

        base_url = self.current_base_url()
        env = os.environ.copy()
        env["ANTHROPIC_AUTH_TOKEN"] = "ollama"
        env["ANTHROPIC_API_KEY"] = ""
        env["ANTHROPIC_BASE_URL"] = base_url

        claude_command = subprocess.list2cmdline(["claude", "--model", self.selected_model.id])
        command = (
            f"title RED Claude Code - {self.selected_model.id} "
            f"&& cls "
            f"&& echo RED Systems Claude Code "
            f"&& echo Modelo: {self.selected_model.id} "
            f"&& echo Pasta : {normalized_folder} "
            f"&& echo. "
            f"&& {claude_command}"
        )
        try:
            subprocess.Popen(
                ["cmd.exe", "/k", command],
                cwd=normalized_folder,
                env=env,
                creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0),
            )
            self.workspace_hint.setText(
                f"Claude aberto com {self.selected_model.id} em {normalized_folder}."
            )
        except Exception as exc:
            QMessageBox.critical(self, APP_NAME, f"Nao foi possivel abrir o Claude Code.\n\n{exc}")

    def _set_pill(self, widget: QLabel, text: str, tone: str) -> None:
        widget.setText(text)
        widget.setProperty("tone", tone)
        widget.style().unpolish(widget)
        widget.style().polish(widget)


def main() -> int:
    app = QApplication(sys.argv)
    app.setOrganizationName(ORG_NAME)
    app.setApplicationName(APP_NAME)
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 10))
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
