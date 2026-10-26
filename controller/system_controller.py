"""System control: screenshot, volume, brightness and media keys.

This is the only module that performs *non-mouse* OS actions.  Everything runs
locally and offline:

* Screenshot  - PIL ``ImageGrab`` saved under ``%APPDATA%\\GestureFlowAI\\screenshots``.
* Volume/mute  - stepped straight through Windows Core Audio (ctypes only) so
  the shell never sees a synthetic volume key: that key is what makes Windows
  pop up *its* volume OSD next to the app's indicator.  Play/pause still uses
  PyAutoGUI's ``keybd_event`` path (VK_MEDIA_PLAY_PAUSE 0xB3), and when Core
  Audio is unavailable the volume gestures fall back to the media virtual keys
  (VK_VOLUME_UP 0xAF, VK_VOLUME_DOWN 0xAE, VK_VOLUME_MUTE 0xAD).  The level
  read back here is what the UI's on-screen indicator displays.
* Brightness  - WMI ``WmiMonitorBrightnessMethods`` (internal laptop panels).
  The ``wmi`` package is an install-time dependency; when it is missing or the
  display does not expose brightness, the feature reports itself unavailable
  instead of failing.

A ``backend`` may be injected so tests never press real keys, capture the real
screen or touch the display.
"""

from __future__ import annotations

import ctypes
from contextlib import contextmanager
from ctypes import byref
from datetime import datetime
from pathlib import Path

from utils.logger import get_logger
from utils.platform_utils import app_data_dir, is_windows

log = get_logger(__name__)

# Virtual keys sent for the system actions (documented Windows VK codes).
KEY_VOLUME_UP = "volumeup"
KEY_VOLUME_DOWN = "volumedown"
KEY_VOLUME_MUTE = "volumemute"
KEY_MEDIA_TOGGLE = "playpause"

# Percent the brightness gestures move per accepted step.
BRIGHTNESS_STEP_PCT = 5

# Percent one Windows volume key press moves (the shell's default step); used
# only to predict a level the OS has not yet reflected in a read-back.
VOLUME_STEP_PCT = 2

# -- Windows Core Audio (master volume / mute) --------------------------------
# Read/step operations against the default output device, done with ctypes so
# neither the on-screen level indicator nor the volume gestures need an extra
# dependency (pycaw/comtypes are not installed).  Every failure path returns
# None/False, which either hides the indicator or sends the media key instead.
_CLSID_MMDEVICEENUMERATOR = "BCDE0395-E52F-467C-8E3D-C4579291692E"
_IID_IMMDEVICEENUMERATOR = "A95664D2-9614-4F35-A746-DE8DB63617E6"
# IAudioEndpointVolume, from the SDK's endpointvolume.h (MIDL_INTERFACE line).
_IID_IAUDIOENDPOINTVOLUME = "5CDF2C82-841E-4546-9722-0CF74078229A"
_CLSCTX_ALL = 0x17
_COINIT_APARTMENTTHREADED = 2
_RPC_E_CHANGED_MODE = -2147417850  # already initialised in another mode: OK


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_uint32),
        ("Data2", ctypes.c_uint16),
        ("Data3", ctypes.c_uint16),
        ("Data4", ctypes.c_uint8 * 8),
    ]


def _guid(text: str) -> _GUID:
    """Parse a registry-style GUID string into the struct COM expects."""
    d1, d2, d3, tail = text.split("-", 3)
    hex4 = (d1, d2, d3, tail.replace("-", ""))  # last group is 4+12 digits
    g = _GUID()
    g.Data1 = int(hex4[0], 16)
    g.Data2 = int(hex4[1], 16)
    g.Data3 = int(hex4[2], 16)
    for i in range(8):
        g.Data4[i] = int(hex4[3][i * 2:i * 2 + 2], 16)
    return g


def _vtable(ptr: int, index: int, restype, argtypes, *args):
    """Call COM vtable slot ``index`` on interface pointer ``ptr``.

    On x64 Windows every method uses the same calling convention, so a slot can
    be invoked as a plain function taking the interface pointer first.  The
    returned HRESULT is checked by the caller.
    """
    vtable = ctypes.c_void_p.from_address(ptr).value or 0
    entry = ctypes.c_void_p.from_address(vtable + 8 * index).value
    # ``argtypes`` already lists the interface pointer ('this') as slot 0.
    proto = ctypes.WINFUNCTYPE(restype, *argtypes)
    return proto(entry)(ptr, *args)


def _release(ptr: int | None) -> None:
    if ptr:
        try:
            _vtable(ptr, 2, ctypes.c_uint32, (ctypes.c_void_p,))  # Release
        except Exception:  # noqa: BLE001 - best-effort cleanup
            pass


