from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QSize, QEvent
from PySide6.QtGui import QAction, QIcon, QKeySequence, QShortcut
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QCheckBox,
    QPushButton,
    QSlider,
    QStyle,
    QVBoxLayout,
    QWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QPlainTextEdit,
    QFrame,
)

from .player_controller import VideoPlayerController
from .video_view import VideoView


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("VideoML Editor - Player")
        self.resize(1200, 720)

        self._player_controller = VideoPlayerController(self)
        self._slider_is_active = False
        self._media_loaded = False
        self._frame_rate = 30.0
        self._current_frame = 0
        self._shortcuts: dict[str, QShortcut] = {}
        self._fit_pending = False
        self._saved_frames: list[int] = []
        self._tree_root: QTreeWidgetItem | None = None

        self.setAcceptDrops(True)

        self._build_actions()
        self._build_ui()
        self._connect_signals()
        self._setup_shortcuts()
        self._update_controls_enabled(False)

    # region UI setup
    def _build_actions(self) -> None:
        self._open_action = QAction("Abrir vídeo...", self)
        self._open_action.setShortcut("Ctrl+O")
        self._open_action.setIcon(self.style().standardIcon(QStyle.SP_DirOpenIcon))

        file_menu = self.menuBar().addMenu("Arquivo")
        file_menu.addAction(self._open_action)

    def _build_ui(self) -> None:
        central = QWidget(self)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(8)

        # Left panel: tree of frames/geometries
        left_panel = QVBoxLayout()
        left_panel.setSpacing(6)
        left_label = QLabel("Frames de interesse", self)
        self._frames_tree = QTreeWidget(self)
        self._frames_tree.setHeaderHidden(True)
        self._tree_root = QTreeWidgetItem(["Frames"])
        self._frames_tree.addTopLevelItem(self._tree_root)
        self._frames_tree.expandAll()
        left_panel.addWidget(left_label)
        left_panel.addWidget(self._frames_tree, stretch=1)

        # Center panel: tools, metadata, video, timeline, controls
        center_panel = QVBoxLayout()
        center_panel.setSpacing(8)

        # Tool bar row
        tool_row = QHBoxLayout()
        tool_row.setSpacing(6)
        self._open_btn = QPushButton(self._icon_for_style(QStyle.SP_DirOpenIcon), "", self)
        self._open_btn.setToolTip("Abrir arquivo .mp4 ou .avi")
        self._hand_btn = QPushButton(self._icon_for_style(QStyle.SP_ArrowUp), "", self)
        self._hand_btn.setCheckable(True)
        self._hand_btn.setToolTip("Mover o vídeo quando houver zoom")
        self._loop_checkbox = QCheckBox("Loop", self)
        self._loop_checkbox.setToolTip("Repetir vídeo ao finalizar")
        for button in (self._open_btn, self._hand_btn):
            button.setIconSize(QSize(20, 20))
            button.setMaximumWidth(34)
        tool_row.addWidget(self._open_btn)
        tool_row.addWidget(self._hand_btn)
        tool_row.addWidget(self._loop_checkbox)
        tool_row.addStretch(1)
        center_panel.addLayout(tool_row)

        # Metadata row (above the video)
        meta_row = QHBoxLayout()
        meta_row.setSpacing(10)
        self._file_label = QLabel("Vídeo: Nenhum arquivo", self)
        self._time_label = QLabel("00:00.000 / 00:00.000", self)
        self._fps_label = QLabel("FPS: 0.00", self)
        self._frame_label = QLabel("Frame: 0", self)
        meta_row.addWidget(self._file_label, stretch=2)
        meta_row.addWidget(self._time_label, stretch=1)
        meta_row.addWidget(self._fps_label, stretch=0)
        meta_row.addWidget(self._frame_label, stretch=0)
        center_panel.addLayout(meta_row)

        # Video view
        self._video_view = VideoView(self)
        self._video_view.setAcceptDrops(True)
        self._video_view.installEventFilter(self)
        center_panel.addWidget(self._video_view, stretch=1)

        # Timeline slider row
        slider_row = QHBoxLayout()
        slider_row.setSpacing(12)
        self._position_slider = QSlider(Qt.Horizontal, self)
        self._position_slider.setRange(0, 0)
        self._position_slider.setSingleStep(1000 // 30)  # approx. 1 frame at 30fps
        slider_row.addWidget(self._position_slider, stretch=1)
        center_panel.addLayout(slider_row)

        # Playback controls row
        controls_layout = QHBoxLayout()
        controls_layout.setSpacing(8)
        self._start_btn = QPushButton(self._icon_for_style(QStyle.SP_MediaSkipBackward), "", self)
        self._back_frame_btn = QPushButton(self._icon_for_style(QStyle.SP_MediaSeekBackward), "", self)
        self._play_btn = QPushButton(self._icon_for_style(QStyle.SP_MediaPlay), "", self)
        self._forward_frame_btn = QPushButton(self._icon_for_style(QStyle.SP_MediaSeekForward), "", self)
        self._end_btn = QPushButton(self._icon_for_style(QStyle.SP_MediaSkipForward), "", self)
        self._save_frame_btn = QPushButton(self._icon_for_style(QStyle.SP_DialogSaveButton), "", self)

        for button in (
            self._start_btn,
            self._back_frame_btn,
            self._play_btn,
            self._forward_frame_btn,
            self._end_btn,
        ):
            button.setIconSize(QSize(26, 26))
            button.setFixedSize(42, 32)

        self._save_frame_btn.setIconSize(QSize(22, 22))
        self._save_frame_btn.setFixedSize(120, 32)

        self._start_btn.setToolTip("Início")
        self._back_frame_btn.setToolTip("Frame anterior")
        self._play_btn.setToolTip("Reproduzir/Pausar")
        self._forward_frame_btn.setToolTip("Próximo frame")
        self._end_btn.setToolTip("Fim")
        self._save_frame_btn.setToolTip("Salvar frame de interesse")

        controls_layout.addStretch(1)
        controls_layout.addWidget(self._start_btn)
        controls_layout.addWidget(self._back_frame_btn)
        controls_layout.addWidget(self._play_btn)
        controls_layout.addWidget(self._forward_frame_btn)
        controls_layout.addWidget(self._end_btn)
        controls_layout.addStretch(1)
        controls_layout.addWidget(self._save_frame_btn)
        center_panel.addLayout(controls_layout)

        # Right panel: properties
        right_panel = QVBoxLayout()
        right_panel.setSpacing(6)
        prop_label = QLabel("Propriedades", self)
        self._prop_view = QPlainTextEdit(self)
        self._prop_view.setReadOnly(True)
        self._prop_view.setFrameShape(QFrame.StyledPanel)
        right_panel.addWidget(prop_label)
        right_panel.addWidget(self._prop_view, stretch=1)

        # assemble
        main_layout.addLayout(left_panel, stretch=2)
        main_layout.addLayout(center_panel, stretch=5)
        main_layout.addLayout(right_panel, stretch=3)

        self.setCentralWidget(central)
        self.setStatusBar(self.statusBar())

        self._player_controller.set_video_output(self._video_view.video_item)
        self._update_properties("Nenhum item selecionado")

    def _icon_for_style(self, style_constant: QStyle.StandardPixmap) -> QIcon:
        return self.style().standardIcon(style_constant)

    # endregion

    # region Signal wiring
    def _connect_signals(self) -> None:
        self._open_action.triggered.connect(self._open_file_dialog)
        self._open_btn.clicked.connect(self._open_file_dialog)

        self._start_btn.clicked.connect(lambda: self._player_controller.set_position(0))
        self._back_frame_btn.clicked.connect(lambda: self._player_controller.skip_frames(-1))
        self._forward_frame_btn.clicked.connect(lambda: self._player_controller.skip_frames(1))
        self._end_btn.clicked.connect(self._seek_to_end)
        self._play_btn.clicked.connect(self._toggle_play_pause)
        self._hand_btn.toggled.connect(self._video_view.set_hand_mode)
        self._loop_checkbox.toggled.connect(self._player_controller.set_looping)
        self._save_frame_btn.clicked.connect(self._save_current_frame)
        self._frames_tree.itemClicked.connect(self._on_tree_item_clicked)

        self._position_slider.sliderPressed.connect(self._on_slider_pressed)
        self._position_slider.sliderReleased.connect(self._on_slider_released)
        self._position_slider.sliderMoved.connect(self._on_slider_moved)

        self._player_controller.position_changed.connect(self._on_position_changed)
        self._player_controller.duration_changed.connect(self._on_duration_changed)
        self._player_controller.playback_state_changed.connect(self._on_playback_state_changed)
        self._player_controller.frame_rate_changed.connect(self._on_frame_rate_changed)
        self._player_controller.error_occurred.connect(self._on_error)
        self._player_controller.media_status_changed.connect(self._on_media_status_changed)

    def _setup_shortcuts(self) -> None:
        """Create default shortcuts and allow later reconfiguration."""
        default_map = {
            "toggle_play_pause": QKeySequence(Qt.Key_Space),
            "frame_forward": QKeySequence(Qt.Key_Right),
            "frame_back": QKeySequence(Qt.Key_Left),
        }
        self.configure_shortcuts(default_map)

    # endregion

    # region Slots
    def _open_file_dialog(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Selecione um vídeo",
            str(Path.home()),
            "Vídeos (*.mp4 *.avi);;Todos os arquivos (*.*)",
        )
        if not file_path:
            return

        self._load_video(Path(file_path))

    def _load_video(self, path: Path) -> None:
        self._player_controller.pause()
        self._player_controller.load(path)
        self._position_slider.setValue(0)
        self._time_label.setText("00:00.000 / 00:00.000")
        self._media_loaded = True
        self._fit_pending = True
        self._saved_frames.clear()
        if self._tree_root:
            self._tree_root.takeChildren()
        self._update_controls_enabled(True)
        self._play_btn.setText("Play")
        self._play_btn.setIcon(self._icon_for_style(QStyle.SP_MediaPlay))
        # Keep loop checkbox state as user preference; just re-apply to controller
        self._player_controller.set_looping(self._loop_checkbox.isChecked())
        self.setWindowTitle(f"VideoML Editor - {path.name}")
        self._file_label.setText(f"Vídeo: {path.name}")
        self._update_frame_label(0)
        self._update_properties("Nenhum item selecionado")

    def _on_position_changed(self, position_ms: int) -> None:
        if not self._slider_is_active:
            self._position_slider.setValue(position_ms)
        self._update_time_label(position_ms, self._position_slider.maximum())
        self._update_frame_label(position_ms)

    def _on_duration_changed(self, duration_ms: int) -> None:
        self._position_slider.setRange(0, max(0, duration_ms))
        self._media_loaded = duration_ms > 0
        self._update_controls_enabled(self._media_loaded)
        self._update_time_label(self._position_slider.value(), duration_ms)

    def _on_playback_state_changed(self, state: QMediaPlayer.PlaybackState) -> None:
        is_playing = state == QMediaPlayer.PlayingState
        self._play_btn.setEnabled(self._media_loaded)
        self._play_btn.setText("Pause" if is_playing else "Play")
        self._play_btn.setIcon(self._icon_for_style(QStyle.SP_MediaPause if is_playing else QStyle.SP_MediaPlay))
        status_text = "Reproduzindo" if is_playing else "Pausado"
        self.statusBar().showMessage(status_text, 2000)

    def _on_frame_rate_changed(self, frame_rate: float) -> None:
        if frame_rate > 0:
            self._frame_rate = frame_rate
        single_step = max(1, int(1000 / frame_rate))
        self._position_slider.setSingleStep(single_step)
        self._fps_label.setText(f"FPS: {frame_rate:.2f}")
        self.statusBar().showMessage(f"Taxa de frames: {frame_rate:.2f} fps")

    def _on_media_status_changed(self, status: QMediaPlayer.MediaStatus) -> None:
        if status == QMediaPlayer.InvalidMedia:
            self._handle_invalid_media()
        elif status in (QMediaPlayer.BufferedMedia, QMediaPlayer.LoadedMedia):
            if self._fit_pending:
                if self._video_view.reset_view():
                    self._fit_pending = False

    def _on_error(self, message: str) -> None:
        self._media_loaded = False
        self._fit_pending = False
        self._saved_frames.clear()
        if self._tree_root:
            self._tree_root.takeChildren()
        self._update_properties("Nenhum item selecionado")
        self._update_controls_enabled(False)
        QMessageBox.critical(self, "Erro ao carregar vídeo", message)

    def _on_slider_pressed(self) -> None:
        self._slider_is_active = True

    def _on_slider_released(self) -> None:
        self._slider_is_active = False
        self._player_controller.set_position(self._position_slider.value())

    def _on_slider_moved(self, value: int) -> None:
        if self._media_loaded:
            self._player_controller.set_position(value)
            self._update_time_label(value, self._position_slider.maximum())
            self._update_frame_label(value)

    # endregion

    # region Helpers
    def _update_controls_enabled(self, enabled: bool) -> None:
        self._back_frame_btn.setEnabled(enabled)
        self._forward_frame_btn.setEnabled(enabled)
        self._play_btn.setEnabled(enabled)
        self._hand_btn.setEnabled(enabled)
        self._start_btn.setEnabled(enabled)
        self._end_btn.setEnabled(enabled)
        self._loop_checkbox.setEnabled(True)  # allow toggling even without media
        self._save_frame_btn.setEnabled(enabled)
        self._frames_tree.setEnabled(enabled or bool(self._saved_frames))
        if not enabled:
            self._hand_btn.setChecked(False)
            self._video_view.set_hand_mode(False)
        self._position_slider.setEnabled(enabled)

    def _update_time_label(self, position_ms: int, duration_ms: int) -> None:
        position_text = self._ms_to_timestamp(position_ms)
        duration_text = self._ms_to_timestamp(duration_ms)
        self._time_label.setText(f"{position_text} / {duration_text}")

    def _update_frame_label(self, position_ms: int) -> None:
        if self._frame_rate <= 0:
            self._frame_rate = 30.0
        frame = int(round(position_ms / (1000.0 / self._frame_rate)))
        self._current_frame = frame
        self._frame_label.setText(f"Frame: {frame}")
        if not self._has_selected_interest():
            self._update_properties(f"Frame atual: {frame}")

    def _save_current_frame(self) -> None:
        if not self._media_loaded:
            return
        frame = self._current_frame
        if frame < 0:
            return
        if frame not in self._saved_frames:
            self._saved_frames.append(frame)
            self._add_frame_to_tree(frame)

    def _add_frame_to_tree(self, frame: int) -> None:
        if not self._tree_root:
            return
        item = QTreeWidgetItem([f"Frame {frame}"])
        item.setData(0, Qt.UserRole, frame)
        self._tree_root.addChild(item)
        self._frames_tree.expandAll()

    def _on_tree_item_clicked(self, item: QTreeWidgetItem) -> None:
        frame = item.data(0, Qt.UserRole)
        if frame is None:
            self._update_properties("Nenhum item selecionado")
            return
        if not self._media_loaded:
            return
        position_ms = self._frame_to_ms(int(frame))
        self._player_controller.set_position(position_ms)
        self._update_frame_label(position_ms)
        self._update_time_label(position_ms, self._position_slider.maximum())
        self._update_properties(f"Frame: {frame}")

    def _is_supported_video(self, path: Path) -> bool:
        return path.suffix.lower() in {".mp4", ".avi"}

    def _handle_drag_enter(self, event) -> bool:
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if self._is_supported_video(Path(url.toLocalFile())):
                    event.acceptProposedAction()
                    return True
        event.ignore()
        return False

    def _handle_drop(self, event) -> bool:
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                path = Path(url.toLocalFile())
                if self._is_supported_video(path):
                    self._load_video(path)
                    event.acceptProposedAction()
                    return True
        event.ignore()
        return False

    def dragEnterEvent(self, event) -> None:
        if self._handle_drag_enter(event):
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:
        if self._handle_drag_enter(event):
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event) -> None:
        if self._handle_drop(event):
            return
        super().dropEvent(event)

    def _toggle_play_pause(self) -> None:
        if self._player_controller.is_playing():
            self._player_controller.pause()
        else:
            self._player_controller.play()

    def configure_shortcuts(self, mapping: dict[str, QKeySequence | str]) -> None:
        """Configure keyboard shortcuts for main actions.

        Supported keys in mapping: toggle_play_pause, frame_forward, frame_back.
        """
        actions = {
            "toggle_play_pause": self._toggle_play_pause,
            "frame_forward": lambda: self._player_controller.skip_frames(1),
            "frame_back": lambda: self._player_controller.skip_frames(-1),
        }

        for key, handler in actions.items():
            if key not in mapping:
                continue
            sequence = mapping[key]
            if isinstance(sequence, str):
                sequence = QKeySequence(sequence)

            shortcut = self._shortcuts.get(key)
            if shortcut is None:
                shortcut = QShortcut(sequence, self)
                shortcut.activated.connect(handler)
                self._shortcuts[key] = shortcut
            else:
                shortcut.setKey(sequence)

    def eventFilter(self, obj, event):
        if obj is self._video_view and event.type() in (QEvent.DragEnter, QEvent.DragMove, QEvent.Drop):
            if event.type() in (QEvent.DragEnter, QEvent.DragMove):
                return self._handle_drag_enter(event)
            if event.type() == QEvent.Drop:
                return self._handle_drop(event)
        return super().eventFilter(obj, event)

    def _ms_to_timestamp(self, value_ms: int) -> str:
        total_seconds = value_ms // 1000
        minutes = total_seconds // 60
        seconds = total_seconds % 60
        millis = value_ms % 1000
        return f"{minutes:02d}:{seconds:02d}.{millis:03d}"

    def _frame_to_ms(self, frame: int) -> int:
        if self._frame_rate <= 0:
            self._frame_rate = 30.0
        return int(round(frame * (1000.0 / self._frame_rate)))

    def _update_properties(self, text: str) -> None:
        self._prop_view.setPlainText(text)

    def _seek_to_end(self) -> None:
        duration = self._position_slider.maximum()
        if duration > 0:
            self._player_controller.set_position(duration)
            self._update_time_label(duration, duration)
            self._update_frame_label(duration)

    def _has_selected_interest(self) -> bool:
        item = self._frames_tree.currentItem()
        if not item:
            return False
        return item.data(0, Qt.UserRole) is not None

    def _handle_invalid_media(self) -> None:
        self._media_loaded = False
        self._fit_pending = False
        self._saved_frames.clear()
        if self._tree_root:
            self._tree_root.takeChildren()
        self._update_properties("Nenhum item selecionado")
        self._update_controls_enabled(False)
        QMessageBox.warning(
            self,
            "Vídeo inválido",
            "Não foi possível carregar este arquivo. Verifique o formato (MP4 ou AVI) e tente novamente.",
        )

    # endregion
