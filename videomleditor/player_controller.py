from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtMultimedia import QAudioOutput, QMediaMetaData, QMediaPlayer


class VideoPlayerController(QObject):
    """Small wrapper around QMediaPlayer to centralize playback logic."""

    position_changed = Signal(int)
    duration_changed = Signal(int)
    playback_state_changed = Signal(QMediaPlayer.PlaybackState)
    media_status_changed = Signal(QMediaPlayer.MediaStatus)
    frame_rate_changed = Signal(float)
    error_occurred = Signal(str)

    _DEFAULT_FRAME_RATE = 30.0  # fps fallback when metadata is missing

    def __init__(
        self,
        parent: Optional[QObject] = None,
        player_factory: Optional[Callable[[QObject], QMediaPlayer]] = None,
    ) -> None:
        super().__init__(parent)
        self._player = (player_factory or QMediaPlayer)(self)
        self._audio_output = QAudioOutput(self)
        if hasattr(self._player, "setAudioOutput"):
            self._player.setAudioOutput(self._audio_output)
        self._frame_interval_ms: float = 1000.0 / self._DEFAULT_FRAME_RATE
        self._current_path: Optional[Path] = None
        self._loop_enabled: bool = False

        self._player.positionChanged.connect(self.position_changed.emit)
        self._player.durationChanged.connect(self.duration_changed.emit)
        self._player.playbackStateChanged.connect(self.playback_state_changed.emit)
        self._player.mediaStatusChanged.connect(self._handle_media_status)
        self._player.errorOccurred.connect(self._handle_error)

    def set_video_output(self, video_output) -> None:
        """Attach a video surface to render frames."""
        if hasattr(self._player, "setVideoOutput"):
            try:
                self._player.setVideoOutput(video_output)
                return
            except TypeError:
                pass

            if hasattr(video_output, "videoSink"):
                try:
                    self._player.setVideoOutput(video_output.videoSink())
                except TypeError:
                    return

    def load(self, file_path: str | Path) -> None:
        """Load a local video file."""
        self._current_path = Path(file_path)
        if hasattr(self._player, "setSource"):
            self._player.setSource(QUrl.fromLocalFile(str(self._current_path)))
        self._apply_loop_setting()

    def play(self) -> None:
        if hasattr(self._player, "play"):
            self._player.play()

    def pause(self) -> None:
        if hasattr(self._player, "pause"):
            self._player.pause()

    def set_position(self, position_ms: int) -> None:
        """Seek to the requested position in milliseconds."""
        if position_ms < 0:
            position_ms = 0
        self._player.setPosition(position_ms)

    def skip_frames(self, frame_offset: int) -> None:
        """Move forward/backward by a number of frames, respecting video duration."""
        if frame_offset == 0 or self._player.duration() <= 0:
            return

        delta_ms = int(frame_offset * self._frame_interval_ms)
        new_position = max(0, min(self._player.duration(), self._player.position() + delta_ms))
        self._player.setPosition(new_position)

    def is_playing(self) -> bool:
        if hasattr(self._player, "playbackState"):
            return self._player.playbackState() == QMediaPlayer.PlayingState
        return False

    def set_looping(self, enabled: bool) -> None:
        self._loop_enabled = enabled
        self._apply_loop_setting()

    def _handle_media_status(self, status: QMediaPlayer.MediaStatus) -> None:
        self.media_status_changed.emit(status)
        if status in (
            QMediaPlayer.MediaStatus.BufferedMedia,
            QMediaPlayer.MediaStatus.LoadedMedia,
        ):
            self._update_frame_interval()
        elif status == QMediaPlayer.MediaStatus.EndOfMedia:
            if not self._loop_enabled:
                # Stop at the last frame instead of looping back.
                duration = self._player.duration()
                if duration > 0:
                    self._player.setPosition(duration)
                self._player.pause()

    def _handle_error(self, error: QMediaPlayer.Error, error_string: str) -> None:
        if error != QMediaPlayer.NoError:
            message = error_string or "Erro ao carregar o vídeo."
            self.error_occurred.emit(message)

    def _update_frame_interval(self) -> None:
        """Derive frame interval from metadata. Fallback to a sensible default."""
        metadata = self._player.metaData()
        frame_rate_value = None

        if metadata is not None:
            try:
                frame_rate_value = metadata.value(QMediaMetaData.VideoFrameRate)
            except AttributeError:
                # Older PySide6 versions expose metadata differently; ignore and fallback.
                frame_rate_value = None

        frame_rate = float(frame_rate_value) if frame_rate_value else self._DEFAULT_FRAME_RATE
        if frame_rate <= 0:
            frame_rate = self._DEFAULT_FRAME_RATE

        self._frame_interval_ms = 1000.0 / frame_rate
        self.frame_rate_changed.emit(frame_rate)

    def _apply_loop_setting(self) -> None:
        """Apply looping preference if backend supports it."""
        if hasattr(self._player, "setLoops"):
            try:
                if self._loop_enabled:
                    self._player.setLoops(QMediaPlayer.Infinite)
                else:
                    self._player.setLoops(1)
            except Exception:
                # Best-effort; fallback will be handled via EndOfMedia.
                return