def _ole32():
    """Return ole32 with typed COM entry points (pointers must not truncate)."""
    ole32 = ctypes.WinDLL("ole32", use_last_error=True)
    ole32.CoInitializeEx.argtypes = (ctypes.c_void_p, ctypes.c_uint)
    ole32.CoInitializeEx.restype = ctypes.c_int32
    ole32.CoCreateInstance.argtypes = (
        ctypes.POINTER(_GUID), ctypes.c_void_p, ctypes.c_uint,
        ctypes.POINTER(_GUID), ctypes.POINTER(ctypes.c_void_p),
    )
    ole32.CoCreateInstance.restype = ctypes.c_int32
    ole32.CoUninitialize.argtypes = ()
    ole32.CoUninitialize.restype = None
    return ole32


def _activate_endpoint(ole32) -> tuple[int, int, int]:
    """Create the default device's interfaces; 0 marks a failed step."""
    p_enumerator = ctypes.c_void_p()
    hr = ole32.CoCreateInstance(
        byref(_guid(_CLSID_MMDEVICEENUMERATOR)), None, _CLSCTX_ALL,
        byref(_guid(_IID_IMMDEVICEENUMERATOR)), byref(p_enumerator),
    )
    if hr < 0 or not p_enumerator.value:
        return 0, 0, 0
    enumerator = p_enumerator.value

    # IMMDeviceEnumerator::GetDefaultAudioEndpoint(eRender, eMultimedia)
    p_device = ctypes.c_void_p()
    hr = _vtable(enumerator, 4, ctypes.c_int32,
                 (ctypes.c_void_p, ctypes.c_int32, ctypes.c_int32,
                  ctypes.POINTER(ctypes.c_void_p)),
                 0, 1, byref(p_device))
    if hr < 0 or not p_device.value:
        _release(enumerator)
        return 0, 0, 0
    device = p_device.value

    # IMMDevice::Activate(IAudioEndpointVolume)
    p_endpoint = ctypes.c_void_p()
    hr = _vtable(device, 3, ctypes.c_int32,
                 (ctypes.c_void_p, ctypes.POINTER(_GUID), ctypes.c_uint,
                  ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)),
                 byref(_guid(_IID_IAUDIOENDPOINTVOLUME)), _CLSCTX_ALL,
                 None, byref(p_endpoint))
    if hr < 0 or not p_endpoint.value:
        _release(device)
        _release(enumerator)
        return 0, 0, 0
    return enumerator, device, p_endpoint.value


@contextmanager
def _audio_endpoint():
    """Yield the ``IAudioEndpointVolume`` pointer of the default output device.

    Yields ``0`` when Core Audio is unavailable.  COM is initialised for the
    calling thread and every interface is released on exit, so callers never
    have to think about lifetimes.
    """
    ole32 = _ole32()
    hr = ole32.CoInitializeEx(None, _COINIT_APARTMENTTHREADED)
    if hr < 0 and hr != _RPC_E_CHANGED_MODE:
        yield 0
        return
    com_ready = hr >= 0  # S_FALSE also needs the matching CoUninitialize()

    enumerator = device = endpoint = 0
    try:
        enumerator, device, endpoint = _activate_endpoint(ole32)
        yield endpoint
    finally:
        _release(endpoint)
        _release(device)
        _release(enumerator)
        if com_ready:
            ole32.CoUninitialize()


def _read_levels(endpoint: int) -> tuple[int, bool]:
    """Master volume (0-100) and mute flag from an open endpoint."""
    level = ctypes.c_float()
    muted = ctypes.c_int32()
    # Vtable order from endpointvolume.h: 3 RegisterControlChangeNotify,
    # 4 Unregister..., 5 GetChannelCount, 6/7/8 Set/Get master level (dB),
    # 9 GetMasterVolumeLevelScalar, ... 14 SetMute, 15 GetMute,
    # 16 GetVolumeStepInfo, 17 VolumeStepUp, 18 VolumeStepDown.
    hr = _vtable(endpoint, 9, ctypes.c_int32,
                 (ctypes.c_void_p, ctypes.POINTER(ctypes.c_float)),
                 byref(level))
    if hr < 0:
        raise RuntimeError(f"GetMasterVolumeLevelScalar failed: {hr:#x}")
    hr = _vtable(endpoint, 15, ctypes.c_int32,
                 (ctypes.c_void_p, ctypes.POINTER(ctypes.c_int32)),
                 byref(muted))
    if hr < 0:
        raise RuntimeError(f"GetMute failed: {hr:#x}")
    return max(0, min(100, round(level.value * 100))), bool(muted.value)


def _audio_state() -> tuple[int, bool] | None:
    """Volume/mute of the default output device, or None when unavailable."""
    if not is_windows():
        return None
    try:
        with _audio_endpoint() as endpoint:
            if not endpoint:
                return None
            return _read_levels(endpoint)
    except Exception:  # noqa: BLE001 - feature simply unavailable
        return None


