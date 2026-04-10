from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from PySide6.QtCore import QSettings, QSize, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QFont, QImage, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTabWidget,
    QTextBrowser,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QDoubleSpinBox,
    QSpinBox,
)

from .client import (
    ChatResult,
    ImageResult,
    ModelInfo,
    RedProxyClient,
    format_model_capabilities,
    normalize_base_url,
    rich_text_block,
)


APP_NAME = "RED Model Studio"
ORG_NAME = "RED Systems"
WINDOW_SIZE = QSize(1460, 940)
PING_INTERVAL_MS = 4000
IMAGE_SIZES = [768, 832, 896, 960, 1024, 1088, 1152, 1216, 1280, 1344]
DEFAULT_BASE_URL = "http://redsystems.ddns.net/ollama"
DEFAULT_SYSTEM_PROMPT = (
    "Seja objetivo, util e confiavel. Quando fizer sentido, deixe claro o thinking "
    "de forma separada da resposta final."
)
DEFAULT_IMAGE_PROMPT = (
    "RED Systems control room, dark matte interface, subtle red accents, premium "
    "technical illustration, clean composition"
)

IMAGE_RULES: dict[str, dict[str, int | str]] = {
    "nim - flux.2-klein-4b": {"default_steps": 4, "max_steps": 4, "min_size": 768},
    "nim - flux.1-schnell": {"default_steps": 4, "max_steps": 4, "min_size": 768},
    "nim - flux.1-dev": {"default_steps": 8, "max_steps": 50, "min_size": 768},
    "nim - stable-diffusion-xl": {"default_steps": 30, "max_steps": 50, "min_size": 1024},
    "nim - stable-diffusion-3-medium": {"default_steps": 30, "max_steps": 50, "min_size": 1024},
}


def format_ms(value: int | None) -> str:
    if value is None:
        return "n/d"
    return f"{int(value)} ms"


def format_tokens_per_second(value: float | None) -> str:
    if value is None:
        return "n/d"
    return f"{value:.2f} tok/s"


def format_int(value: int | None) -> str:
    if value is None:
        return "n/d"
    return f"{value}"


def image_rules_for_model(model_name: str) -> dict[str, int | str]:
    lowered = str(model_name or "").strip().lower()
    return IMAGE_RULES.get(lowered, {"default_steps": 8, "max_steps": 50, "min_size": 768})


class PingWorker(QThread):
    succeeded = Signal(float)
    failed = Signal(str)

    def __init__(self, base_url: str) -> None:
        super().__init__()
        self.base_url = base_url

    def run(self) -> None:
        try:
            client = RedProxyClient(self.base_url)
            latency = client.ping_latency_ms()
            self.succeeded.emit(latency)
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
            models = client.fetch_models()
            self.succeeded.emit(models)
        except Exception as exc:
            self.failed.emit(str(exc))


class ChatWorker(QThread):
    delta = Signal(object)
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        messages: list[dict[str, str]],
        system_prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> None:
        super().__init__()
        self.base_url = base_url
        self.model = model
        self.messages = messages
        self.system_prompt = system_prompt
        self.temperature = temperature
        self.max_tokens = max_tokens

    def run(self) -> None:
        try:
            client = RedProxyClient(self.base_url)
            result = client.chat_stream(
                model=self.model,
                messages=self.messages,
                system_prompt=self.system_prompt,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                on_delta=lambda item: self.delta.emit(item),
            )
            self.succeeded.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))


class ImageWorker(QThread):
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        prompt: str,
        width: int,
        height: int,
        steps: int,
        seed: str,
    ) -> None:
        super().__init__()
        self.base_url = base_url
        self.model = model
        self.prompt = prompt
        self.width = width
        self.height = height
        self.steps = steps
        self.seed = seed

    def run(self) -> None:
        try:
            client = RedProxyClient(self.base_url)
            result = client.generate_image(
                model=self.model,
                prompt=self.prompt,
                width=self.width,
                height=self.height,
                steps=self.steps,
                seed=self.seed,
            )
            self.succeeded.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))


