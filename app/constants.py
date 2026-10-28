"""Application-wide constants.

Every value here is a *default*. Runtime values live in
``app.config.AppConfig`` and are persisted through the settings service.
"""

from __future__ import annotations

APP_NAME = "GestureFlow AI"
APP_VERSION = "1.2.0"

# ---------------------------------------------------------------------------
# Hand landmark indices (MediaPipe hand model, 21 points).
# ---------------------------------------------------------------------------
WRIST = 0
THUMB_CMC, THUMB_MCP, THUMB_IP, THUMB_TIP = 1, 2, 3, 4
INDEX_MCP, INDEX_PIP, INDEX_DIP, INDEX_TIP = 5, 6, 7, 8
MIDDLE_MCP, MIDDLE_PIP, MIDDLE_DIP, MIDDLE_TIP = 9, 10, 11, 12
RING_MCP, RING_PIP, RING_DIP, RING_TIP = 13, 14, 15, 16
PINKY_MCP, PINKY_PIP, PINKY_DIP, PINKY_TIP = 17, 18, 19, 20

# ---------------------------------------------------------------------------
# Gesture identifiers
# ---------------------------------------------------------------------------
GESTURE_NONE = "none"
GESTURE_POINT = "point"            # index extended -> cursor movement
GESTURE_PINCH = "pinch"            # thumb+index pinch -> left click / drag
GESTURE_DRAG = "drag"              # hold pinch -> drag (behaviour flag)
GESTURE_DOUBLE_CLICK = "double_click"
GESTURE_RIGHT_CLICK = "right_pinch"  # thumb+middle pinch -> right click
GESTURE_SCROLL_V = "scroll_vertical"
GESTURE_SCROLL_H = "scroll_horizontal"
GESTURE_OPEN_PALM = "open_palm"    # pause
GESTURE_FIST = "fist"              # screenshot

# -- system-control gestures (added in 1.1) ---------------------------------
GESTURE_THUMB_UP = "thumb_up"            # volume up
GESTURE_THUMB_DOWN = "thumb_down"        # volume down
GESTURE_THREE_FINGERS = "three_fingers"  # brightness (pose + move up/down)
GESTURE_SHAKA = "shaka"                  # thumb + pinky -> mute toggle
GESTURE_FLAT_HAND = "flat_hand"          # four fingers, thumb tucked -> play/pause

GESTURE_LABELS: dict[str, str] = {
    GESTURE_NONE: "No hand",
    GESTURE_POINT: "Point (move cursor)",
    GESTURE_PINCH: "Pinch (click / drag)",
    GESTURE_DRAG: "Held pinch (drag)",
    GESTURE_DOUBLE_CLICK: "Double click",
    GESTURE_RIGHT_CLICK: "Middle pinch (right click)",
    GESTURE_SCROLL_V: "Two fingers (scroll)",
    GESTURE_SCROLL_H: "Two fingers sideways (scroll H)",
    GESTURE_OPEN_PALM: "Open palm (pause)",
    GESTURE_FIST: "Fist (screenshot)",
    GESTURE_THUMB_UP: "Thumb up (volume +)",
    GESTURE_THUMB_DOWN: "Thumb down (volume -)",
    GESTURE_THREE_FINGERS: "Three fingers (brightness)",
    GESTURE_SHAKA: "Thumb + pinky (mute)",
    GESTURE_FLAT_HAND: "Flat hand (play / pause)",
}

# ---------------------------------------------------------------------------
# Controller states
# ---------------------------------------------------------------------------
STATE_IDLE = "IDLE"
STATE_TRACKING = "TRACKING"
STATE_MOVING = "MOVING"
STATE_LEFT_CLICK = "LEFT_CLICK"
STATE_RIGHT_CLICK = "RIGHT_CLICK"
STATE_DOUBLE_CLICK = "DOUBLE_CLICK"
STATE_DRAGGING = "DRAGGING"
STATE_SCROLLING = "SCROLLING"
STATE_PAUSED = "PAUSED"
STATE_NO_HAND = "NO_HAND"
STATE_ERROR = "ERROR"
# System-control states (HUD feedback for the non-mouse actions).
STATE_VOLUME = "VOLUME"
STATE_BRIGHTNESS = "BRIGHTNESS"
STATE_SCREENSHOT = "SCREENSHOT"
STATE_MEDIA = "MEDIA"

# ---------------------------------------------------------------------------
# Mouse actions emitted by the state machine
# ---------------------------------------------------------------------------
ACTION_NONE = "none"
ACTION_MOVE = "move"
ACTION_LEFT_CLICK = "left_click"
ACTION_RIGHT_CLICK = "right_click"
ACTION_DOUBLE_CLICK = "double_click"
ACTION_DRAG_START = "drag_start"
ACTION_DRAG_MOVE = "drag_move"
ACTION_DRAG_END = "drag_end"
ACTION_SCROLL_V = "scroll_vertical"
ACTION_SCROLL_H = "scroll_horizontal"
ACTION_PAUSE = "pause"
ACTION_RESUME = "resume"

# -- system actions (non-mouse); executed by SystemController ----------------
ACTION_SCREENSHOT = "screenshot"
ACTION_VOLUME_UP = "volume_up"
ACTION_VOLUME_DOWN = "volume_down"
ACTION_VOLUME_MUTE = "volume_mute"
# "brightness" is the per-gesture rule descriptor; the state machine resolves
# it to the directional form below based on hand movement.
ACTION_BRIGHTNESS = "brightness"
ACTION_BRIGHTNESS_UP = "brightness_up"
ACTION_BRIGHTNESS_DOWN = "brightness_down"
ACTION_MEDIA_TOGGLE = "media_toggle"

# Discrete system actions fire at most once per held pose (repeat actions like
# volume keep firing on an interval instead).
DISCRETE_SYSTEM_ACTIONS: frozenset[str] = frozenset({
    ACTION_SCREENSHOT, ACTION_VOLUME_MUTE, ACTION_MEDIA_TOGGLE,
})

# ---------------------------------------------------------------------------
# Defaults (mirrored into AppDefaults in config.py; kept here for import-time
# safety so no module has to import config just for a literal).
# ---------------------------------------------------------------------------
DEFAULT_CAMERA_INDEX = 0
DEFAULT_CAPTURE_WIDTH = 1280
DEFAULT_CAPTURE_HEIGHT = 720
DEFAULT_DETECTION_CONFIDENCE = 0.6
DEFAULT_TRACKING_CONFIDENCE = 0.6
DEFAULT_MIRROR_PREVIEW = True
DEFAULT_CURSOR_SPEED = 1.0
DEFAULT_SMOOTHING = 0.55
DEFAULT_PINCH_THRESHOLD = 0.32
DEFAULT_RELEASE_THRESHOLD = 0.45
DEFAULT_RIGHT_PINCH_THRESHOLD = 0.34
DEFAULT_CLICK_COOLDOWN_MS = 260
DEFAULT_DOUBLE_CLICK_WINDOW_MS = 420
DEFAULT_DRAG_HOLD_MS = 320
DEFAULT_SCROLL_SENSITIVITY = 1.0
DEFAULT_SCROLL_DEADZONE_PX = 12
DEFAULT_PAUSE_HOLD_MS = 900
DEFAULT_MOVEMENT_DEADZONE = 0.006
DEFAULT_MAX_FPS = 30
