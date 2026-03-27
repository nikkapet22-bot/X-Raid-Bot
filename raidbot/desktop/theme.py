from __future__ import annotations

WINDOW_BG = "#0b1220"
SURFACE_BG = "#0f1724"
ELEVATED_BG = "#131d2d"
ACCENT = "#2f7ef7"
TEXT = "#edf3ff"
MUTED = "#90a0bd"
BORDER = "#22314a"
ERROR = "#ff6b81"
PRIMARY_TEXT = "#ffffff"

SECTION_OBJECT_NAME = "section"
CARD_OBJECT_NAME = "card"

SECTION_RADIUS = 14
CARD_RADIUS = 14
INPUT_RADIUS = 10
GROUP_BOX_RADIUS = 12
TAB_RADIUS = 10
BUTTON_RADIUS = 10

INPUT_PADDING_Y = 8
INPUT_PADDING_X = 10
BUTTON_PADDING_X = 14
LIST_PADDING = 4
GROUP_BOX_MARGIN_TOP = 12
GROUP_BOX_PADDING = 10
TAB_PADDING_Y = 8
TAB_PADDING_X = 14
GROUP_BOX_TITLE_PADDING_X = 6
NAV_BUTTON_MIN_WIDTH = 96


def section_selector(name: str = SECTION_OBJECT_NAME) -> str:
    return f'QWidget#{name}'


def card_selector(name: str = CARD_OBJECT_NAME) -> str:
    return f'QFrame#{name}'


def wizard_nav_button_selector() -> str:
    return "QWizard QPushButton"


def build_application_stylesheet() -> str:
    return f"""
    QWidget {{
        background-color: {WINDOW_BG};
        color: {TEXT};
    }}
    {section_selector()} {{
        background-color: {SURFACE_BG};
        border: 1px solid {BORDER};
        border-radius: {SECTION_RADIUS}px;
    }}
    {card_selector()} {{
        background-color: {ELEVATED_BG};
        border: 1px solid {BORDER};
        border-radius: {CARD_RADIUS}px;
    }}
    QLabel {{
        color: {TEXT};
    }}
    QLabel[muted="true"] {{
        color: {MUTED};
    }}
    QLineEdit,
    QComboBox,
    QTextEdit,
    QPlainTextEdit {{
        background-color: {SURFACE_BG};
        color: {TEXT};
        border: 1px solid {BORDER};
        border-radius: {INPUT_RADIUS}px;
        padding: {INPUT_PADDING_Y}px {INPUT_PADDING_X}px;
        selection-background-color: {ACCENT};
    }}
    QListWidget {{
        background-color: {SURFACE_BG};
        color: {TEXT};
        border: 1px solid {BORDER};
        border-radius: {INPUT_RADIUS}px;
        padding: {LIST_PADDING}px;
    }}
    QGroupBox {{
        background-color: transparent;
        border: 1px solid {BORDER};
        border-radius: {GROUP_BOX_RADIUS}px;
        margin-top: {GROUP_BOX_MARGIN_TOP}px;
        padding: {GROUP_BOX_PADDING}px;
    }}
    QGroupBox::title {{
        color: {TEXT};
        subcontrol-origin: margin;
        subcontrol-position: top left;
        padding: 0 {GROUP_BOX_TITLE_PADDING_X}px;
    }}
    QTabWidget::pane {{
        border: 1px solid {BORDER};
        border-radius: {GROUP_BOX_RADIUS}px;
        background: {SURFACE_BG};
    }}
    QTabBar::tab {{
        background: {ELEVATED_BG};
        color: {MUTED};
        padding: {TAB_PADDING_Y}px {TAB_PADDING_X}px;
        border: 1px solid {BORDER};
        border-bottom: none;
        border-top-left-radius: {TAB_RADIUS}px;
        border-top-right-radius: {TAB_RADIUS}px;
    }}
    QTabBar::tab:selected {{
        background: {SURFACE_BG};
        color: {TEXT};
    }}
    QPushButton {{
        min-height: 36px;
        border-radius: {BUTTON_RADIUS}px;
        border: 1px solid {BORDER};
        background-color: {ELEVATED_BG};
        color: {TEXT};
        padding: 0 {BUTTON_PADDING_X}px;
    }}
    QPushButton:hover {{
        border-color: {ACCENT};
    }}
    QPushButton:pressed {{
        background-color: {SURFACE_BG};
    }}
    QPushButton[variant="primary"] {{
        background-color: {ACCENT};
        color: {PRIMARY_TEXT};
        border-color: {ACCENT};
    }}
    QPushButton[variant="danger"] {{
        background-color: {ERROR};
        color: {PRIMARY_TEXT};
        border-color: {ERROR};
    }}
    QPushButton[variant="secondary"] {{
        background-color: {ELEVATED_BG};
        color: {TEXT};
        border-color: {BORDER};
    }}
    QPushButton[variant="quiet"] {{
        background-color: transparent;
        color: {MUTED};
        border-color: transparent;
    }}
    QPushButton[variant="quiet"]:hover {{
        background-color: {SURFACE_BG};
        color: {TEXT};
        border-color: transparent;
    }}
    {wizard_nav_button_selector()} {{
        min-width: {NAV_BUTTON_MIN_WIDTH}px;
    }}
    """