class MetricCard(QFrame):
    def __init__(self, label: str, value: str = "-", subtitle: str = "") -> None:
        super().__init__()
        self.setObjectName("metricCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(4)

        self.label_widget = QLabel(label)
        self.label_widget.setObjectName("metricCardLabel")
        self.value_widget = QLabel(value)
        self.value_widget.setObjectName("metricCardValue")
        self.subtitle_widget = QLabel(subtitle)
        self.subtitle_widget.setObjectName("metricCardSubtitle")
        self.subtitle_widget.setWordWrap(True)

        layout.addWidget(self.label_widget)
        layout.addWidget(self.value_widget)
        layout.addWidget(self.subtitle_widget)

    def set_value(self, value: str, subtitle: str = "") -> None:
        self.value_widget.setText(value)
        self.subtitle_widget.setText(subtitle)


class MessageBubble(QFrame):
    def __init__(self, role: str, content: str = "", thinking: str = "") -> None:
        super().__init__()
        self.role = role
        self.setObjectName("messageBubble")
        self.setProperty("role", role)
        self.setProperty("pending", False)
        self.setFrameShape(QFrame.StyledPanel)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)

        self.title_label = QLabel("Voce" if role == "user" else "Modelo")
        self.title_label.setObjectName("messageTitle")
        self.meta_label = QLabel("")
        self.meta_label.setObjectName("messageMeta")
        self.meta_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        header.addWidget(self.title_label)
        header.addStretch(1)
        header.addWidget(self.meta_label)
        layout.addLayout(header)

        self.answer_browser = QTextBrowser()
        self.answer_browser.setObjectName("messageBody")
        self.answer_browser.setOpenExternalLinks(True)
        self.answer_browser.setReadOnly(True)
        self.answer_browser.setFrameShape(QFrame.NoFrame)
        self.answer_browser.setMinimumHeight(56)
        layout.addWidget(self.answer_browser)

        self.thinking_toggle = QToolButton()
        self.thinking_toggle.setObjectName("thinkingToggle")
        self.thinking_toggle.setCheckable(True)
        self.thinking_toggle.setChecked(False)
        self.thinking_toggle.setText("Thinking")
        self.thinking_toggle.setVisible(False)
        self.thinking_toggle.toggled.connect(self._toggle_thinking)
        layout.addWidget(self.thinking_toggle)

        self.thinking_browser = QTextBrowser()
        self.thinking_browser.setObjectName("thinkingBody")
        self.thinking_browser.setReadOnly(True)
        self.thinking_browser.setFrameShape(QFrame.NoFrame)
        self.thinking_browser.setMinimumHeight(72)
        self.thinking_browser.setVisible(False)
        layout.addWidget(self.thinking_browser)

        self.set_content(content, thinking)

    def _toggle_thinking(self, checked: bool) -> None:
        self.thinking_browser.setVisible(checked and self.thinking_toggle.isVisible())

    def set_pending(self, enabled: bool) -> None:
        self.setProperty("pending", enabled)
        self.style().unpolish(self)
        self.style().polish(self)

    def set_meta(self, text: str) -> None:
        self.meta_label.setText(text)

    def set_content(self, content: str, thinking: str = "") -> None:
        self.answer_browser.setHtml(rich_text_block(content or "..."))
        clean_thinking = str(thinking or "").strip()
        self.thinking_toggle.setVisible(bool(clean_thinking))
        self.thinking_browser.setHtml(rich_text_block(clean_thinking))
        if not clean_thinking:
            self.thinking_toggle.setChecked(False)
            self.thinking_browser.setVisible(False)

    def set_error(self, text: str) -> None:
        self.title_label.setText("Erro")
        self.setProperty("role", "error")
        self.style().unpolish(self)
        self.style().polish(self)
        self.set_content(text, "")


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.settings = QSettings(ORG_NAME, APP_NAME)
        self.models: list[ModelInfo] = []
        self.model_map: dict[str, ModelInfo] = {}
        self.chat_history: list[dict[str, str]] = []
        self.pending_assistant_bubble: MessageBubble | None = None
        self.current_image_result: ImageResult | None = None
        self.ping_worker: PingWorker | None = None
        self.catalog_worker: CatalogWorker | None = None
        self.chat_worker: ChatWorker | None = None
        self.image_worker: ImageWorker | None = None

        self.setWindowTitle(APP_NAME)
        self.resize(WINDOW_SIZE)
        self.setMinimumSize(1180, 760)

        self._build_ui()
        self._apply_styles()
        self._restore_settings()
        self._start_ping_timer()
        QTimer.singleShot(120, self.refresh_models)

    def _build_ui(self) -> None:
        central = QWidget()
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(18, 18, 18, 18)
        central_layout.setSpacing(14)
        self.setCentralWidget(central)

        header = self._build_header()
        central_layout.addWidget(header)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("mainTabs")
        self.tabs.addTab(self._build_chat_tab(), "Chat")
        self.tabs.addTab(self._build_image_tab(), "Imagens")
        central_layout.addWidget(self.tabs, 1)

        footer = QLabel("Proxy alvo: RED Systems unified VM | compatibilidade Ollama/OpenAI/NIM")
        footer.setObjectName("footerLabel")
        central_layout.addWidget(footer)

    def _build_header(self) -> QWidget:
        wrapper = QFrame()
        wrapper.setObjectName("heroCard")
        layout = QHBoxLayout(wrapper)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(16)

        title_box = QVBoxLayout()
        title_box.setSpacing(4)
        eyebrow = QLabel("RED Systems")
        eyebrow.setObjectName("eyebrow")
        title = QLabel("RED Model Studio")
        title.setObjectName("heroTitle")
        subtitle = QLabel(
            "Chat, thinking, latencia real, throughput e geracao de imagens a partir do proxy oficial."
        )
        subtitle.setObjectName("heroSubtitle")
        subtitle.setWordWrap(True)
        title_box.addWidget(eyebrow)
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        layout.addLayout(title_box, 1)

        controls = QVBoxLayout()
        controls.setSpacing(10)

        base_row = QHBoxLayout()
        base_row.setSpacing(8)
        self.base_url_input = QLineEdit()
        self.base_url_input.setPlaceholderText(DEFAULT_BASE_URL)
        self.base_url_input.setMinimumWidth(360)
        self.base_url_input.returnPressed.connect(self.refresh_models)
        self.connect_button = QPushButton("Conectar")
        self.connect_button.clicked.connect(self.refresh_models)
        self.refresh_button = QPushButton("Atualizar modelos")
        self.refresh_button.clicked.connect(self.refresh_models)
        base_row.addWidget(self.base_url_input, 1)
        base_row.addWidget(self.connect_button)
        base_row.addWidget(self.refresh_button)
        controls.addLayout(base_row)

        status_row = QHBoxLayout()
        status_row.setSpacing(8)
        self.connection_status = QLabel("Aguardando catalogo")
        self.connection_status.setObjectName("statusPill")
        self.connection_status.setProperty("tone", "neutral")
        self.ping_status = QLabel("Ping -- ms")
        self.ping_status.setObjectName("statusPill")
        self.ping_status.setProperty("tone", "neutral")
        self.catalog_status = QLabel("Modelos --")
        self.catalog_status.setObjectName("statusPill")
        self.catalog_status.setProperty("tone", "neutral")
        status_row.addWidget(self.connection_status)
        status_row.addWidget(self.ping_status)
        status_row.addWidget(self.catalog_status)
        status_row.addStretch(1)
        controls.addLayout(status_row)

        layout.addLayout(controls, 1)
        return wrapper

    def _build_chat_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        controls = QFrame()
        controls.setObjectName("toolbarCard")
        controls_layout = QGridLayout(controls)
        controls_layout.setContentsMargins(14, 14, 14, 14)
        controls_layout.setHorizontalSpacing(10)
        controls_layout.setVerticalSpacing(8)

        self.chat_model_combo = QComboBox()
        self.chat_model_combo.setEditable(True)
        self.chat_model_combo.setInsertPolicy(QComboBox.NoInsert)
        self.chat_model_combo.currentTextChanged.connect(self._on_chat_model_changed)

        self.temperature_input = QDoubleSpinBox()
        self.temperature_input.setDecimals(2)
        self.temperature_input.setRange(0.0, 2.0)
        self.temperature_input.setSingleStep(0.05)
        self.temperature_input.setValue(0.2)

        self.max_tokens_input = QSpinBox()
        self.max_tokens_input.setRange(32, 16384)
        self.max_tokens_input.setSingleStep(64)
        self.max_tokens_input.setValue(2048)

        self.chat_clear_button = QPushButton("Nova conversa")
        self.chat_clear_button.clicked.connect(self.clear_chat)

        controls_layout.addWidget(QLabel("Modelo"), 0, 0)
        controls_layout.addWidget(self.chat_model_combo, 1, 0, 1, 3)
        controls_layout.addWidget(QLabel("Temperatura"), 0, 3)
        controls_layout.addWidget(self.temperature_input, 1, 3)
        controls_layout.addWidget(QLabel("Max tokens"), 0, 4)
        controls_layout.addWidget(self.max_tokens_input, 1, 4)
        controls_layout.addWidget(self.chat_clear_button, 1, 5)
        layout.addWidget(controls)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(12)

        history_card = QFrame()
        history_card.setObjectName("panelCard")
        history_layout = QVBoxLayout(history_card)
        history_layout.setContentsMargins(12, 12, 12, 12)
        history_layout.setSpacing(10)
        history_header = QLabel("Conversa")
        history_header.setObjectName("sectionTitle")
        history_layout.addWidget(history_header)

        self.chat_scroll = QScrollArea()
        self.chat_scroll.setWidgetResizable(True)
        self.chat_scroll.setFrameShape(QFrame.NoFrame)
        self.chat_scroll.setObjectName("chatScrollArea")
        self.chat_scroll_widget = QWidget()
        self.chat_scroll_layout = QVBoxLayout(self.chat_scroll_widget)
        self.chat_scroll_layout.setContentsMargins(0, 0, 0, 0)
        self.chat_scroll_layout.setSpacing(10)
        self.chat_scroll_layout.addStretch(1)
        self.chat_scroll.setWidget(self.chat_scroll_widget)
        history_layout.addWidget(self.chat_scroll, 1)
        left_layout.addWidget(history_card, 1)

        composer = QFrame()
        composer.setObjectName("panelCard")
        composer_layout = QVBoxLayout(composer)
        composer_layout.setContentsMargins(12, 12, 12, 12)
        composer_layout.setSpacing(8)
        composer_title = QLabel("Prompt")
        composer_title.setObjectName("sectionTitle")
        composer_layout.addWidget(composer_title)

        self.chat_input = QPlainTextEdit()
        self.chat_input.setPlaceholderText("Escreva sua pergunta para o proxy...")
        self.chat_input.setMinimumHeight(140)
        composer_layout.addWidget(self.chat_input)

        composer_actions = QHBoxLayout()
        composer_actions.setSpacing(8)
        self.send_button = QPushButton("Enviar")
        self.send_button.setObjectName("primaryButton")
        self.send_button.clicked.connect(self.send_message)
        self.chat_status = QLabel("Pronto para conversar.")
        self.chat_status.setObjectName("mutedLabel")
        composer_actions.addWidget(self.chat_status, 1)
        composer_actions.addWidget(self.send_button)
        composer_layout.addLayout(composer_actions)
        left_layout.addWidget(composer)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(12)

        metrics_card = QFrame()
        metrics_card.setObjectName("panelCard")
        metrics_layout = QVBoxLayout(metrics_card)
        metrics_layout.setContentsMargins(12, 12, 12, 12)
        metrics_layout.setSpacing(10)
        metrics_layout.addWidget(self._section_label("Metrica da resposta"))

        metrics_grid = QGridLayout()
        metrics_grid.setHorizontalSpacing(10)
        metrics_grid.setVerticalSpacing(10)
        self.metric_cards = {
            "response_model": MetricCard("Modelo final", "-", "rota devolvida pelo proxy"),
            "total_ms": MetricCard("Tempo total", "-", "resposta completa"),
            "first_token_ms": MetricCard("Primeiro token", "-", "latencia de inicio"),
            "tokens_per_second": MetricCard("Throughput", "-", "tokens por segundo"),
            "prompt_tokens": MetricCard("Prompt tokens", "-", ""),
            "completion_tokens": MetricCard("Completion tokens", "-", ""),
            "total_tokens": MetricCard("Tokens totais", "-", ""),
            "finish_reason": MetricCard("Finish reason", "-", ""),
        }
        for index, key in enumerate(
            [
                "response_model",
                "total_ms",
                "first_token_ms",
                "tokens_per_second",
                "prompt_tokens",
                "completion_tokens",
                "total_tokens",
                "finish_reason",
            ]
        ):
            metrics_grid.addWidget(self.metric_cards[key], index // 2, index % 2)
        metrics_layout.addLayout(metrics_grid)
        right_layout.addWidget(metrics_card)

        thinking_card = QFrame()
        thinking_card.setObjectName("panelCard")
        thinking_layout = QVBoxLayout(thinking_card)
        thinking_layout.setContentsMargins(12, 12, 12, 12)
        thinking_layout.setSpacing(8)
        thinking_layout.addWidget(self._section_label("Thinking / cadeia de raciocinio"))
        self.thinking_status = QLabel("Nenhum thinking recebido ainda.")
        self.thinking_status.setObjectName("mutedLabel")
        self.thinking_view = QTextBrowser()
        self.thinking_view.setObjectName("thinkingInspector")
        self.thinking_view.setReadOnly(True)
        self.thinking_view.setOpenExternalLinks(True)
        thinking_layout.addWidget(self.thinking_status)
        thinking_layout.addWidget(self.thinking_view, 1)
        right_layout.addWidget(thinking_card, 1)

        config_card = QFrame()
        config_card.setObjectName("panelCard")
        config_layout = QVBoxLayout(config_card)
        config_layout.setContentsMargins(12, 12, 12, 12)
        config_layout.setSpacing(8)
        config_layout.addWidget(self._section_label("System prompt"))
        self.system_prompt_input = QPlainTextEdit()
        self.system_prompt_input.setPlaceholderText("Opcional. O system prompt vai junto em todas as mensagens.")
        self.system_prompt_input.setMinimumHeight(120)
        self.system_prompt_input.setPlainText(DEFAULT_SYSTEM_PROMPT)
        config_layout.addWidget(self.system_prompt_input)
        self.model_note_label = QLabel("Carregando detalhes do modelo...")
        self.model_note_label.setWordWrap(True)
        self.model_note_label.setObjectName("mutedLabel")
        config_layout.addWidget(self.model_note_label)
        right_layout.addWidget(config_card)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter, 1)
        return page

    def _build_image_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        header = QFrame()
        header.setObjectName("toolbarCard")
        header_layout = QGridLayout(header)
        header_layout.setContentsMargins(14, 14, 14, 14)
        header_layout.setHorizontalSpacing(10)
        header_layout.setVerticalSpacing(8)

        self.image_model_combo = QComboBox()
        self.image_model_combo.currentTextChanged.connect(self._on_image_model_changed)
        self.image_generate_button = QPushButton("Gerar imagem")
        self.image_generate_button.setObjectName("primaryButton")
        self.image_generate_button.clicked.connect(self.generate_image)
        self.image_save_button = QPushButton("Salvar")
        self.image_save_button.clicked.connect(self.save_image)
        self.image_save_button.setEnabled(False)

        header_layout.addWidget(QLabel("Modelo de imagem"), 0, 0)
        header_layout.addWidget(self.image_model_combo, 1, 0, 1, 3)
        header_layout.addWidget(self.image_generate_button, 1, 3)
        header_layout.addWidget(self.image_save_button, 1, 4)
        layout.addWidget(header)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)

        left = QFrame()
        left.setObjectName("panelCard")
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(12, 12, 12, 12)
        left_layout.setSpacing(10)
        left_layout.addWidget(self._section_label("Prompt de imagem"))

        self.image_prompt_input = QPlainTextEdit()
        self.image_prompt_input.setMinimumHeight(180)
        self.image_prompt_input.setPlainText(DEFAULT_IMAGE_PROMPT)
        left_layout.addWidget(self.image_prompt_input)

        controls = QGridLayout()
        controls.setHorizontalSpacing(10)
        controls.setVerticalSpacing(8)

        self.image_width_combo = QComboBox()
        self.image_height_combo = QComboBox()
        for value in IMAGE_SIZES:
            self.image_width_combo.addItem(str(value), value)
            self.image_height_combo.addItem(str(value), value)
        self._set_combo_value(self.image_width_combo, 1024)
        self._set_combo_value(self.image_height_combo, 1024)

        self.image_steps_input = QSpinBox()
        self.image_steps_input.setRange(1, 50)
        self.image_steps_input.setValue(4)

        self.image_seed_input = QLineEdit()
        self.image_seed_input.setPlaceholderText("Opcional")

        controls.addWidget(QLabel("Largura"), 0, 0)
        controls.addWidget(self.image_width_combo, 1, 0)
        controls.addWidget(QLabel("Altura"), 0, 1)
        controls.addWidget(self.image_height_combo, 1, 1)
        controls.addWidget(QLabel("Steps"), 0, 2)
        controls.addWidget(self.image_steps_input, 1, 2)
        controls.addWidget(QLabel("Seed"), 0, 3)
        controls.addWidget(self.image_seed_input, 1, 3)
        left_layout.addLayout(controls)

        self.image_model_note = QLabel("Use tamanhos seguros para evitar erro do backend.")
        self.image_model_note.setWordWrap(True)
        self.image_model_note.setObjectName("mutedLabel")
        left_layout.addWidget(self.image_model_note)

        self.image_status = QLabel("Pronto para gerar.")
        self.image_status.setObjectName("mutedLabel")
        left_layout.addWidget(self.image_status)

        right = QFrame()
        right.setObjectName("panelCard")
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(12, 12, 12, 12)
        right_layout.setSpacing(10)
        right_layout.addWidget(self._section_label("Preview"))

        self.image_preview = QLabel("A imagem gerada aparece aqui.")
        self.image_preview.setObjectName("imagePreview")
        self.image_preview.setAlignment(Qt.AlignCenter)
        self.image_preview.setMinimumSize(500, 500)
        self.image_preview.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        right_layout.addWidget(self.image_preview, 1)

        meta_grid = QGridLayout()
        meta_grid.setHorizontalSpacing(10)
        meta_grid.setVerticalSpacing(10)
        self.image_metric_cards = {
            "image_model": MetricCard("Modelo", "-", ""),
            "image_duration": MetricCard("Duracao", "-", ""),
            "image_seed": MetricCard("Seed", "-", ""),
            "image_size": MetricCard("Tamanho", "-", ""),
        }
        for index, key in enumerate(["image_model", "image_duration", "image_seed", "image_size"]):
            meta_grid.addWidget(self.image_metric_cards[key], index // 2, index % 2)
        right_layout.addLayout(meta_grid)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        layout.addWidget(splitter, 1)
        return page

    def _section_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("sectionTitle")
        return label

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QWidget {
                background: #0b0f16;
                color: #f4f7fb;
                font-family: Segoe UI, Inter, Arial, sans-serif;
                font-size: 13px;
            }
            QMainWindow {
                background: #070b11;
            }
            QFrame#heroCard, QFrame#toolbarCard, QFrame#panelCard, QFrame#metricCard {
                background: #111722;
                border: 1px solid #222b3b;
                border-radius: 8px;
            }
            QFrame#heroCard {
                border-color: #3a1b1f;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #141922, stop:1 #161018);
            }
            QLabel#eyebrow {
                color: #ff6b6b;
                font-size: 12px;
                font-weight: 700;
            }
            QLabel#heroTitle {
                font-size: 28px;
                font-weight: 700;
                color: #ffffff;
            }
            QLabel#heroSubtitle, QLabel#footerLabel, QLabel#mutedLabel, QLabel#metricCardSubtitle, QLabel#messageMeta {
                color: #9ba8be;
            }
            QLabel#sectionTitle {
                font-size: 16px;
                font-weight: 700;
                color: #ffffff;
            }
            QLabel#statusPill {
                padding: 7px 12px;
                border-radius: 8px;
                border: 1px solid #2d3646;
                background: #101621;
                font-weight: 600;
            }
            QLabel#statusPill[tone="ok"] {
                border-color: #1f6b4f;
                background: #0f1f19;
                color: #8fe0b7;
            }
            QLabel#statusPill[tone="warn"] {
                border-color: #8b5f18;
                background: #20170d;
                color: #f7cb7a;
            }
            QLabel#statusPill[tone="error"] {
                border-color: #7f2532;
                background: #220f14;
                color: #ff9ca8;
            }
            QLabel#metricCardLabel {
                color: #9ba8be;
                font-size: 12px;
            }
            QLabel#metricCardValue {
                color: #ffffff;
                font-size: 18px;
                font-weight: 700;
            }
            QLineEdit, QPlainTextEdit, QComboBox, QDoubleSpinBox, QSpinBox, QTextBrowser {
                background: #0e141f;
                border: 1px solid #283243;
                border-radius: 8px;
                padding: 8px 10px;
                selection-background-color: #9a2226;
            }
            QPlainTextEdit, QTextBrowser {
                padding: 10px 12px;
            }
            QComboBox::drop-down {
                width: 28px;
                border: none;
            }
            QPushButton {
                background: #161d29;
                border: 1px solid #293345;
                border-radius: 8px;
                padding: 9px 14px;
                font-weight: 600;
            }
            QPushButton:hover {
                border-color: #3a4962;
            }
            QPushButton:disabled {
                color: #708099;
                background: #101621;
                border-color: #1d2531;
            }
            QPushButton#primaryButton {
                background: #a62028;
                border-color: #c42d36;
                color: #ffffff;
            }
            QPushButton#primaryButton:hover {
                background: #b72630;
            }
            QTabWidget::pane {
                border: none;
                margin-top: 8px;
            }
            QTabBar::tab {
                background: #0f141d;
                color: #9ba8be;
                border: 1px solid #212a38;
                border-bottom: none;
                padding: 10px 16px;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                margin-right: 6px;
            }
            QTabBar::tab:selected {
                background: #141b27;
                color: #ffffff;
                border-color: #3a1b1f;
            }
            QScrollArea#chatScrollArea {
                background: transparent;
            }
            QFrame#messageBubble {
                border-radius: 8px;
                border: 1px solid #283243;
                background: #0f141d;
            }
            QFrame#messageBubble[role="user"] {
                border-color: #1f4d5c;
                background: #0d1820;
            }
            QFrame#messageBubble[role="assistant"] {
                border-color: #3a1b1f;
                background: #15111a;
            }
            QFrame#messageBubble[role="error"] {
                border-color: #7f2532;
                background: #220f14;
            }
            QFrame#messageBubble[pending="true"] {
                border-style: dashed;
            }
            QLabel#messageTitle {
                font-weight: 700;
                color: #ffffff;
            }
            QToolButton#thinkingToggle {
                text-align: left;
                color: #f7cb7a;
                border: 1px solid #5b4720;
                border-radius: 8px;
                background: #19140c;
                padding: 7px 10px;
            }
            QTextBrowser#thinkingInspector, QTextBrowser#thinkingBody {
                background: #0f1318;
                border-color: #3d2f12;
            }
            QLabel#imagePreview {
                border: 1px dashed #3a4558;
                border-radius: 8px;
                background: #0a1018;
                color: #8ea0ba;
                padding: 12px;
            }
            """
        )

    def _restore_settings(self) -> None:
        self.base_url_input.setText(str(self.settings.value("base_url", DEFAULT_BASE_URL)))
        self.system_prompt_input.setPlainText(str(self.settings.value("system_prompt", DEFAULT_SYSTEM_PROMPT)))
        self.temperature_input.setValue(float(self.settings.value("temperature", 0.2)))
        self.max_tokens_input.setValue(int(self.settings.value("max_tokens", 2048)))
        self.image_prompt_input.setPlainText(str(self.settings.value("image_prompt", DEFAULT_IMAGE_PROMPT)))
        self.image_seed_input.setText(str(self.settings.value("image_seed", "")))
        self._set_combo_value(self.image_width_combo, int(self.settings.value("image_width", 1024)))
        self._set_combo_value(self.image_height_combo, int(self.settings.value("image_height", 1024)))
        self.image_steps_input.setValue(int(self.settings.value("image_steps", 4)))

    def closeEvent(self, event: Any) -> None:
        if hasattr(self, "ping_timer"):
            self.ping_timer.stop()
        for worker_name in ("ping_worker", "catalog_worker", "chat_worker", "image_worker"):
            worker = getattr(self, worker_name, None)
            if worker and worker.isRunning():
                worker.wait(3000)
        self.settings.setValue("base_url", self.base_url_input.text().strip())
        self.settings.setValue("system_prompt", self.system_prompt_input.toPlainText())
        self.settings.setValue("temperature", self.temperature_input.value())
        self.settings.setValue("max_tokens", self.max_tokens_input.value())
        self.settings.setValue("chat_model", self.chat_model_combo.currentText())
        self.settings.setValue("image_model", self.image_model_combo.currentText())
        self.settings.setValue("image_prompt", self.image_prompt_input.toPlainText())
        self.settings.setValue("image_width", self.image_width_combo.currentData())
        self.settings.setValue("image_height", self.image_height_combo.currentData())
        self.settings.setValue("image_steps", self.image_steps_input.value())
        self.settings.setValue("image_seed", self.image_seed_input.text().strip())
        super().closeEvent(event)

    def _start_ping_timer(self) -> None:
        self.ping_timer = QTimer(self)
        self.ping_timer.timeout.connect(self.refresh_ping)
        self.ping_timer.start(PING_INTERVAL_MS)
        self.refresh_ping()

    def current_base_url(self) -> str:
        return normalize_base_url(self.base_url_input.text().strip() or DEFAULT_BASE_URL)

    def refresh_ping(self) -> None:
        if self.ping_worker and self.ping_worker.isRunning():
            return
        self.ping_worker = PingWorker(self.current_base_url())
        self.ping_worker.succeeded.connect(self._on_ping_success)
        self.ping_worker.failed.connect(self._on_ping_error)
        self.ping_worker.finished.connect(self.ping_worker.deleteLater)
        self.ping_worker.start()

    def _on_ping_success(self, latency_ms: float) -> None:
        self._set_pill(self.ping_status, f"Ping {latency_ms:.0f} ms", "ok" if latency_ms < 150 else "warn")
        self.ping_worker = None

    def _on_ping_error(self, error: str) -> None:
        self._set_pill(self.ping_status, f"Ping offline ({error[:48]})", "error")
        self.ping_worker = None

    def refresh_models(self) -> None:
        if self.catalog_worker and self.catalog_worker.isRunning():
            return
        self.connect_button.setEnabled(False)
        self.refresh_button.setEnabled(False)
        self._set_pill(self.connection_status, "Carregando catalogo...", "warn")
        self.catalog_worker = CatalogWorker(self.current_base_url())
        self.catalog_worker.succeeded.connect(self._on_catalog_loaded)
        self.catalog_worker.failed.connect(self._on_catalog_error)
        self.catalog_worker.finished.connect(self.catalog_worker.deleteLater)
        self.catalog_worker.start()

    def _on_catalog_loaded(self, models: list[ModelInfo]) -> None:
        self.models = list(models or [])
        self.model_map = {model.id: model for model in self.models}
        self._fill_model_combos()
        chat_count = sum(1 for model in self.models if model.supports_chat)
        image_count = sum(1 for model in self.models if model.supports_image)
        self._set_pill(self.connection_status, "Proxy conectado", "ok")
        self._set_pill(self.catalog_status, f"Modelos {len(self.models)} | chat {chat_count} | img {image_count}", "ok")
        self.connect_button.setEnabled(True)
        self.refresh_button.setEnabled(True)
        self.catalog_worker = None
        self.refresh_ping()

    def _on_catalog_error(self, error: str) -> None:
        self._set_pill(self.connection_status, f"Falha no catalogo ({error[:64]})", "error")
        self._set_pill(self.catalog_status, "Modelos indisponiveis", "error")
        self.connect_button.setEnabled(True)
        self.refresh_button.setEnabled(True)
        self.catalog_worker = None

    def _fill_model_combos(self) -> None:
        desired_chat = str(self.settings.value("chat_model", self.chat_model_combo.currentText()))
        desired_image = str(self.settings.value("image_model", self.image_model_combo.currentText()))

        chat_models = [model for model in self.models if model.supports_chat]
        image_models = [model for model in self.models if model.supports_image]

        self.chat_model_combo.blockSignals(True)
        self.chat_model_combo.clear()
        for model in chat_models:
            self.chat_model_combo.addItem(model.id)
        self.chat_model_combo.blockSignals(False)

        self.image_model_combo.blockSignals(True)
        self.image_model_combo.clear()
        for model in image_models:
            self.image_model_combo.addItem(model.id)
        self.image_model_combo.blockSignals(False)

        if chat_models:
            self._set_combo_text(self.chat_model_combo, desired_chat or chat_models[0].id)
            self._on_chat_model_changed(self.chat_model_combo.currentText())
        if image_models:
            self._set_combo_text(self.image_model_combo, desired_image or image_models[0].id)
            self._on_image_model_changed(self.image_model_combo.currentText())

    def _on_chat_model_changed(self, model_name: str) -> None:
        model = self.model_map.get(model_name)
        if not model:
            self.model_note_label.setText("Modelo nao encontrado no catalogo atual.")
            return
        note_parts = [
            f"Provider: {model.provider or model.owned_by or 'n/d'}",
            f"Capabilities: {format_model_capabilities(model)}",
        ]
        if model.route_model:
            note_parts.append(f"Route model: {model.route_model}")
        if model.note:
            note_parts.append(model.note)
        self.model_note_label.setText(" | ".join(note_parts))

    def _on_image_model_changed(self, model_name: str) -> None:
        rules = image_rules_for_model(model_name)
        default_steps = int(rules.get("default_steps", 8))
        max_steps = int(rules.get("max_steps", 50))
        min_size = int(rules.get("min_size", 768))
        self.image_steps_input.setRange(1, max_steps)
        if self.image_steps_input.value() > max_steps or self.image_steps_input.value() < default_steps:
            self.image_steps_input.setValue(default_steps)
        if int(self.image_width_combo.currentData() or 0) < min_size:
            self._set_combo_value(self.image_width_combo, min_size)
        if int(self.image_height_combo.currentData() or 0) < min_size:
            self._set_combo_value(self.image_height_combo, min_size)

        model = self.model_map.get(model_name)
        note_parts = [
            f"Steps padrao {default_steps} / max {max_steps}",
            f"Tamanho minimo seguro {min_size}px",
        ]
        if model and model.note:
            note_parts.append(model.note)
        self.image_model_note.setText(" | ".join(note_parts))

    def clear_chat(self) -> None:
        self.chat_history = []
        self.pending_assistant_bubble = None
        self.thinking_view.clear()
        self.thinking_status.setText("Nenhum thinking recebido ainda.")
        self.chat_status.setText("Nova conversa iniciada.")
        while self.chat_scroll_layout.count() > 1:
            item = self.chat_scroll_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self._reset_chat_metrics()

    def send_message(self) -> None:
        if self.chat_worker and self.chat_worker.isRunning():
            return
        user_text = self.chat_input.toPlainText().strip()
        if not user_text:
            QMessageBox.information(self, APP_NAME, "Escreva uma pergunta antes de enviar.")
            return
        model_name = self.chat_model_combo.currentText().strip()
        if not model_name:
            QMessageBox.warning(self, APP_NAME, "Escolha um modelo primeiro.")
            return

        self._append_bubble("user", user_text, "", "voce")
        assistant = self._append_bubble("assistant", "", "", "modelo preparando stream...")
        assistant.set_pending(True)
        self.pending_assistant_bubble = assistant
        self.chat_input.clear()
        self.thinking_view.clear()
        self.thinking_status.setText("Aguardando o modelo...")
        self.chat_status.setText("Enviando para o proxy...")
        self.send_button.setEnabled(False)
        self.chat_clear_button.setEnabled(False)

        messages = [*self.chat_history, {"role": "user", "content": user_text}]
        self.chat_worker = ChatWorker(
            base_url=self.current_base_url(),
            model=model_name,
            messages=messages,
            system_prompt=self.system_prompt_input.toPlainText().strip(),
            temperature=self.temperature_input.value(),
            max_tokens=self.max_tokens_input.value(),
        )
        self.chat_worker.delta.connect(self._on_chat_delta)
        self.chat_worker.succeeded.connect(lambda result, prompt=user_text: self._on_chat_success(prompt, result))
        self.chat_worker.failed.connect(self._on_chat_error)
        self.chat_worker.finished.connect(self.chat_worker.deleteLater)
        self.chat_worker.start()

    def _on_chat_delta(self, payload: dict[str, Any]) -> None:
        bubble = self.pending_assistant_bubble
        if bubble is None:
            return
        answer = str(payload.get("answer") or "")
        thinking = str(payload.get("thinking") or "")
        response_model = str(payload.get("response_model") or self.chat_model_combo.currentText())
        first_token_ms = payload.get("first_token_ms")
        bubble.set_content(answer, thinking)
        bubble.set_meta(f"{response_model} | primeiro token {format_ms(first_token_ms)}")
        self.thinking_view.setHtml(rich_text_block(thinking or "Sem thinking ate agora."))
        self.thinking_status.setText("Thinking em tempo real" if thinking else "Streaming sem thinking explicito.")
        self.chat_status.setText("Recebendo resposta...")
        self._scroll_chat_to_bottom()

    def _on_chat_success(self, user_prompt: str, result: ChatResult) -> None:
        self.chat_worker = None
        bubble = self.pending_assistant_bubble
        if bubble is not None:
            bubble.set_pending(False)
            bubble.set_content(result.answer, result.thinking)
            bubble.set_meta(self._bubble_meta_text(result))
        self.pending_assistant_bubble = None
        self.chat_history.append({"role": "user", "content": user_prompt})
        self.chat_history.append({"role": "assistant", "content": result.answer})
        self.chat_status.setText("Resposta recebida com sucesso.")
        self.send_button.setEnabled(True)
        self.chat_clear_button.setEnabled(True)
        self.thinking_view.setHtml(rich_text_block(result.thinking or "Sem thinking retornado pelo modelo."))
        self.thinking_status.setText("Thinking final." if result.thinking else "O modelo nao expos thinking.")
        self._apply_chat_metrics(result)
        self._scroll_chat_to_bottom()

    def _on_chat_error(self, error: str) -> None:
        self.chat_worker = None
        bubble = self.pending_assistant_bubble
        if bubble is not None:
            bubble.set_pending(False)
            bubble.set_error(error)
            bubble.set_meta("falha no request")
        self.pending_assistant_bubble = None
        self.chat_status.setText("Falha ao consultar o modelo.")
        self.send_button.setEnabled(True)
        self.chat_clear_button.setEnabled(True)
        self.thinking_status.setText("Sem thinking por causa do erro.")
        self.thinking_view.setHtml(rich_text_block(error))

    def _bubble_meta_text(self, result: ChatResult) -> str:
        metrics = result.metrics
        return (
            f"{metrics.response_model or '-'} | {format_ms(metrics.total_ms)} | "
            f"{format_tokens_per_second(metrics.tokens_per_second)} | "
            f"comp {format_int(metrics.completion_tokens)} | {metrics.finish_reason or 'stop'}"
        )

    def _apply_chat_metrics(self, result: ChatResult) -> None:
        metrics = result.metrics
        self.metric_cards["response_model"].set_value(metrics.response_model or "-", "modelo real devolvido")
        self.metric_cards["total_ms"].set_value(format_ms(metrics.total_ms), "tempo total da resposta")
        self.metric_cards["first_token_ms"].set_value(format_ms(metrics.first_token_ms), "latencia de arranque")
        self.metric_cards["tokens_per_second"].set_value(format_tokens_per_second(metrics.tokens_per_second), "completion / tempo")
        self.metric_cards["prompt_tokens"].set_value(format_int(metrics.prompt_tokens))
        self.metric_cards["completion_tokens"].set_value(format_int(metrics.completion_tokens))
        self.metric_cards["total_tokens"].set_value(format_int(metrics.total_tokens))
        self.metric_cards["finish_reason"].set_value(metrics.finish_reason or "stop")

    def _reset_chat_metrics(self) -> None:
        for card in self.metric_cards.values():
            card.set_value("-", "")

    def _append_bubble(self, role: str, content: str, thinking: str, meta: str) -> MessageBubble:
        bubble = MessageBubble(role=role, content=content, thinking=thinking)
        bubble.set_meta(meta)
        insert_at = max(0, self.chat_scroll_layout.count() - 1)
        self.chat_scroll_layout.insertWidget(insert_at, bubble)
        self._scroll_chat_to_bottom()
        return bubble

    def _scroll_chat_to_bottom(self) -> None:
        bar = self.chat_scroll.verticalScrollBar()
        bar.setValue(bar.maximum())

    def generate_image(self) -> None:
        if self.image_worker and self.image_worker.isRunning():
            return
        model_name = self.image_model_combo.currentText().strip()
        prompt = self.image_prompt_input.toPlainText().strip()
        if not model_name:
            QMessageBox.warning(self, APP_NAME, "Escolha um modelo de imagem.")
            return
        if not prompt:
            QMessageBox.information(self, APP_NAME, "Escreva um prompt para gerar a imagem.")
            return

        width = int(self.image_width_combo.currentData() or 1024)
        height = int(self.image_height_combo.currentData() or 1024)
        steps = int(self.image_steps_input.value())
        rules = image_rules_for_model(model_name)
        steps = min(steps, int(rules.get("max_steps", 50)))
        steps = max(steps, 1)

        self.image_generate_button.setEnabled(False)
        self.image_save_button.setEnabled(False)
        self.image_status.setText("Gerando imagem pelo proxy...")
        self.image_worker = ImageWorker(
            base_url=self.current_base_url(),
            model=model_name,
            prompt=prompt,
            width=width,
            height=height,
            steps=steps,
            seed=self.image_seed_input.text().strip(),
        )
        self.image_worker.succeeded.connect(self._on_image_success)
        self.image_worker.failed.connect(self._on_image_error)
        self.image_worker.finished.connect(self.image_worker.deleteLater)
        self.image_worker.start()

    def _on_image_success(self, result: ImageResult) -> None:
        self.image_worker = None
        self.current_image_result = result
        image = QImage.fromData(result.image_bytes)
        if image.isNull():
            self._on_image_error("O proxy respondeu, mas o preview veio invalido.")
            return
        pixmap = QPixmap.fromImage(image)
        scaled = pixmap.scaled(
            self.image_preview.size(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        self.image_preview.setPixmap(scaled)
        self.image_preview.setText("")
        self.image_status.setText("Imagem gerada com sucesso.")
        self.image_generate_button.setEnabled(True)
        self.image_save_button.setEnabled(True)
        self.image_metric_cards["image_model"].set_value(result.model)
        self.image_metric_cards["image_duration"].set_value(format_ms(result.duration_ms))
        self.image_metric_cards["image_seed"].set_value(result.seed or "-", "seed final")
        self.image_metric_cards["image_size"].set_value(f"{result.width}x{result.height}", result.mime_type)

    def resizeEvent(self, event: Any) -> None:
        super().resizeEvent(event)
        if self.current_image_result:
            self._on_image_success(self.current_image_result)

    def _on_image_error(self, error: str) -> None:
        self.image_worker = None
        self.image_status.setText(f"Falha na imagem: {error}")
        self.image_generate_button.setEnabled(True)
        self.image_save_button.setEnabled(bool(self.current_image_result))
        QMessageBox.warning(self, APP_NAME, error)

    def save_image(self) -> None:
        if not self.current_image_result:
            QMessageBox.information(self, APP_NAME, "Nenhuma imagem gerada ainda.")
            return
        default_name = f"red-image-{self.current_image_result.seed or 'latest'}.jpg"
        target, _ = QFileDialog.getSaveFileName(
            self,
            "Salvar imagem",
            str(Path.home() / default_name),
            "JPEG (*.jpg *.jpeg);;PNG (*.png);;Todos os arquivos (*)",
        )
        if not target:
            return
        Path(target).write_bytes(self.current_image_result.image_bytes)
        self.image_status.setText(f"Imagem salva em {target}")

    def _set_pill(self, widget: QLabel, text: str, tone: str) -> None:
        widget.setText(text)
        widget.setProperty("tone", tone)
        widget.style().unpolish(widget)
        widget.style().polish(widget)

    @staticmethod
    def _set_combo_text(combo: QComboBox, desired: str) -> None:
        if not desired:
            return
        index = combo.findText(desired, Qt.MatchExactly)
        if index >= 0:
            combo.setCurrentIndex(index)
        elif combo.isEditable():
            combo.setCurrentText(desired)

    @staticmethod
    def _set_combo_value(combo: QComboBox, desired_value: int) -> None:
        index = combo.findData(desired_value)
        if index >= 0:
            combo.setCurrentIndex(index)


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
