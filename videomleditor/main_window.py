from __future__ import annotations

from pathlib import Path
import math

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
    QButtonGroup,
    QInputDialog,
    QMenu,
    QWidgetAction,
    QSpinBox,
    QColorDialog,
)

from PySide6.QtGui import QColor

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
        self._saved_frames: list[dict[str, int | str | None]] = []
        self._tree_root: QTreeWidgetItem | None = None
        
        # Point tool settings
        self._point_size: int = 3
        self._point_color: QColor = QColor("yellow")

        # Line tool settings
        self._line_width: int = 2
        self._line_color: QColor = QColor("yellow")
        self._line_guide_enabled: bool = False

        # Angle tool settings
        self._angle_width: int = 2
        self._angle_color: QColor = QColor("yellow")

        # Annotations storage: {frame_number: [{"type": "point", "x": float, "y": float, "size": int, "color": QColor, "name": str | None}, ...]}
        self._annotations: dict[int, list[dict]] = {}
        self._annotation_counter: dict[str, int] = {"point": 0, "line": 0, "angle": 0, "freehand": 0, "brush": 0}

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
        left_header = QHBoxLayout()
        left_header.setSpacing(4)
        left_label = QLabel("Frames de interesse", self)
        self._edit_frame_btn = QPushButton("✏", self)
        self._edit_frame_btn.setFixedSize(28, 24)
        self._edit_frame_btn.setToolTip("Renomear frame selecionado")
        self._delete_frame_btn = QPushButton("🗑", self)
        self._delete_frame_btn.setFixedSize(28, 24)
        self._delete_frame_btn.setToolTip("Remover frame selecionado")
        left_header.addWidget(left_label)
        left_header.addStretch(1)
        left_header.addWidget(self._edit_frame_btn)
        left_header.addWidget(self._delete_frame_btn)
        self._frames_tree = QTreeWidget(self)
        self._frames_tree.setHeaderHidden(True)
        self._tree_root = QTreeWidgetItem(["Frames"])
        self._frames_tree.addTopLevelItem(self._tree_root)
        self._frames_tree.expandAll()
        left_panel.addLayout(left_header)
        left_panel.addWidget(self._frames_tree, stretch=1)

        # Center panel: tools, metadata, video, timeline, controls
        center_panel = QVBoxLayout()
        center_panel.setSpacing(8)

        # Open row centered above toolbar
        self._open_btn = QPushButton(self._icon_for_style(QStyle.SP_DirOpenIcon), "Abrir vídeo", self)
        self._open_btn.setToolTip("Abrir arquivo .mp4 ou .avi")
        self._open_btn.setIconSize(QSize(22, 22))
        self._open_btn.setMinimumWidth(120)
        open_row = QHBoxLayout()
        open_row.addStretch(1)
        open_row.addWidget(self._open_btn)
        open_row.addStretch(1)
        center_panel.addLayout(open_row)

        # Tool bar row (selection + hand + geometry tools)
        tool_row = QHBoxLayout()
        tool_row.setSpacing(6)
        self._selection_btn = QPushButton("🖱", self)
        self._selection_btn.setCheckable(True)
        self._selection_btn.setToolTip("Seleção (cursor)")
        self._hand_btn = QPushButton("✋", self)
        self._hand_btn.setCheckable(True)
        self._hand_btn.setToolTip("Mover o vídeo quando houver zoom")

        # Geometry tools
        self._point_btn = QPushButton("●", self)
        self._point_btn.setCheckable(True)
        self._point_btn.setToolTip("Desenhar ponto (clique direito para configurar)")
        self._point_btn.setContextMenuPolicy(Qt.CustomContextMenu)
        self._point_btn.customContextMenuRequested.connect(self._show_point_context_menu)
        
        self._line_btn = QPushButton("╱", self)
        self._line_btn.setCheckable(True)
        self._line_btn.setToolTip("Desenhar reta (clique direito para configurar)")
        self._line_btn.setContextMenuPolicy(Qt.CustomContextMenu)
        self._line_btn.customContextMenuRequested.connect(self._show_line_context_menu)
        
        self._angle_btn = QPushButton("∠", self)
        self._angle_btn.setCheckable(True)
        self._angle_btn.setToolTip("Desenhar ângulo (clique direito para configurar)\nSegure Shift para ângulo de 90°")
        self._angle_btn.setContextMenuPolicy(Qt.CustomContextMenu)
        self._angle_btn.customContextMenuRequested.connect(self._show_angle_context_menu)
        
        self._freehand_btn = QPushButton("◌", self)
        self._freehand_btn.setCheckable(True)
        self._freehand_btn.setToolTip("Máscara free hand")
        
        self._brush_btn = QPushButton("🖌", self)
        self._brush_btn.setCheckable(True)
        self._brush_btn.setToolTip("Brush")

        for button in (
            self._selection_btn,
            self._hand_btn,
            self._point_btn,
            self._line_btn,
            self._angle_btn,
            self._freehand_btn,
            self._brush_btn,
        ):
            button.setIconSize(QSize(20, 20))
            button.setMaximumWidth(36)

        self._tool_group = QButtonGroup(self)
        self._tool_group.setExclusive(True)
        self._tool_group.addButton(self._selection_btn)
        self._tool_group.addButton(self._hand_btn)
        self._tool_group.addButton(self._point_btn)
        self._tool_group.addButton(self._line_btn)
        self._tool_group.addButton(self._angle_btn)
        self._tool_group.addButton(self._freehand_btn)
        self._tool_group.addButton(self._brush_btn)
        self._selection_btn.setChecked(True)

        tool_row.addStretch(1)
        tool_row.addWidget(self._selection_btn)
        tool_row.addWidget(self._hand_btn)

        # Separador visual entre navegação e geometria
        tool_separator = QFrame(self)
        tool_separator.setFrameShape(QFrame.VLine)
        tool_separator.setFrameShadow(QFrame.Sunken)
        tool_row.addWidget(tool_separator)

        tool_row.addWidget(self._point_btn)
        tool_row.addWidget(self._line_btn)
        tool_row.addWidget(self._angle_btn)
        tool_row.addWidget(self._freehand_btn)
        tool_row.addWidget(self._brush_btn)
        tool_row.addStretch(1)
        center_panel.addLayout(tool_row)

        # Metadata row (above the video)
        meta_row = QHBoxLayout()
        meta_row.setSpacing(10)
        self._file_label = QLabel("Vídeo: Nenhum arquivo", self)
        self._angle_display_label = QLabel("", self)  # Shows angle during drawing
        self._angle_display_label.setStyleSheet("color: #FF9800; font-weight: bold;")
        self._angle_display_label.setVisible(False)
        self._time_label = QLabel("00:00.000 / 00:00.000", self)
        self._fps_label = QLabel("FPS: 0.00", self)
        self._frame_label = QLabel("Frame: 0", self)
        meta_row.addWidget(self._file_label, stretch=2)
        meta_row.addWidget(self._angle_display_label, stretch=0)
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
        self._loop_checkbox = QCheckBox("Loop", self)
        self._loop_checkbox.setToolTip("Repetir vídeo ao finalizar")
        self._start_btn = QPushButton(self._icon_for_style(QStyle.SP_MediaSkipBackward), "", self)
        self._back_frame_btn = QPushButton(self._icon_for_style(QStyle.SP_MediaSeekBackward), "", self)
        self._play_btn = QPushButton(self._icon_for_style(QStyle.SP_MediaPlay), "", self)
        self._forward_frame_btn = QPushButton(self._icon_for_style(QStyle.SP_MediaSeekForward), "", self)
        self._end_btn = QPushButton(self._icon_for_style(QStyle.SP_MediaSkipForward), "", self)
        self._save_frame_btn = QPushButton(self._icon_for_style(QStyle.SP_DialogSaveButton), "Salvar frame", self)

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

        controls_layout.addWidget(self._loop_checkbox)
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
        self._hand_btn.toggled.connect(self._on_hand_toggled)
        self._selection_btn.toggled.connect(self._on_selection_toggled)
        self._point_btn.toggled.connect(self._on_point_toggled)
        self._line_btn.toggled.connect(self._on_line_toggled)
        self._angle_btn.toggled.connect(self._on_angle_toggled)

        # Video view line completion
        self._video_view.line_completed.connect(self._on_line_completed)

        # Video view angle signals
        self._video_view.angle_completed.connect(self._on_angle_completed)
        self._video_view.angle_preview_changed.connect(self._on_angle_preview_changed)
        
        self._loop_checkbox.toggled.connect(self._player_controller.set_looping)
        self._save_frame_btn.clicked.connect(self._save_current_frame)
        self._frames_tree.itemClicked.connect(self._on_tree_item_clicked)
        self._edit_frame_btn.clicked.connect(self._rename_selected_frame)
        self._delete_frame_btn.clicked.connect(self._delete_selected_frame)

        # Video view click for annotations
        self._video_view.annotation_requested.connect(self._on_annotation_requested)

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
        self._play_btn.setIcon(self._icon_for_style(QStyle.SP_MediaPlay))
        self._selection_btn.setChecked(True)
        # Keep loop checkbox state as user preference; just re-apply to controller
        self._player_controller.set_looping(self._loop_checkbox.isChecked())
        self.setWindowTitle(f"VideoML Editor - {path.name}")
        self._file_label.setText(f"Vídeo: {path.name}")
        self._update_frame_label(0)
        self._update_properties("Nenhum item selecionado")
        self._update_interest_actions_enabled()

    def _on_position_changed(self, position_ms: int) -> None:
        if not self._slider_is_active:
            self._position_slider.setValue(position_ms)
        self._update_time_label(position_ms, self._position_slider.maximum())
        self._update_frame_label(position_ms)
        
        # Update visible annotations for current frame
        self._video_view.set_annotations(self._annotations.get(self._current_frame, []))

    def _on_duration_changed(self, duration_ms: int) -> None:
        self._position_slider.setRange(0, max(0, duration_ms))
        self._media_loaded = duration_ms > 0
        self._update_controls_enabled(self._media_loaded)
        self._update_time_label(self._position_slider.value(), duration_ms)

    def _on_playback_state_changed(self, state: QMediaPlayer.PlaybackState) -> None:
        is_playing = state == QMediaPlayer.PlayingState
        self._play_btn.setEnabled(self._media_loaded)
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
            if self._selection_btn.isChecked():
                self._update_properties(f"Frame atual: {self._current_frame}")

    def _show_point_context_menu(self, pos) -> None:
        """Show context menu for point tool configuration."""
        menu = QMenu(self)
        
        # Size configuration
        size_label = QLabel("  Tamanho: ")
        size_spinbox = QSpinBox()
        size_spinbox.setRange(1, 50)
        size_spinbox.setValue(self._point_size)
        size_spinbox.valueChanged.connect(lambda val: setattr(self, '_point_size', val))
        
        size_layout = QHBoxLayout()
        size_layout.addWidget(size_label)
        size_layout.addWidget(size_spinbox)
        size_layout.setContentsMargins(4, 4, 4, 4)
        
        size_widget = QWidget()
        size_widget.setLayout(size_layout)
        
        size_action = QWidgetAction(menu)
        size_action.setDefaultWidget(size_widget)
        menu.addAction(size_action)
        
        menu.addSeparator()
        
        # Color configuration
        color_action = menu.addAction("  Escolher cor...")
        color_action.triggered.connect(self._choose_point_color)
        
        # Color preview
        preview_label = QLabel(f"  Cor atual: ")
        preview_box = QLabel("    ")
        preview_box.setStyleSheet(f"background-color: {self._point_color.name()}; border: 1px solid black;")
        
        preview_layout = QHBoxLayout()
        preview_layout.addWidget(preview_label)
        preview_layout.addWidget(preview_box)
        preview_layout.addStretch()
        preview_layout.setContentsMargins(4, 4, 4, 4)
        
        preview_widget = QWidget()
        preview_widget.setLayout(preview_layout)
        
        preview_action = QWidgetAction(menu)
        preview_action.setDefaultWidget(preview_widget)
        menu.addAction(preview_action)
        
        menu.exec(self._point_btn.mapToGlobal(pos))

    def _choose_point_color(self) -> None:
        """Open color dialog to choose point color."""
        color = QColorDialog.getColor(self._point_color, self, "Escolher cor do ponto")
        if color.isValid():
            self._point_color = color

    def _show_line_context_menu(self, pos) -> None:
        """Show context menu for line tool configuration."""
        menu = QMenu(self)
        
        # Guide line checkbox
        guide_checkbox = QCheckBox("  Linha Guia")
        guide_checkbox.setChecked(self._line_guide_enabled)
        guide_checkbox.toggled.connect(self._on_line_guide_toggled)
        
        guide_action = QWidgetAction(menu)
        guide_action.setDefaultWidget(guide_checkbox)
        menu.addAction(guide_action)
        
        menu.addSeparator()
        
        # Width configuration
        width_label = QLabel("  Espessura: ")
        width_spinbox = QSpinBox()
        width_spinbox.setRange(1, 20)
        width_spinbox.setValue(self._line_width)
        width_spinbox.valueChanged.connect(lambda val: setattr(self, '_line_width', val))
        
        width_layout = QHBoxLayout()
        width_layout.addWidget(width_label)
        width_layout.addWidget(width_spinbox)
        width_layout.setContentsMargins(4, 4, 4, 4)
        
        width_widget = QWidget()
        width_widget.setLayout(width_layout)
        
        width_action = QWidgetAction(menu)
        width_action.setDefaultWidget(width_widget)
        menu.addAction(width_action)
        
        menu.addSeparator()
        
        # Color configuration
        color_action = menu.addAction("  Escolher cor...")
        color_action.triggered.connect(self._choose_line_color)
        
        # Color preview
        preview_label = QLabel("  Cor atual: ")
        preview_box = QLabel("    ")
        preview_box.setStyleSheet(f"background-color: {self._line_color.name()}; border: 1px solid black;")
        
        preview_layout = QHBoxLayout()
        preview_layout.addWidget(preview_label)
        preview_layout.addWidget(preview_box)
        preview_layout.addStretch()
        preview_layout.setContentsMargins(4, 4, 4, 4)
        
        preview_widget = QWidget()
        preview_widget.setLayout(preview_layout)
        
        preview_action = QWidgetAction(menu)
        preview_action.setDefaultWidget(preview_widget)
        menu.addAction(preview_action)
        
        menu.exec(self._line_btn.mapToGlobal(pos))

    def _on_line_guide_toggled(self, checked: bool) -> None:
        """Toggle line guide preview."""
        self._line_guide_enabled = checked
        self._video_view.set_line_guide_enabled(checked)

    def _choose_line_color(self) -> None:
        """Open color dialog to choose line color."""
        color = QColorDialog.getColor(self._line_color, self, "Escolher cor da reta")
        if color.isValid():
            self._line_color = color
            self._video_view.set_line_preview_style(self._line_color, self._line_width)

    def _show_angle_context_menu(self, pos) -> None:
        """Show context menu for angle tool configuration."""
        menu = QMenu(self)
        
        # Width configuration
        width_label = QLabel("  Espessura: ")
        width_spinbox = QSpinBox()
        width_spinbox.setRange(1, 20)
        width_spinbox.setValue(self._angle_width)
        width_spinbox.valueChanged.connect(lambda val: setattr(self, '_angle_width', val))
        
        width_layout = QHBoxLayout()
        width_layout.addWidget(width_label)
        width_layout.addWidget(width_spinbox)
        width_layout.setContentsMargins(4, 4, 4, 4)
        
        width_widget = QWidget()
        width_widget.setLayout(width_layout)
        
        width_action = QWidgetAction(menu)
        width_action.setDefaultWidget(width_widget)
        menu.addAction(width_action)
        
        menu.addSeparator()
        
        # Color configuration
        color_action = menu.addAction("  Escolher cor...")
        color_action.triggered.connect(self._choose_angle_color)
        
        # Color preview
        preview_label = QLabel("  Cor atual: ")
        preview_box = QLabel("    ")
        preview_box.setStyleSheet(f"background-color: {self._angle_color.name()}; border: 1px solid black;")
        
        preview_layout = QHBoxLayout()
        preview_layout.addWidget(preview_label)
        preview_layout.addWidget(preview_box)
        preview_layout.addStretch()
        preview_layout.setContentsMargins(4, 4, 4, 4)
        
        preview_widget = QWidget()
        preview_widget.setLayout(preview_layout)
        
        preview_action = QWidgetAction(menu)
        preview_action.setDefaultWidget(preview_widget)
        menu.addAction(preview_action)
        
        menu.exec(self._angle_btn.mapToGlobal(pos))

    def _choose_angle_color(self) -> None:
        """Open color dialog to choose angle color."""
        color = QColorDialog.getColor(self._angle_color, self, "Escolher cor do ângulo")
        if color.isValid():
            self._angle_color = color
            self._video_view.set_angle_preview_style(self._angle_color, self._angle_width)

    def _on_annotation_requested(self, x: float, y: float) -> None:
        """Handle click on video view to create annotation based on active tool."""
        if not self._media_loaded:
            return
        
        if self._point_btn.isChecked():
            self._create_point_annotation(x, y)

    def _create_point_annotation(self, x: float, y: float) -> None:
        """Create a point annotation at the given video coordinates."""
        frame = self._current_frame
        
        # Ensure frame exists in saved_frames
        if not any(entry["frame"] == frame for entry in self._saved_frames):
            self._saved_frames.append({"frame": frame, "name": None})
            self._saved_frames.sort(key=lambda e: e["frame"])
        
        # Initialize annotations list for this frame if needed
        if frame not in self._annotations:
            self._annotations[frame] = []
        
        # Increment counter and create annotation
        self._annotation_counter["point"] += 1
        annotation = {
            "type": "point",
            "x": x,
            "y": y,
            "size": self._point_size,
            "color": QColor(self._point_color),  # Copy to preserve current settings
            "name": None,
            "id": self._annotation_counter["point"],
        }
        self._annotations[frame].append(annotation)
        
        # Update tree and video view
        self._rebuild_frames_tree()
        self._video_view.set_annotations(self._annotations.get(frame, []))

    def _on_line_completed(self, x1: float, y1: float, x2: float, y2: float) -> None:
        """Handle line completion from video view."""
        if not self._media_loaded:
            return
        self._create_line_annotation(x1, y1, x2, y2)

    def _create_line_annotation(self, x1: float, y1: float, x2: float, y2: float) -> None:
        """Create a line annotation with the given coordinates."""
        frame = self._current_frame
        
        # Ensure frame exists in saved_frames
        if not any(entry["frame"] == frame for entry in self._saved_frames):
            self._saved_frames.append({"frame": frame, "name": None})
            self._saved_frames.sort(key=lambda e: e["frame"])
        
        # Initialize annotations list for this frame if needed
        if frame not in self._annotations:
            self._annotations[frame] = []
        
        # Increment counter and create annotation
        self._annotation_counter["line"] += 1
        annotation = {
            "type": "line",
            "x1": x1,
            "y1": y1,
            "x2": x2,
            "y2": y2,
            "width": self._line_width,
            "color": QColor(self._line_color),  # Copy to preserve current settings
            "name": None,
            "id": self._annotation_counter["line"],
        }
        self._annotations[frame].append(annotation)
        
        # Update tree and video view
        self._rebuild_frames_tree()
        self._video_view.set_annotations(self._annotations.get(frame, []))
    
    def _on_angle_completed(self, x1: float, y1: float, x2: float, y2: float, x3: float, y3: float) -> None:
        """Handle angle completion from video view."""
        if not self._media_loaded:
            return
        self._create_angle_annotation(x1, y1, x2, y2, x3, y3)
        # Hide angle display after creation
        self._angle_display_label.setVisible(False)

    def _on_angle_preview_changed(self, angle: float) -> None:
        """Handle angle preview update during drawing."""
        if angle < 0:
            # -1 signals that no angle is being drawn
            self._angle_display_label.setVisible(False)
        else:
            self._angle_display_label.setText(f"∠ {angle:.4f}°")
            self._angle_display_label.setVisible(True)

    def _create_angle_annotation(self, x1: float, y1: float, x2: float, y2: float, x3: float, y3: float) -> None:
        """Create an angle annotation with the given coordinates."""
        frame = self._current_frame
        
        # Ensure frame exists in saved_frames
        if not any(entry["frame"] == frame for entry in self._saved_frames):
            self._saved_frames.append({"frame": frame, "name": None})
            self._saved_frames.sort(key=lambda e: e["frame"])
        
        # Initialize annotations list for this frame if needed
        if frame not in self._annotations:
            self._annotations[frame] = []
        
        # Calculate the angle
        angle = self._calculate_angle_degrees(x1, y1, x2, y2, x3, y3)
        
        # Increment counter and create annotation
        self._annotation_counter["angle"] += 1
        annotation = {
            "type": "angle",
            "x1": x1,
            "y1": y1,
            "x2": x2,
            "y2": y2,
            "x3": x3,
            "y3": y3,
            "angle": angle,
            "width": self._angle_width,
            "color": QColor(self._angle_color),
            "name": None,
            "id": self._annotation_counter["angle"],
        }
        self._annotations[frame].append(annotation)
        
        # Update tree and video view
        self._rebuild_frames_tree()
        self._video_view.set_annotations(self._annotations.get(frame, []))

    def _calculate_angle_degrees(self, x1: float, y1: float, x2: float, y2: float, x3: float, y3: float) -> float:
        """Calculate the angle at p2 formed by p1-p2-p3, always returning < 180 degrees."""
        # Vectors from p2 to p1 and from p2 to p3
        v1x = x1 - x2
        v1y = y1 - y2
        v2x = x3 - x2
        v2y = y3 - y2
        
        # Calculate magnitudes
        mag1 = math.sqrt(v1x * v1x + v1y * v1y)
        mag2 = math.sqrt(v2x * v2x + v2y * v2y)
        
        if mag1 < 0.001 or mag2 < 0.001:
            return 0.0
        
        # Calculate dot product and angle
        dot = v1x * v2x + v1y * v2y
        cos_angle = dot / (mag1 * mag2)
        
        # Clamp to avoid numerical errors
        cos_angle = max(-1.0, min(1.0, cos_angle))
        
        angle_rad = math.acos(cos_angle)
        angle_deg = math.degrees(angle_rad)
        
        # Ensure angle is always < 180
        if angle_deg > 180:
            angle_deg = 360 - angle_deg
        
        return angle_deg
    
    # endregion

    # region Helpers
    def _update_controls_enabled(self, enabled: bool) -> None:
        self._back_frame_btn.setEnabled(enabled)
        self._forward_frame_btn.setEnabled(enabled)
        self._play_btn.setEnabled(enabled)
        self._hand_btn.setEnabled(enabled)
        self._selection_btn.setEnabled(True)
        self._start_btn.setEnabled(enabled)
        self._end_btn.setEnabled(enabled)
        self._loop_checkbox.setEnabled(True)  # allow toggling even without media
        self._save_frame_btn.setEnabled(enabled)
        self._frames_tree.setEnabled(enabled or bool(self._saved_frames))
        self._update_interest_actions_enabled()
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
        if any(entry["frame"] == frame for entry in self._saved_frames):
            return

        self._saved_frames.append({"frame": frame, "name": None})
        self._saved_frames.sort(key=lambda e: e["frame"])
        self._rebuild_frames_tree()
        self._update_interest_actions_enabled()

    def _rebuild_frames_tree(self) -> None:
        if not self._tree_root:
            return
        
        # Store current selection
        selected_data = None
        current = self._frames_tree.currentItem()
        if current is not None:
            selected_data = current.data(0, Qt.UserRole)

        self._tree_root.takeChildren()
        
        for entry in self._saved_frames:
            frame_num = entry["frame"]
            frame_item = QTreeWidgetItem()
            frame_item.setData(0, Qt.UserRole, {"type": "frame", "frame": frame_num})
            self._tree_root.addChild(frame_item)
            self._decorate_tree_item(frame_item, entry)
            
            # Add annotations as children of the frame
            frame_annotations = self._annotations.get(frame_num, [])
            for annotation in frame_annotations:
                ann_item = QTreeWidgetItem()
                ann_item.setData(0, Qt.UserRole, {"type": "annotation", "frame": frame_num, "annotation": annotation})
                frame_item.addChild(ann_item)
                self._decorate_annotation_item(ann_item, annotation)
        
        self._frames_tree.expandAll()
        
        # Restore selection
        if selected_data is not None:
            self._select_tree_item_by_data(selected_data)

    def _decorate_annotation_item(self, item: QTreeWidgetItem, annotation: dict) -> None:
        """Style an annotation tree item."""
        wrapper = QWidget(self._frames_tree)
        layout = QHBoxLayout(wrapper)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(4)
        
        ann_type = annotation["type"]
        ann_id = annotation["id"]
        ann_name = annotation.get("name")
        
        # Type symbol
        symbols = {"point": "●", "line": "╱", "angle": "∠", "freehand": "◌", "brush": "🖌"}
        symbol = symbols.get(ann_type, "?")
        
        # Color preview for point, line, and angle
        if ann_type in ("point", "line", "angle"):
            color_label = QLabel(symbol)
            color_label.setStyleSheet(f"color: {annotation['color'].name()}; font-size: 14px;")
            layout.addWidget(color_label)
        else:
            symbol_label = QLabel(symbol)
            layout.addWidget(symbol_label)
        
        # Name or default
        type_names = {"point": "Ponto", "line": "Reta", "angle": "Ângulo", "freehand": "Máscara", "brush": "Brush"}
        display_name = ann_name if ann_name else f"{type_names.get(ann_type, ann_type)} {ann_id}"
        
        name_label = QLabel(display_name)
        if ann_name:
            font = name_label.font()
            font.setBold(True)
            name_label.setFont(font)
        layout.addWidget(name_label)
        
        layout.addStretch()
        wrapper.setLayout(layout)
        self._frames_tree.setItemWidget(item, 0, wrapper)

    def _select_tree_item_by_data(self, data) -> None:
        """Find and select a tree item by its stored data."""
        def data_matches(stored_data, target_data) -> bool:
            """Compare data by type and identifiers, not by full equality."""
            if stored_data is None or target_data is None:
                return stored_data is target_data
            if isinstance(stored_data, int) and isinstance(target_data, int):
                return stored_data == target_data
            if isinstance(stored_data, dict) and isinstance(target_data, dict):
                if stored_data.get("type") != target_data.get("type"):
                    return False
                if stored_data.get("frame") != target_data.get("frame"):
                    return False
                # For annotations, compare by id
                if stored_data.get("type") == "annotation":
                    stored_ann = stored_data.get("annotation", {})
                    target_ann = target_data.get("annotation", {})
                    return stored_ann.get("id") == target_ann.get("id") and stored_ann.get("type") == target_ann.get("type")
                return True
            return False

        def find_item(parent):
            for i in range(parent.childCount()):
                child = parent.child(i)
                if data_matches(child.data(0, Qt.UserRole), data):
                    return child
                found = find_item(child)
                if found:
                    return found
            return None
        
        item = find_item(self._tree_root)
        if item:
            self._frames_tree.setCurrentItem(item)

    def _decorate_tree_item(self, item: QTreeWidgetItem, entry: dict[str, int | str | None]) -> None:
        wrapper = QWidget(self._frames_tree)
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(0)

        frame = entry["frame"]
        name = entry.get("name")

        name_label = QLabel(wrapper)
        name_label.setText(name if name else f"Frame {frame}")
        if name:
            font = name_label.font()
            font.setBold(True)
            name_label.setFont(font)

        layout.addWidget(name_label)

        if name:
            frame_label = QLabel(f"Frame {frame}", wrapper)
            frame_label.setStyleSheet("color: #666666; font-size: 11px;")
            layout.addWidget(frame_label)

        wrapper.setLayout(layout)
        self._frames_tree.setItemWidget(item, 0, wrapper)

    def _on_tree_item_clicked(self, item: QTreeWidgetItem) -> None:
        data = item.data(0, Qt.UserRole)
        if data is None:
            self._update_properties("Nenhum item selecionado")
            self._update_interest_actions_enabled()
            return
        if not self._media_loaded:
            self._update_interest_actions_enabled()
            return
        
        # Handle both old format (int) and new format (dict)
        if isinstance(data, int):
            frame = data
            item_type = "frame"
        else:
            frame = data.get("frame")
            item_type = data.get("type", "frame")
        
        position_ms = self._frame_to_ms(int(frame))
        self._player_controller.set_position(position_ms)
        self._update_frame_label(position_ms)
        self._update_time_label(position_ms, self._position_slider.maximum())
        
        # Update properties based on item type
        if item_type == "annotation":
            annotation = data.get("annotation", {})
            self._update_properties(self._format_annotation_properties(annotation))
        else:
            self._update_properties(f"Frame: {frame}")
        
        self._update_interest_actions_enabled()

    def _format_annotation_properties(self, annotation: dict) -> str:
        """Format annotation details for the properties panel."""
        ann_type = annotation.get("type", "unknown")
        lines = []
        
        type_names = {"point": "Ponto", "line": "Reta", "angle": "Ângulo", "freehand": "Máscara", "brush": "Brush"}
        lines.append(f"Tipo: {type_names.get(ann_type, ann_type)}")
        
        if annotation.get("name"):
            lines.append(f"Nome: {annotation['name']}")
        
        if ann_type == "point":
            lines.append(f"Posição: ({annotation.get('x', 0):.1f}, {annotation.get('y', 0):.1f})")
            lines.append(f"Tamanho: {annotation.get('size', 3)}")
            color = annotation.get('color')
            if color:
                lines.append(f"Cor: {color.name()}")
        
        elif ann_type == "line":
            x1, y1 = annotation.get('x1', 0), annotation.get('y1', 0)
            x2, y2 = annotation.get('x2', 0), annotation.get('y2', 0)
            lines.append(f"Início: ({x1:.1f}, {y1:.1f})")
            lines.append(f"Fim: ({x2:.1f}, {y2:.1f})")
            length = math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
            lines.append(f"Comprimento: {length:.1f} px")
            lines.append(f"Espessura: {annotation.get('width', 2)}")
            color = annotation.get('color')
            if color:
                lines.append(f"Cor: {color.name()}")
        
        elif ann_type == "angle":
            x1, y1 = annotation.get('x1', 0), annotation.get('y1', 0)
            x2, y2 = annotation.get('x2', 0), annotation.get('y2', 0)
            x3, y3 = annotation.get('x3', 0), annotation.get('y3', 0)
            
            lines.append(f"Ponto 1: ({x1:.1f}, {y1:.1f})")
            lines.append(f"Vértice: ({x2:.1f}, {y2:.1f})")
            lines.append(f"Ponto 3: ({x3:.1f}, {y3:.1f})")
            
            # Calculate line lengths
            len1 = math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
            len2 = math.sqrt((x3 - x2) ** 2 + (y3 - y2) ** 2)
            lines.append(f"Comprimento reta 1: {len1:.1f} px")
            lines.append(f"Comprimento reta 2: {len2:.1f} px")
            
            angle = annotation.get('angle', 0)
            lines.append(f"Ângulo: {angle:.4f}°")
            
            lines.append(f"Espessura: {annotation.get('width', 2)}")
            color = annotation.get('color')
            if color:
                lines.append(f"Cor: {color.name()}")

        return "\n".join(lines)

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

    def _rename_selected_frame(self) -> None:
        item = self._frames_tree.currentItem()
        if not item:
            return
        data = item.data(0, Qt.UserRole)
        if data is None:
            return
        
        # Handle both old format (int) and new format (dict)
        if isinstance(data, int):
            # Old format - frame only
            frame = data
            entry = next((e for e in self._saved_frames if e["frame"] == frame), None)
            if entry is None:
                return
            current_name = entry.get("name") or ""
            name, ok = QInputDialog.getText(self, "Renomear frame", "Nome:", text=current_name)
            if not ok:
                return
            entry["name"] = name.strip() or None
            self._rebuild_frames_tree()
            self._update_interest_actions_enabled()
            
        elif data.get("type") == "frame":
            frame = data["frame"]
            entry = next((e for e in self._saved_frames if e["frame"] == frame), None)
            if entry is None:
                return
            current_name = entry.get("name") or ""
            name, ok = QInputDialog.getText(self, "Renomear frame", "Nome:", text=current_name)
            if not ok:
                return
            entry["name"] = name.strip() or None
            self._rebuild_frames_tree()
            self._update_interest_actions_enabled()
            
        elif data.get("type") == "annotation":
            frame = data.get("frame")
            annotation_data = data.get("annotation")
            if annotation_data is None or frame is None:
                return
            
            # Find the annotation in self._annotations by id and type
            ann_id = annotation_data.get("id")
            ann_type = annotation_data.get("type")
            
            frame_annotations = self._annotations.get(frame, [])
            annotation = next(
                (a for a in frame_annotations if a.get("id") == ann_id and a.get("type") == ann_type),
                None
            )
            
            if annotation is None:
                return
            
            current_name = annotation.get("name") or ""
            type_names = {"point": "Ponto", "line": "Reta", "angle": "Ângulo", "freehand": "Máscara", "brush": "Brush"}
            type_label = type_names.get(ann_type, "Item")
            name, ok = QInputDialog.getText(self, f"Renomear {type_label.lower()}", "Nome:", text=current_name)
            if not ok:
                return
            
            annotation["name"] = name.strip() or None
            
            # Rebuild and reselect
            self._rebuild_frames_tree()
            
            # Manually select the renamed item
            self._select_annotation_in_tree(frame, ann_id, ann_type)
            self._update_interest_actions_enabled()

    def _select_annotation_in_tree(self, frame: int, ann_id: int, ann_type: str) -> None:
        """Select a specific annotation in the tree by its identifiers."""
        if not self._tree_root:
            return
        
        for i in range(self._tree_root.childCount()):
            frame_item = self._tree_root.child(i)
            frame_data = frame_item.data(0, Qt.UserRole)
            if isinstance(frame_data, dict) and frame_data.get("frame") == frame:
                for j in range(frame_item.childCount()):
                    ann_item = frame_item.child(j)
                    ann_data = ann_item.data(0, Qt.UserRole)
                    if isinstance(ann_data, dict) and ann_data.get("type") == "annotation":
                        annotation = ann_data.get("annotation", {})
                        if annotation.get("id") == ann_id and annotation.get("type") == ann_type:
                            self._frames_tree.setCurrentItem(ann_item)
                            return

    def _delete_selected_frame(self) -> None:
        item = self._frames_tree.currentItem()
        if not item:
            return
        data = item.data(0, Qt.UserRole)
        if data is None:
            return
        
        # Handle both old format (int) and new format (dict)
        if isinstance(data, int):
            frame = data
            self._saved_frames = [e for e in self._saved_frames if e["frame"] != frame]
            if frame in self._annotations:
                del self._annotations[frame]
        elif data.get("type") == "frame":
            frame = data["frame"]
            self._saved_frames = [e for e in self._saved_frames if e["frame"] != frame]
            if frame in self._annotations:
                del self._annotations[frame]
        elif data.get("type") == "annotation":
            frame = data["frame"]
            annotation = data.get("annotation")
            if frame in self._annotations and annotation in self._annotations[frame]:
                self._annotations[frame].remove(annotation)
                # If no more annotations, keep the frame (user saved it for a reason)
        
        self._rebuild_frames_tree()
        self._update_interest_actions_enabled()
        self._update_properties("Nenhum item selecionado")
        
        # Update video view
        self._video_view.set_annotations(self._annotations.get(self._current_frame, []))

    def _has_selected_interest(self) -> bool:
        item = self._frames_tree.currentItem()
        if not item:
            return False
        data = item.data(0, Qt.UserRole)
        if data is None:
            return False
        # Accept both old format (int) and new format (dict with type)
        if isinstance(data, int):
            return True
        return data.get("type") in ("frame", "annotation")

    def _on_selection_toggled(self, checked: bool) -> None:
        if checked:
            self._video_view.set_hand_mode(False)
            self._video_view.set_current_tool("selection")
            self._video_view.viewport().setCursor(Qt.ArrowCursor)

    def _on_hand_toggled(self, checked: bool) -> None:
        self._video_view.set_hand_mode(checked)
        self._video_view.set_current_tool("hand" if checked else "selection")

    def _on_point_toggled(self, checked: bool) -> None:
        if checked:
            self._video_view.set_hand_mode(False)
            self._video_view.set_current_tool("point")
            self._video_view.viewport().setCursor(Qt.CrossCursor)
        else:
            self._video_view.set_current_tool("selection")
    
    def _on_line_toggled(self, checked: bool) -> None:
        if checked:
            self._video_view.set_hand_mode(False)
            self._video_view.set_current_tool("line")
            self._video_view.set_line_guide_enabled(self._line_guide_enabled)
            self._video_view.set_line_preview_style(self._line_color, self._line_width)
            self._video_view.viewport().setCursor(Qt.CrossCursor)
        else:
            self._video_view.set_current_tool("selection")

    def _on_angle_toggled(self, checked: bool) -> None:
        if checked:
            self._video_view.set_hand_mode(False)
            self._video_view.set_current_tool("angle")
            self._video_view.set_angle_preview_style(self._angle_color, self._angle_width)
            self._video_view.viewport().setCursor(Qt.CrossCursor)
        else:
            self._video_view.set_current_tool("selection")
            # Hide angle display when tool is deselected
            self._angle_display_label.setVisible(False)

    def _update_interest_actions_enabled(self) -> None:
        selected = self._frames_tree.currentItem()
        has_frame = bool(selected and selected.data(0, Qt.UserRole) is not None)
        self._edit_frame_btn.setEnabled(has_frame)
        self._delete_frame_btn.setEnabled(has_frame)

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
