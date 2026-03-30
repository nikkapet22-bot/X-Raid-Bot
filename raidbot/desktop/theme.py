from __future__ import annotations

# ── Core Palette ──────────────────────────────────────────────────────────────
WINDOW_BG     = "#060c18"
SURFACE_BG    = "#0a1628"
ELEVATED_BG   = "#0e1e35"
DEEP_BG       = "#040912"
SIDEBAR_BG    = "#070e1d"

ACCENT        = "#4f8ef7"
ACCENT_HOVER  = "#6ba3f9"
ACCENT_DIM    = "#1a3a7a"

TEXT          = "#dce8ff"
MUTED         = "#4e6a94"
SUBTLE        = "#253550"
PRIMARY_TEXT  = "#ffffff"

BORDER        = "#142035"
BORDER_MED    = "#1e3252"
BORDER_FOCUS  = "#4f8ef7"

SUCCESS       = "#2dd4bf"
SUCCESS_DIM   = "#0d3d37"
SUCCESS_TEXT  = "#99f6ec"

WARNING       = "#fb923c"
WARNING_DIM   = "#431e0a"

ERROR         = "#f87171"
ERROR_DIM     = "#3d0f0f"
ERROR_TEXT    = "#fca5a5"

# ── Object names ──────────────────────────────────────────────────────────────
SECTION_OBJECT_NAME = "section"
CARD_OBJECT_NAME    = "card"

# ── Geometry ─────────────────────────────────────────────────────────────────
SECTION_RADIUS       = 12
CARD_RADIUS          = 10
INPUT_RADIUS         = 8
GROUP_BOX_RADIUS     = 10
TAB_RADIUS           = 8
BUTTON_RADIUS        = 8
NAV_SIDEBAR_WIDTH    = 210

# ── Spacing ───────────────────────────────────────────────────────────────────
INPUT_PADDING_Y           = 8
INPUT_PADDING_X           = 12
BUTTON_PADDING_X          = 20
LIST_PADDING              = 4
GROUP_BOX_MARGIN_TOP      = 14
GROUP_BOX_PADDING         = 14
TAB_PADDING_Y             = 8
TAB_PADDING_X             = 16
GROUP_BOX_TITLE_PADDING_X = 6
NAV_BUTTON_MIN_WIDTH      = 100


def section_selector(name: str = SECTION_OBJECT_NAME) -> str:
    return f"QWidget#{name}"


def card_selector(name: str = CARD_OBJECT_NAME) -> str:
    return f"QFrame#{name}"


def wizard_nav_button_selector() -> str:
    return "QWizard QPushButton"


