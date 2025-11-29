import os

import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtTest import QSignalSpy

from videomleditor.player_controller import VideoPlayerController


@pytest.fixture(scope="session", autouse=True)
def qcore_app():
    """Ensure a Qt application exists for QObject/SIGNAL plumbing during tests."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication([])
    yield app


class FakeSignal:
    """Minimal Qt-like signal for driving controller wiring in tests."""

    def __init__(self):
        self._subscribers = []

    def connect(self, callback):
        self._subscribers.append(callback)

    def emit(self, *args, **kwargs):
        for callback in list(self._subscribers):
            callback(*args, **kwargs)


class FakeMetaData:
    def __init__(self, frame_rate=None):
        self._frame_rate = frame_rate

    def value(self, _key):
        return self._frame_rate


class FakePlayer:
    """Stub for QMediaPlayer interactions used by VideoPlayerController."""

    def __init__(self, position=0, duration=1000, frame_rate=None):
        self._position = position
        self._duration = duration
        self.positionChanged = FakeSignal()
        self.durationChanged = FakeSignal()
        self.playbackStateChanged = FakeSignal()
        self.mediaStatusChanged = FakeSignal()
        self.errorOccurred = FakeSignal()
        self._frame_rate = frame_rate
        self.video_output = None
        self.source = None

    def setAudioOutput(self, _output):
        return None

    def setVideoOutput(self, output):
        self.video_output = output

    def setSource(self, source):
        self.source = source

    def play(self):
        return None

    def pause(self):
        return None

    def duration(self):
        return self._duration

    def position(self):
        return self._position

    def setPosition(self, value):
        self._position = value

    def playbackState(self):
        return QMediaPlayer.PlayingState

    def metaData(self):
        return FakeMetaData(self._frame_rate)


def build_controller(fake_player: FakePlayer) -> VideoPlayerController:
    return VideoPlayerController(player_factory=lambda parent: fake_player)


def test_skip_frames_forward_and_backward():
    player = FakePlayer(position=0, duration=1000)
    controller = build_controller(player)

    controller.skip_frames(1)
    assert player.position() == 33  # 1000/30 ~= 33ms per frame

    player.setPosition(10)
    controller.skip_frames(-1)
    assert player.position() == 0  # clamped to zero


def test_skip_frames_respects_duration_cap():
    player = FakePlayer(position=980, duration=1000)
    controller = build_controller(player)

    controller.skip_frames(2)  # ~66ms forward, should cap at duration
    assert player.position() == 1000


def test_frame_rate_metadata_updates_interval():
    player = FakePlayer(position=0, duration=1000, frame_rate=60)
    controller = build_controller(player)

    controller._handle_media_status(QMediaPlayer.BufferedMedia)
    controller.skip_frames(1)

    assert player.position() == 16  # 1000/60 ~= 16ms per frame


def test_error_emits_message_signal():
    player = FakePlayer()
    controller = build_controller(player)
    spy = QSignalSpy(controller.error_occurred)

    controller._handle_error(QMediaPlayer.ResourceError, "boom")
    assert spy.count() == 1
    assert spy.takeFirst()[0] == "boom"


def test_no_error_does_not_emit():
    player = FakePlayer()
    controller = build_controller(player)
    spy = QSignalSpy(controller.error_occurred)

    controller._handle_error(QMediaPlayer.NoError, "")
    assert spy.count() == 0