def _step_volume_os(delta: int) -> int | None:
    """Move the master volume by the system's own increment and read it back.

    Going through Core Audio instead of ``VK_VOLUME_UP/DOWN`` is deliberate:
    a synthetic volume key makes the shell pop up *its* volume OSD next to the
    app's own indicator, and the two overlays fight over the same corner of
    the screen.  Returns the new level, or None when Core Audio is missing.
    """
    if not is_windows():
        return None
    try:
        with _audio_endpoint() as endpoint:
            if not endpoint:
                return None
            index = 17 if delta >= 0 else 18  # VolumeStepUp / VolumeStepDown
            # Both take an optional GUID* event context; NULL is allowed.
            hr = _vtable(endpoint, index, ctypes.c_int32,
                         (ctypes.c_void_p, ctypes.c_void_p), None)
            if hr < 0:
                return None
            return _read_levels(endpoint)[0]
    except Exception:  # noqa: BLE001 - caller falls back to the media keys
        return None


def _set_muted_os(muted: bool) -> bool:
    """Set the master mute flag directly (again: no key press, no shell OSD)."""
    if not is_windows():
        return False
    try:
        with _audio_endpoint() as endpoint:
            if not endpoint:
                return False
            hr = _vtable(endpoint, 14, ctypes.c_int32,
                         (ctypes.c_void_p, ctypes.c_int32, ctypes.c_void_p),
                         int(bool(muted)), None)  # SetMute(BOOL, GUID*)
            return hr >= 0
    except Exception:  # noqa: BLE001 - caller falls back to the media key
        return False


class SystemBackend:
    """Raw OS operations.  The default implementation drives Windows."""

    def grab_screen(self):
        """Return a capture of the screen (PIL image-like)."""
        from PIL import ImageGrab  # noqa: PLC0415 - lazy, optional at test time

        return ImageGrab.grab()

    def press_key(self, key: str) -> None:
        import pyautogui  # noqa: PLC0415 - lazy so tests need no real backend

        pyautogui.press(key)

    def get_brightness(self) -> int | None:
        """Current screen brightness 0-100, or None when unsupported."""
        try:
            import wmi  # noqa: PLC0415 - install-time dependency, guarded
        except Exception:  # noqa: BLE001 - feature simply unavailable
            return None
        try:
            instances = wmi.WMI(namespace="root/wmi").WmiMonitorBrightness()
        except Exception:  # noqa: BLE001 - display may not expose WMI brightness
            return None
        if not instances:
            return None
        try:
            return int(instances[0].CurrentBrightness)
        except Exception:  # noqa: BLE001
            return None

    def get_volume(self) -> int | None:
        """Master output volume 0-100, or None when it cannot be read."""
        state = _audio_state()
        return None if state is None else state[0]

    def is_muted(self) -> bool | None:
        """Master mute flag, or None when it cannot be read."""
        state = _audio_state()
        return None if state is None else state[1]

    def step_volume(self, delta: int) -> int | None:
        """Move the master volume by ~``delta`` percent; None when unsupported.

        This bypasses the media keys on purpose (see ``_step_volume_os``).
        """
        return _step_volume_os(int(delta))

    def set_muted(self, muted: bool) -> bool:
        """Set the master mute flag directly; False when unsupported."""
        return _set_muted_os(bool(muted))

    def set_brightness(self, level: int) -> bool:
        try:
            import wmi  # noqa: PLC0415
        except Exception:  # noqa: BLE001
            return False
        try:
            methods = wmi.WMI(namespace="root/wmi").WmiMonitorBrightnessMethods()
        except Exception:  # noqa: BLE001
            return False
        if not methods:
            return False
        try:
            # NOTE: keyword args are mandatory here.  The WMI method signature is
            # WmiSetBrightness(Timeout, Brightness), but the `wmi` Python module
            # forwards *positional* args in the opposite order (Brightness, Timeout).
            # Passing (1, level) positionally therefore wrote Brightness=1 on every
            # step, pinning the screen to 1%.  Keywords bind by name and are safe.
            methods[0].WmiSetBrightness(Timeout=1, Brightness=int(level))
            return True
        except Exception:  # noqa: BLE001
            return False