def build_application_stylesheet() -> str:
    return f"""
    QWidget {{
        background-color: {WINDOW_BG};
        color: {TEXT};
        font-size: 13px;
        font-family: "Segoe UI", system-ui, -apple-system, sans-serif;
    }}
    QMainWindow, QDialog {{
        background-color: {WINDOW_BG};
    }}

    {section_selector()} {{
        background-color: {SURFACE_BG};
        border: 1px solid {BORDER_MED};
        border-radius: {SECTION_RADIUS}px;
    }}
    {card_selector()} {{
        background-color: {ELEVATED_BG};
        border: 1px solid {BORDER};
        border-radius: {CARD_RADIUS}px;
    }}
    {card_selector()}[profileStatus="green"] {{
        background-color: {SUCCESS_DIM};
        border: 1px solid #1a4a40;
    }}
    {card_selector()}[profileStatus="red"] {{
        background-color: {ERROR_DIM};
        border: 1px solid #5a1a1a;
    }}

    QWidget#sidebar {{
        background-color: {SIDEBAR_BG};
        border-right: 1px solid {BORDER};
    }}
    QPushButton#navButton {{
        background-color: transparent;
        color: {MUTED};
        border: none;
        border-radius: 8px;
        text-align: left;
        padding: 10px 16px;
        font-size: 13px;
        font-weight: 500;
        min-height: 40px;
    }}
    QPushButton#navButton:hover {{
        background-color: {ELEVATED_BG};
        color: {TEXT};
    }}
    QPushButton#navButton[active="true"] {{
        background-color: {ACCENT_DIM};
        color: {ACCENT_HOVER};
        border-left: 3px solid {ACCENT};
        padding-left: 13px;
    }}

    QLabel {{
        color: {TEXT};
        background: transparent;
    }}
    QLabel[muted="true"] {{
        color: {MUTED};
        font-size: 12px;
    }}
    QLabel#sectionTitle {{
        font-size: 14px;
        font-weight: 600;
        color: {TEXT};
    }}
    QLabel#botActionGlyph {{
        font-size: 15px;
        font-weight: 700;
        color: {TEXT};
        letter-spacing: 0.3px;
    }}
    QLabel#botActionSlotMeta {{
        font-size: 11px;
        font-weight: 500;
        color: {MUTED};
    }}
    QLabel#pageTitle {{
        font-size: 20px;
        font-weight: 700;
        color: {TEXT};
    }}
    QLabel#metricValue {{
        font-size: 23px;
        font-weight: 700;
        color: {TEXT};
    }}
    QLabel#metricTitle {{
        font-size: 10px;
        font-weight: 500;
        color: {MUTED};
        letter-spacing: 0.3px;
    }}
    QLabel#appName {{
        font-size: 14px;
        font-weight: 700;
        color: {TEXT};
    }}
    QLabel#wizardHeadline {{
        font-size: 22px;
        font-weight: 700;
        color: {TEXT};
    }}

    QLabel[stateVariant="running"] {{ color: {SUCCESS}; font-weight: 600; }}
    QLabel[stateVariant="active"]  {{ color: {WARNING}; font-weight: 600; }}
    QLabel[stateVariant="error"]   {{ color: {ERROR};   font-weight: 600; }}
    QLabel[stateVariant="neutral"] {{ color: {MUTED}; }}

    QLabel#statusDot {{
        min-width: 9px; max-width: 9px;
        min-height: 9px; max-height: 9px;
        border-radius: 4px;
        background-color: {MUTED};
    }}
    QLabel#statusDot[stateVariant="running"] {{ background-color: {SUCCESS}; }}
    QLabel#statusDot[stateVariant="active"]  {{ background-color: {WARNING}; }}
    QLabel#statusDot[stateVariant="error"]   {{ background-color: {ERROR}; }}
    QLabel#statusDot[stateVariant="neutral"] {{ background-color: {MUTED}; }}

    QLineEdit, QComboBox, QAbstractSpinBox, QTextEdit, QPlainTextEdit {{
        background-color: {DEEP_BG};
        color: {TEXT};
        border: 1px solid {BORDER_MED};
        border-radius: {INPUT_RADIUS}px;
        padding: {INPUT_PADDING_Y}px {INPUT_PADDING_X}px;
        selection-background-color: {ACCENT_DIM};
        selection-color: {PRIMARY_TEXT};
    }}
    QLineEdit:focus, QComboBox:focus, QAbstractSpinBox:focus,
    QTextEdit:focus, QPlainTextEdit:focus {{
        border-color: {BORDER_FOCUS};
        background-color: {SURFACE_BG};
    }}
    QLineEdit:disabled, QComboBox:disabled {{
        color: {SUBTLE};
        background-color: {SURFACE_BG};
        border-color: {BORDER};
    }}
    QComboBox::drop-down {{ border: none; width: 26px; }}
    QComboBox QAbstractItemView {{
        background-color: {ELEVATED_BG};
        border: 1px solid {BORDER_MED};
        border-radius: {INPUT_RADIUS}px;
        color: {TEXT};
        selection-background-color: {ACCENT_DIM};
        selection-color: {PRIMARY_TEXT};
        padding: 4px;
    }}

    QListWidget {{
        background-color: {DEEP_BG};
        color: {TEXT};
        border: 1px solid {BORDER_MED};
        border-radius: {INPUT_RADIUS}px;
        padding: {LIST_PADDING}px;
        outline: none;
    }}
    QListWidget::item {{ padding: 7px 10px; border-radius: 6px; color: {TEXT}; }}
    QListWidget::item:hover    {{ background-color: {ELEVATED_BG}; }}
    QListWidget::item:selected {{ background-color: {ACCENT_DIM}; color: {ACCENT_HOVER}; }}
    QListWidget#activityList {{
        background-color: transparent;
        border: none;
        padding: 0;
    }}
    QListWidget#activityList::item {{
        background: transparent;
        border: none;
        padding: 0;
        margin: 0 0 6px 0;
    }}
    QFrame#activityCard {{
        background-color: #091427;
        border: 1px solid {BORDER_MED};
        border-radius: 10px;
    }}
    QLabel#activityTime {{
        color: {MUTED};
        font-size: 11px;
        letter-spacing: 0.2px;
    }}
    QLabel#activityUrl {{
        color: {ACCENT_HOVER};
        font-size: 12px;
        font-weight: 500;
    }}
    QLabel#activityReason {{
        color: {MUTED};
        font-size: 12px;
    }}
    QLabel#activityBadge {{
        border-radius: 999px;
        padding: 4px 12px;
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 0.5px;
        border: 1px solid transparent;
    }}
    QLabel#activityBadge[activityTone="accent"] {{
        background-color: #1d4aa6;
        border-color: #3167d7;
        color: #b7d4ff;
    }}
    QLabel#activityBadge[activityTone="success"] {{
        background-color: #0f5a4d;
        border-color: #1f8d79;
        color: #7ff0de;
    }}
    QLabel#activityBadge[activityTone="warning"] {{
        background-color: #7b3b08;
        border-color: #c86518;
        color: #ffc68f;
    }}
    QLabel#activityBadge[activityTone="error"] {{
        background-color: #7a1f25;
        border-color: #ca4c55;
        color: #ffb4b9;
    }}

    QScrollBar:vertical {{
        background: transparent; width: 6px; margin: 0;
    }}
    QScrollBar::handle:vertical {{
        background: {BORDER_MED}; border-radius: 3px; min-height: 20px;
    }}
    QScrollBar::handle:vertical:hover {{ background: {MUTED}; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QScrollBar:horizontal {{
        background: transparent; height: 6px;
    }}
    QScrollBar::handle:horizontal {{
        background: {BORDER_MED}; border-radius: 3px; min-width: 20px;
    }}
    QScrollBar::handle:horizontal:hover {{ background: {MUTED}; }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
    QScrollArea {{ border: none; background: transparent; }}

    QGroupBox {{
        background-color: transparent;
        border: 1px solid {BORDER_MED};
        border-radius: {GROUP_BOX_RADIUS}px;
        margin-top: {GROUP_BOX_MARGIN_TOP}px;
        padding: {GROUP_BOX_PADDING}px;
        font-weight: 500;
    }}
    QGroupBox::title {{
        color: {MUTED};
        subcontrol-origin: margin;
        subcontrol-position: top left;
        padding: 0 {GROUP_BOX_TITLE_PADDING_X}px;
        font-size: 11px;
    }}

    QTabWidget::pane {{
        border: 1px solid {BORDER_MED};
        border-radius: {GROUP_BOX_RADIUS}px;
        background: {SURFACE_BG};
        top: -1px;
    }}
    QTabBar {{ background: transparent; }}
    QTabBar::tab {{
        background: transparent;
        color: {MUTED};
        padding: {TAB_PADDING_Y}px {TAB_PADDING_X}px;
        border: none;
        border-bottom: 2px solid transparent;
        margin-right: 4px;
        font-size: 13px;
        font-weight: 500;
    }}
    QTabBar::tab:selected {{
        color: {TEXT};
        border-bottom: 2px solid {ACCENT};
    }}
    QTabBar::tab:hover:!selected {{ color: {TEXT}; }}

    QPushButton {{
        min-height: 34px;
        border-radius: {BUTTON_RADIUS}px;
        border: 1px solid {BORDER_MED};
        background-color: {ELEVATED_BG};
        color: {TEXT};
        padding: 0 {BUTTON_PADDING_X}px;
        font-size: 13px;
        font-weight: 500;
    }}
    QPushButton:hover {{
        border-color: {ACCENT};
        background-color: #11253f;
    }}
    QPushButton:pressed  {{ background-color: {SURFACE_BG}; }}
    QPushButton:disabled {{
        color: {SUBTLE}; border-color: {BORDER}; background-color: {SURFACE_BG};
    }}
    QPushButton[variant="primary"] {{
        background-color: {ACCENT}; color: {PRIMARY_TEXT};
        border-color: {ACCENT}; font-weight: 600;
    }}
    QPushButton[variant="primary"]:hover {{
        background-color: {ACCENT_HOVER}; border-color: {ACCENT_HOVER};
    }}
    QPushButton[variant="primary"]:pressed {{ background-color: {ACCENT_DIM}; }}
    QPushButton[variant="danger"] {{
        background-color: {ERROR}; color: {PRIMARY_TEXT};
        border-color: {ERROR}; font-weight: 600;
    }}
    QPushButton[variant="danger"]:hover  {{
        background-color: {ERROR_TEXT}; border-color: {ERROR_TEXT};
    }}
    QPushButton[variant="danger"]:disabled {{
        background-color: {ERROR_DIM}; border-color: {ERROR_DIM}; color: {MUTED};
    }}
    QPushButton[variant="secondary"] {{
        background-color: {ELEVATED_BG}; color: {TEXT}; border-color: {BORDER_MED};
    }}
    QPushButton[variant="quiet"] {{
        background-color: transparent; color: {MUTED}; border-color: transparent;
    }}
    QPushButton[variant="quiet"]:hover {{
        background-color: {ELEVATED_BG}; color: {TEXT}; border-color: transparent;
    }}
    QWidget#botActionButtonRow {{
        background: transparent;
    }}
    QPushButton[botActionButton="true"] {{
        min-height: 30px;
        border-radius: 999px;
        padding: 0 14px;
        font-size: 12px;
        font-weight: 600;
        background-color: #0d1c30;
        border-color: #244262;
    }}
    QPushButton[botActionButton="true"]:hover {{
        background-color: #122744;
        border-color: #2c5a86;
    }}
    QPushButton[botActionButton="true"]:pressed {{
        background-color: #0a1627;
    }}

    {wizard_nav_button_selector()} {{ min-width: {NAV_BUTTON_MIN_WIDTH}px; }}

    QWidget#wizardSurface {{
        background-color: {SURFACE_BG};
        border: 1px solid {BORDER_MED};
        border-radius: {SECTION_RADIUS}px;
    }}
    QFrame#wizardHeader {{ background: transparent; border: none; }}

    QToolTip {{
        background-color: {ELEVATED_BG};
        color: {TEXT};
        border: 1px solid {BORDER_MED};
        border-radius: 6px;
        padding: 6px 10px;
        font-size: 12px;
    }}

    QCheckBox {{ color: {TEXT}; spacing: 8px; }}
    QCheckBox::indicator {{
        width: 16px; height: 16px;
        border: 1px solid {BORDER_MED};
        border-radius: 4px;
        background-color: {DEEP_BG};
    }}
    QCheckBox::indicator:checked {{ background-color: {ACCENT}; border-color: {ACCENT}; }}
    QCheckBox::indicator:hover   {{ border-color: {ACCENT}; }}

    QLabel#botActionsStatusValue {{
        color: {PRIMARY_TEXT};
        font-size: 15px;
        font-weight: 700;
    }}
    QLabel#botActionsStatusMetaValue {{
        color: {TEXT};
        font-size: 13px;
        font-weight: 500;
    }}
    QLabel#botActionsStatusErrorValue {{
        color: {ERROR_TEXT};
        font-size: 13px;
        font-weight: 600;
    }}
    """
