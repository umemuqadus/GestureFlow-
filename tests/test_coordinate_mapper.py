"""Tests for coordinate mapping and cursor smoothing."""

from __future__ import annotations

from controller.coordinate_mapper import CoordinateMapper
from controller.cursor_smoother import CursorSmoother, EmaSmoother, OneEuroFilter

SCREEN = (1920, 1080)


def make_mapper(**kwargs) -> CoordinateMapper:
    return CoordinateMapper(screen_size=lambda: SCREEN, **kwargs)


def test_centre_maps_to_centre():
    mapper = make_mapper(roi_fraction=1.0)
    x, y = mapper.to_screen(0.5, 0.5)
    assert abs(x - 960) <= 1 and abs(y - 540) <= 1


def test_roi_maps_region_to_full_screen():
    """With ROI 0.5, the central half of the frame spans the whole screen."""
    mapper = make_mapper(roi_fraction=0.5)
    left, _ = mapper.to_screen(0.25, 0.5)     # left edge of ROI
    right, _ = mapper.to_screen(0.75, 0.5)    # right edge of ROI
    assert left <= 1
    assert right >= SCREEN[0] - 2


def test_coordinates_are_clamped_to_screen():
    mapper = make_mapper(roi_fraction=1.0, speed=5.0)
    for nx, ny in ((-0.5, -0.5), (1.5, 1.5), (2.0, 0.5)):
        x, y = mapper.to_screen(nx, ny)
        assert 0 <= x < SCREEN[0]
        assert 0 <= y < SCREEN[1]


def test_invert_x_flips_horizontal():
    normal = make_mapper(roi_fraction=1.0)
    inverted = make_mapper(roi_fraction=1.0, invert_x=True)
    nx = 0.25
    x_normal, _ = normal.to_screen(nx, 0.5)
    x_inverted, _ = inverted.to_screen(nx, 0.5)
    assert x_inverted > x_normal


def test_invert_y_flips_vertical():
    normal = make_mapper(roi_fraction=1.0)
    inverted = make_mapper(roi_fraction=1.0, invert_y=True)
    _, y_normal = normal.to_screen(0.5, 0.25)
    _, y_inverted = inverted.to_screen(0.5, 0.25)
    assert y_inverted > y_normal


def test_speed_scales_sensitivity():
    slow = make_mapper(roi_fraction=1.0, speed=1.0)
    fast = make_mapper(roi_fraction=1.0, speed=2.0)
    # The same small motion covers more distance at higher speed.
    x_slow, _ = slow.to_screen(0.5, 0.5)
    x_fast, _ = fast.to_screen(0.51, 0.5)
    assert abs(x_fast - 960) > abs(x_slow - 960)


def test_to_screen_matches_two_stage_api():
    mapper = make_mapper(roi_fraction=0.62, speed=1.3)
    direct = mapper.to_screen(0.3, 0.7)
    vx, vy = mapper.to_virtual(0.3, 0.7)
    staged = mapper.virtual_to_pixels(vx, vy)
    assert direct == staged


def test_custom_screen_size_is_honoured():
    mapper = CoordinateMapper(screen_size=lambda: (800, 600), roi_fraction=1.0)
    x, y = mapper.to_screen(0.99, 0.99)
    assert x < 800 and y < 600


def test_invalid_screen_size_raises():
    mapper = CoordinateMapper(screen_size=lambda: (0, 0))
    try:
        mapper.to_screen(0.5, 0.5)
    except ValueError:
        pass
    else:  # pragma: no cover
        raise AssertionError("expected ValueError for invalid screen size")


def test_never_targets_pyautogui_failsafe_corner():
    """The mapper must never emit the exact top-left pixel (0, 0).

    PyAutoGUI's fail-safe treats (0, 0) as its emergency corner: once the real
    cursor lands there, every subsequent mouse call raises FailSafeException —
    including the call that would move it away — deadlocking control.  Even
    inputs far outside the frame (which map to virtual 0,0) are clamped to a
    safe inset so the deadlock cannot be reached from the controller's own
    output.
    """
    mapper = make_mapper(roi_fraction=1.0, speed=5.0)
    for nx, ny in ((-0.5, -0.5), (0.0, 0.0), (0.25, 0.0), (0.0, 0.25), (2.0, -1.0)):
        x, y = mapper.to_screen(nx, ny)
        assert (x, y) != (0, 0)
        assert x >= 1 and y >= 1


# ---------------------------------------------------------------------------
# Smoothing
# ---------------------------------------------------------------------------
def test_ema_first_sample_passes_through():
    ema = EmaSmoother(smoothing=0.9)
    assert ema(10.0, 20.0) == (10.0, 20.0)


def test_ema_reduces_jump():
    ema = EmaSmoother(smoothing=0.9)
    ema(0.0, 0.0)
    x, _ = ema(100.0, 0.0)
    assert 0.0 < x < 100.0


def test_ema_alpha_increases_as_smoothing_decreases():
    assert EmaSmoother(0.0).alpha > EmaSmoother(0.9).alpha


def test_one_euro_converges_to_constant():
    filt = OneEuroFilter()
    out = None
    for i in range(120):
        out = filt(5.0, 5.0, i / 60.0)
    assert abs(out[0] - 5.0) < 0.01
    assert abs(out[1] - 5.0) < 0.01


def test_one_euro_reset_forgets_state():
    filt = OneEuroFilter()
    filt(0.0, 0.0, 0.0)
    filt.reset()
    assert filt(50.0, 50.0, 0.1) == (50.0, 50.0)


def test_cursor_smoother_switches_strategies():
    smoother = CursorSmoother(smoothing=0.5, use_one_euro=True)
    smoother(1.0, 1.0, 0.0)
    smoother.update(use_one_euro=False)
    smoother.reset()
    assert smoother(5.0, 5.0, 0.1) == (5.0, 5.0)  # EMA path, first sample passes