class SystemController:
    """Performs system actions with app-level policy (paths, clamping, logging)."""

    def __init__(self, backend: SystemBackend | None = None) -> None:
        self.backend = backend if backend is not None else SystemBackend()
        self.screenshot_dir: Path = app_data_dir() / "screenshots"
        # Levels last reported by a gesture action.  They feed the on-screen
        # volume/brightness indicator; None means "nothing to show" (e.g. the
        # display exposes no brightness, or no action has run yet).
        self.volume_level: int | None = None
        self.brightness_level: int | None = None
        self.muted: bool | None = None

    # -- availability ---------------------------------------------------------
    @property
    def brightness_supported(self) -> bool:
        """True when the display exposes WMI brightness control."""
        if not is_windows():
            return False
        return self.backend.get_brightness() is not None

    @property
    def screenshot_dir_path(self) -> Path:
        return self.screenshot_dir

    # -- screenshot -----------------------------------------------------------
    def screenshot(self) -> Path | None:
        """Capture the screen and save it locally.  Returns the file or None."""
        try:
            self.screenshot_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = self.screenshot_dir / f"screenshot_{stamp}.png"
            image = self.backend.grab_screen()
            image.save(path)
        except Exception as exc:  # noqa: BLE001 - never crash the pipeline
            log.error("Screenshot failed: %s", exc)
            return None
        log.info("Screenshot saved to %s", path)
        return path

    # -- volume ----------------------------------------------------------------
    def volume_up(self) -> None:
        self._step_volume(+VOLUME_STEP_PCT)

    def volume_down(self) -> None:
        self._step_volume(-VOLUME_STEP_PCT)

    def volume_mute(self) -> None:
        current = self._read_muted()
        if current is not None and self._apply_muted(not current):
            state = self._read_muted()
            self.muted = not current if state is None else state
            if self.volume_level is None:
                self.volume_level = self._read_volume()
            return
        # Fallback: the mute media key toggles whatever the state is (this is
        # the path that also raises the shell's own OSD, so it is last resort).
        before = current
        if not self._press(KEY_VOLUME_MUTE, "mute"):
            return
        after = self._read_muted()
        if after is None:
            self.muted = None
        elif before is None or after != before:
            self.muted = after            # the toggle already landed
        else:
            self.muted = not after        # the read raced ahead of the key event
        if self.volume_level is None:
            self.volume_level = self._read_volume()

    def media_toggle(self) -> None:
        """Play/pause the active media player."""
        self._press(KEY_MEDIA_TOGGLE, "play/pause")

    def _press(self, key: str, label: str) -> bool:
        try:
            self.backend.press_key(key)
        except Exception as exc:  # noqa: BLE001
            log.error("System key '%s' (%s) failed: %s", key, label, exc)
            return False
        log.debug("System action: %s", label)
        return True

    def _step_volume(self, delta: int) -> None:
        level = self._backend_step(delta)
        if level is not None:
            self.volume_level = level      # real, already-applied value
            return
        # Fallback (no Core Audio): the media keys, whose read-back races the
        # key event, so predict the shell's step instead of lagging one press.
        before = self._read_volume()
        if not self._press(
            KEY_VOLUME_UP if delta > 0 else KEY_VOLUME_DOWN,
            "volume up" if delta > 0 else "volume down",
        ):
            return  # nothing changed, so keep the last reported level
        after = self._read_volume()
        if after is None:
            self.volume_level = None
        elif after == before:
            self.volume_level = max(0, min(100, int(before) + delta))
        else:
            self.volume_level = after

    def _backend_step(self, delta: int) -> int | None:
        try:
            return self.backend.step_volume(delta)
        except Exception:  # noqa: BLE001 - fall back to the media keys
            return None

    def _apply_muted(self, muted: bool) -> bool:
        try:
            return bool(self.backend.set_muted(muted))
        except Exception:  # noqa: BLE001 - fall back to the media key
            return False

    def _read_volume(self) -> int | None:
        try:
            value = self.backend.get_volume()
        except Exception:  # noqa: BLE001 - indicator simply hidden
            return None
        if value is None:
            return None
        return max(0, min(100, int(value)))

    def _read_muted(self) -> bool | None:
        try:
            return self.backend.is_muted()
        except Exception:  # noqa: BLE001 - indicator simply hidden
            return None

    # -- brightness ------------------------------------------------------------
    def brightness_up(self, amount: int = BRIGHTNESS_STEP_PCT) -> bool:
        return self._step_brightness(+abs(amount))

    def brightness_down(self, amount: int = BRIGHTNESS_STEP_PCT) -> bool:
        return self._step_brightness(-abs(amount))

    def _step_brightness(self, delta: int) -> bool:
        current = self.backend.get_brightness()
        if current is None:
            log.warning("Brightness control unavailable on this display.")
            return False
        target = max(0, min(100, int(current) + delta))
        if target == int(current):
            # Already at the limit: not an error, but the indicator should
            # still show where the level sits.
            self.brightness_level = int(current)
            return True  # already at the limit; not an error
        if not self.backend.set_brightness(target):
            log.warning("Setting brightness to %d%% failed.", target)
            return False
        self.brightness_level = target
        log.info("Brightness %d%% -> %d%%", int(current), target)
        return True
