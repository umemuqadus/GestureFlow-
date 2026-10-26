"""SystemController tests: OS actions against an injected fake backend.

Nothing here presses a real key, captures the real screen, or touches the real
display.  Verifies key mapping, screenshot file creation, brightness clamping,
and graceful handling of an unsupported display.
"""

from __future__ import annotations

import pytest

from controller.system_controller import (
    KEY_MEDIA_TOGGLE,
    KEY_VOLUME_DOWN,
    KEY_VOLUME_MUTE,
    KEY_VOLUME_UP,
    SystemBackend,
    SystemController,
)


class FakeImage:
    def __init__(self, backend: "FakeBackend") -> None:
        self._backend = backend

    def save(self, path) -> None:
        if self._backend.fail_grab:
            raise RuntimeError("capture failed")
        path.write_bytes(b"\x89PNG fake")
        self._backend.screenshots += 1


class FakeBackend(SystemBackend):
    def __init__(self, brightness: int | None = 50, volume: int | None = 40,
                 core_audio: bool = True) -> None:
        self.pressed: list[str] = []
        self.brightness = brightness
        self.fail_grab = False
        self.fail_set = False
        self.set_calls: list[int] = []
        self.screenshots = 0
        self.volume = volume
        self.muted = False
        # With Core Audio "available" the volume gestures go straight to the
        # audio endpoint (no media key, so no shell OSD); when it is not, the
        # controller must fall back to VK_VOLUME_*.
        self.core_audio = core_audio

    def grab_screen(self):
        return FakeImage(self)

    def press_key(self, key: str) -> None:
        self.pressed.append(key)

    def get_brightness(self) -> int | None:
        return self.brightness

    def set_brightness(self, level: int) -> bool:
        if self.fail_set:
            return False
        self.set_calls.append(int(level))
        self.brightness = int(level)
        return True

    def get_volume(self) -> int | None:
        return self.volume

    def is_muted(self) -> bool | None:
        return self.muted

    def step_volume(self, delta: int) -> int | None:
        if not self.core_audio or self.volume is None:
            return None
        self.volume = max(0, min(100, int(self.volume) + int(delta)))
        return self.volume

    def set_muted(self, muted: bool) -> bool:
        if not self.core_audio:
            return False
        self.muted = bool(muted)
        return True


@pytest.fixture()
def controller(tmp_path) -> tuple[SystemController, FakeBackend]:
    backend = FakeBackend()
    ctrl = SystemController(backend=backend)
    ctrl.screenshot_dir = tmp_path / "screenshots"  # never write to real APPDATA
    return ctrl, backend


# -- volume / media keys -------------------------------------------------------
def test_volume_goes_through_core_audio_without_a_key_press(controller):
    """A synthetic VK_VOLUME_* press pops Windows' own OSD over ours.

    Regression guard for the "two indicators at once" bug: the happy path must
    reach the audio endpoint directly and never touch the keyboard.
    """
    ctrl, backend = controller
    backend.volume = 40
    ctrl.volume_up()
    ctrl.volume_down()
    ctrl.volume_mute()
    assert backend.pressed == []
    assert ctrl.volume_level == 40
    assert ctrl.muted is True
    ctrl.volume_mute()
    assert ctrl.muted is False


def test_volume_keys_are_the_fallback_when_core_audio_is_unavailable(controller):
    ctrl, backend = controller
    backend.core_audio = False
    ctrl.volume_up()
    ctrl.volume_down()
    ctrl.volume_mute()
    ctrl.media_toggle()
    assert backend.pressed == [KEY_VOLUME_UP, KEY_VOLUME_DOWN,
                               KEY_VOLUME_MUTE, KEY_MEDIA_TOGGLE]


def test_volume_key_names_match_windows_vks():
    # Documented Windows VK codes: these names are what PyAutoGUI maps to
    # 0xAF / 0xAE / 0xAD / 0xB3.  A rename here would silently break control.
    assert (KEY_VOLUME_UP, KEY_VOLUME_DOWN, KEY_VOLUME_MUTE, KEY_MEDIA_TOGGLE) == (
        "volumeup", "volumedown", "volumemute", "playpause",
    )


def test_press_failure_is_swallowed():
    class BoomBackend(FakeBackend):
        def press_key(self, key: str) -> None:
            raise RuntimeError("no audio device")

    ctrl = SystemController(backend=BoomBackend(core_audio=False))
    ctrl.volume_up()  # must not raise
    ctrl.media_toggle()
    # Nothing changed, so no level is reported to the indicator.
    assert ctrl.volume_level is None


# -- level bookkeeping for the on-screen indicator ----------------------------
def test_volume_level_reports_the_applied_step(controller):
    """Core Audio applies the step synchronously, so the level is exact."""
    ctrl, backend = controller
    backend.volume = 40
    ctrl.volume_up()
    assert ctrl.volume_level == 42
    ctrl.volume_up()
    assert ctrl.volume_level == 44
    ctrl.volume_down()
    assert ctrl.volume_level == 42
    assert ctrl.muted is None          # mute state unknown until a mute gesture


