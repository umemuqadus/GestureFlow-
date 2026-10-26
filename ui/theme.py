"""Theme definitions and stylesheet loading.

``build_qss()`` reads ``ui/styles.qss`` and substitutes ``@@token@@`` colour
placeholders for the selected theme (light or dark).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

_QSS_PATH = Path(__file__).resolve().parent / "styles.qss"


@dataclass(frozen=True)
class Theme:
    name: str
    background: str
    sidebar: str
    surface: str
    header: str
    field: str
    border: str
    hover: str
    text: str
    muted: str
    muted_soft: str
    accent: str
    accent_hover: str
    accent_soft: str
    on_accent: str
    danger: str
    danger_hover: str
    danger_soft: str
    ok: str
    ok_soft: str
    warn: str
    warn_soft: str


LIGHT = Theme(
    name="light",
    background="#F5F6FB",
    sidebar="#FFFFFF",
    surface="#FFFFFF",
    header="#FAFAFE",
    field="#FBFBFE",
    border="#E6E8F2",
    hover="#F1F2FA",
    text="#1B2559",
    muted="#6B7295",
    muted_soft="#EEF0F8",
    accent="#5B6CFF",
    accent_hover="#4A5AF0",
    accent_soft="#ECEDFF",
    on_accent="#FFFFFF",
    danger="#E0475B",
    danger_hover="#CF3D50",
    danger_soft="#FDECEF",
    ok="#0FA47F",
    ok_soft="#E4F7F1",
    warn="#B7791F",
    warn_soft="#FCF3E3",
)

DARK = Theme(
    name="dark",
    background="#0E1120",
    sidebar="#131729",
    surface="#171C31",
    header="#1B2138",
    field="#141A2E",
    border="#282F4C",
    hover="#1E2440",
    text="#E9ECFB",
    muted="#9AA2C7",
    muted_soft="#232A45",
    accent="#8B8CFF",
    accent_hover="#7A7BF5",
    accent_soft="#242850",
    on_accent="#0E1120",
    danger="#FF6B81",
    danger_hover="#F2556D",
    danger_soft="#331826",
    ok="#3ED2A6",
    ok_soft="#12312A",
    warn="#E8B44A",
    warn_soft="#332913",
)


def theme_by_name(name: str) -> Theme:
    return DARK if name == "dark" else LIGHT


def build_qss(theme: Theme) -> str:
    """Load the stylesheet template and substitute theme colour tokens."""
    template = _QSS_PATH.read_text(encoding="utf-8")
    tokens = {
        "background": theme.background,
        "sidebar": theme.sidebar,
        "surface": theme.surface,
        "header": theme.header,
        "field": theme.field,
        "border": theme.border,
        "hover": theme.hover,
        "text": theme.text,
        "muted": theme.muted,
        "muted_soft": theme.muted_soft,
        "accent": theme.accent,
        "accent_hover": theme.accent_hover,
        "accent_soft": theme.accent_soft,
        "on_accent": theme.on_accent,
        "danger": theme.danger,
        "danger_hover": theme.danger_hover,
        "danger_soft": theme.danger_soft,
        "ok": theme.ok,
        "ok_soft": theme.ok_soft,
        "warn": theme.warn,
        "warn_soft": theme.warn_soft,
    }
    qss = template
    for token, value in tokens.items():
        qss = qss.replace(f"@@{token}@@", value)
    return qss