def test_volume_level_is_predicted_when_the_key_read_races(controller):
    """On the media-key fallback the read right after the press is stale."""
    ctrl, backend = controller
    backend.core_audio = False
    backend.volume = 40
    ctrl.volume_up()
    assert ctrl.volume_level == 42   # Windows' 2% step, applied optimistically
    backend.volume = 42              # the shell caught up
    ctrl.volume_up()
    assert ctrl.volume_level == 44
    backend.volume = 44
    ctrl.volume_down()
    assert ctrl.volume_level == 42
    assert ctrl.muted is None


def test_volume_level_uses_the_real_reading_when_it_moves():
    class Applying(FakeBackend):
        def press_key(self, key: str) -> None:
            super().press_key(key)
            self.volume = 75            # the OS applied the change already

    ctrl = SystemController(backend=Applying(core_audio=False))
    ctrl.volume_up()
    assert ctrl.volume_level == 75      # never predicted over a real reading


def test_volume_level_is_none_when_unreadable(controller):
    ctrl, backend = controller
    backend.volume = None               # e.g. no default output device
    ctrl.volume_up()
    assert ctrl.volume_level is None


def test_mute_toggles_the_flag(controller):
    ctrl, backend = controller
    backend.volume = 40
    ctrl.volume_mute()
    assert ctrl.muted is True           # set directly through Core Audio
    assert ctrl.volume_level == 40
    ctrl.volume_mute()
    assert ctrl.muted is False


def test_mute_falls_back_to_the_key_and_predicts_the_toggle(controller):
    ctrl, backend = controller
    backend.core_audio = False
    backend.volume = 40
    ctrl.volume_mute()
    assert backend.pressed == [KEY_VOLUME_MUTE]
    assert ctrl.muted is True           # fake never flips it: predicted
    assert ctrl.volume_level == 40


# -- Core Audio GUID decoding ---------------------------------------------------
def test_audio_guid_decodes_to_the_sdk_byte_layout():
    """Guard the ctypes struct: a misparsed GUID silently yields E_NOINTERFACE."""
    from controller.system_controller import _guid, _IID_IAUDIOENDPOINTVOLUME

    guid = _guid(_IID_IAUDIOENDPOINTVOLUME)  # 5CDF2C82-841E-4546-9722-0CF74078229A
    assert bytes(guid) == bytes(
        (0x82, 0x2C, 0xDF, 0x5C, 0x1E, 0x84, 0x46, 0x45,
         0x97, 0x22, 0x0C, 0xF7, 0x40, 0x78, 0x22, 0x9A)
    )


# -- screenshot ----------------------------------------------------------------
def test_screenshot_saved_locally(controller, tmp_path):
    ctrl, backend = controller
    path = ctrl.screenshot()
    assert path is not None
    assert path.exists()
    assert path.parent == tmp_path / "screenshots"
    assert path.name.startswith("screenshot_") and path.name.endswith(".png")
    assert backend.screenshots == 1


def test_screenshot_failure_returns_none(controller):
    ctrl, backend = controller
    backend.fail_grab = True
    assert ctrl.screenshot() is None


# -- brightness ----------------------------------------------------------------
def test_brightness_up_and_down(controller):
    ctrl, backend = controller
    backend.brightness = 50
    assert ctrl.brightness_up() is True
    assert backend.brightness == 55
    assert ctrl.brightness_down() is True
    assert backend.brightness == 50


def test_brightness_clamped_to_bounds(controller):
    ctrl, backend = controller
    backend.brightness = 98
    ctrl.brightness_up()
    assert backend.brightness == 100  # never exceeds 100
    backend.brightness = 2
    ctrl.brightness_down()
    assert backend.brightness == 0  # never below 0


def test_brightness_already_at_limit_is_not_an_error(controller):
    ctrl, backend = controller
    backend.brightness = 100
    assert ctrl.brightness_up() is True  # no-op, still success
    assert backend.set_calls == []


def test_brightness_unsupported_reports_false(tmp_path):
    backend = FakeBackend(brightness=None)  # display exposes no WMI brightness
    ctrl = SystemController(backend=backend)
    ctrl.screenshot_dir = tmp_path / "s"
    assert ctrl.brightness_supported is False
    assert ctrl.brightness_up() is False
    assert ctrl.brightness_down() is False
    assert backend.set_calls == []


def test_brightness_set_failure_reports_false(controller):
    ctrl, backend = controller
    backend.brightness = 50
    backend.fail_set = True
    assert ctrl.brightness_up() is False
    assert ctrl.brightness_level is None  # no level to show for a failed step


def test_brightness_supported_when_readable(controller):
    ctrl, _ = controller
    assert ctrl.brightness_supported is True


def test_brightness_level_follows_each_step(controller):
    ctrl, backend = controller
    backend.brightness = 50
    ctrl.brightness_up()
    assert ctrl.brightness_level == 55
    ctrl.brightness_down()
    assert ctrl.brightness_level == 50
    backend.brightness = 100
    ctrl.brightness_up()                # already at the limit: still reported
    assert ctrl.brightness_level == 100


def test_brightness_level_stays_none_when_unsupported(tmp_path):
    backend = FakeBackend(brightness=None)
    ctrl = SystemController(backend=backend)
    ctrl.screenshot_dir = tmp_path / "s"
    ctrl.brightness_up()
    assert ctrl.brightness_level is None  # indicator must not invent a level
