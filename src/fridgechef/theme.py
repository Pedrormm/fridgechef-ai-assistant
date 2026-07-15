from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VisualTheme:
    """Small runtime theme descriptor used by the Streamlit UI.

    These presets only control visual styling. They do not affect prompts,
    inventory data, recipe generation or any guardrail.
    """

    key: str
    label: str


THEME_CURRENT = "current"
THEME_DARK = "streamlit_dark"
THEME_ELEGANT = "elegant_fridge"

_THEME_LABELS: dict[str, VisualTheme] = {
    THEME_CURRENT: VisualTheme(THEME_CURRENT, "Claro"),
    THEME_DARK: VisualTheme(THEME_DARK, "Oscuro"),
    THEME_ELEGANT: VisualTheme(THEME_ELEGANT, "Elegante"),
}


def theme_options() -> list[str]:
    """Return the three allowed theme keys in a stable order."""
    return [THEME_CURRENT, THEME_DARK, THEME_ELEGANT]


def theme_label(key: str) -> str:
    """Return the user-facing label for a theme key."""
    return _THEME_LABELS.get(key, _THEME_LABELS[THEME_CURRENT]).label


def build_theme_css(key: str) -> str:
    """Build the CSS override for the selected theme.

    The default theme intentionally returns a very small override because the
    main application stylesheet already represents the current design. Dark and
    elegant themes are layered after the base stylesheet, so they can change the
    visual system without touching application logic.
    """
    if key == THEME_DARK:
        return _dark_theme_css()
    if key == THEME_ELEGANT:
        return _elegant_theme_css()
    return _current_theme_css()


def _current_theme_css() -> str:
    """Keep the existing look as the default theme."""
    return """
    <style>
        :root { color-scheme: light; }
    </style>
    """


def _dark_theme_css() -> str:
    """Match Streamlit's native dark palette as closely as possible."""
    return """
    <style>
        :root {
            color-scheme: dark;
            --fc-primary: #FF4B4B;
            --fc-primary-strong: #FF4B4B;
            --fc-accent: #FF4B4B;
            --fc-warning: #F0B429;
            --fc-danger: #FF6B6B;
            --fc-border: rgba(250, 250, 250, 0.16);
            --fc-shadow: 0 18px 48px rgba(0, 0, 0, 0.35);
            --fc-radius: 18px;
            --fc-dark-bg: #0E1117;
            --fc-dark-secondary: #262730;
            --fc-dark-panel: #1B1C24;
            --fc-dark-text: #FAFAFA;
            --fc-dark-muted: rgba(250, 250, 250, 0.68);
        }

        .stApp {
            background: #0E1117 !important;
            color: #FAFAFA !important;
        }
        .block-container,
        [data-testid="stAppViewContainer"],
        [data-testid="stAppViewBlockContainer"] {
            color: #FAFAFA !important;
        }
        [data-testid="stHeader"] {
            background: #0E1117 !important;
        }
        section[data-testid="stSidebar"],
        section[data-testid="stSidebar"] > div:first-child,
        section[data-testid="stSidebar"] [data-testid="stSidebarContent"],
        section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] {
            background: #262730 !important;
            color: #FAFAFA !important;
            border-right-color: rgba(250, 250, 250, 0.14) !important;
        }
        h1, h2, h3, h4, h5, h6,
        p, li, label, span,
        .stMarkdown, .stMarkdown *,
        [data-testid="stCaptionContainer"],
        [data-testid="stCaptionContainer"] * {
            color: #FAFAFA !important;
        }
        .muted,
        [data-testid="stCaptionContainer"],
        [data-testid="stCaptionContainer"] * {
            color: rgba(250, 250, 250, 0.68) !important;
        }
        .hero-card,
        .recipe-card,
        div[data-testid="stVerticalBlockBorderWrapper"],
        div[data-testid="stExpander"],
        section[data-testid="stSidebar"] details,
        section[data-testid="stSidebar"] details > summary {
            background: #262730 !important;
            color: #FAFAFA !important;
            border-color: rgba(250, 250, 250, 0.16) !important;
            box-shadow: 0 14px 34px rgba(0, 0, 0, 0.32) !important;
        }
        .hero-card {
            background: linear-gradient(135deg, #262730 0%, #1B1C24 100%) !important;
        }
        .soft-note {
            background: #262730 !important;
            color: #FAFAFA !important;
            border-left-color: #F0B429 !important;
        }
        .success-soft {
            background: #12362B !important;
            color: #D1FAE5 !important;
            border-left-color: #10B981 !important;
        }
        .danger-soft {
            background: #3A2411 !important;
            color: #FED7AA !important;
            border-left-color: #F97316 !important;
        }
        textarea, input,
        [data-baseweb="select"] > div,
        [data-testid="stTextInput"] input,
        [data-testid="stTextArea"] textarea,
        [data-testid="stFileUploader"],
        [data-testid="stFileUploaderDropzone"],
        [data-testid="stCameraInput"] {
            background: #262730 !important;
            color: #FAFAFA !important;
            border-color: rgba(250, 250, 250, 0.16) !important;
        }
        textarea::placeholder,
        input::placeholder {
            color: rgba(250, 250, 250, 0.42) !important;
        }
        div.stButton > button,
        [data-testid="stFileUploaderDropzone"] button,
        [data-testid="stCameraInput"] button {
            background: #262730 !important;
            color: #FAFAFA !important;
            border: 1px solid rgba(250, 250, 250, 0.22) !important;
            box-shadow: 0 8px 22px rgba(0, 0, 0, 0.28) !important;
        }
        div.stButton > button[kind="primary"] {
            background: #FF4B4B !important;
            color: #FFFFFF !important;
            border-color: #FF4B4B !important;
        }
        [data-testid="stFileUploaderDropzone"] button::after,
        [data-testid="stFileUploader"] button::after,
        [data-testid="stCameraInput"] button::after {
            color: #FAFAFA !important;
        }
        [data-testid="stFileUploaderDropzone"] small::after,
        [data-testid="stFileUploaderDropzone"] > div:last-child::after,
        [data-testid="stCameraInput"] p::after {
            color: rgba(250, 250, 250, 0.68) !important;
        }
        div[data-baseweb="tab-list"] {
            border-bottom-color: rgba(250, 250, 250, 0.18) !important;
        }
        div[data-baseweb="tab"] p {
            color: rgba(250, 250, 250, 0.72) !important;
        }
        div[data-baseweb="tab"][aria-selected="true"] p {
            color: #FF4B4B !important;
        }
        hr {
            border-color: rgba(250, 250, 250, 0.16) !important;
        }

        @media (max-width: 768px) {
            section[data-testid="stSidebar"],
            section[data-testid="stSidebar"] > div:first-child,
            section[data-testid="stSidebar"] [data-testid="stSidebarContent"],
            section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] {
                background: #262730 !important;
                box-shadow: 14px 0 34px rgba(0, 0, 0, 0.48) !important;
            }
            [data-testid="stSidebarCollapsedControl"],
            [data-testid="collapsedControl"],
            [data-testid="stExpandSidebarButton"],
            [data-testid="stSidebarCollapseButton"],
            section[data-testid="stSidebar"] [data-testid="stSidebarCollapseButton"] {
                background: #262730 !important;
                color: #FAFAFA !important;
            }
        }
    </style>
    """


def _elegant_theme_css() -> str:
    """Create a more distinctive fridge-inspired visual theme."""
    return """
    <style>
        :root {
            color-scheme: light;
            --fc-primary: #35B7DA;
            --fc-primary-strong: #138FBA;
            --fc-accent: #58D6A6;
            --fc-warning: #FFB454;
            --fc-danger: #B45B1E;
            --fc-border: rgba(25, 89, 122, 0.16);
            --fc-shadow: 0 22px 58px rgba(42, 130, 176, 0.15);
            --fc-radius: 28px;
            --fc-elegant-text: #123047;
            --fc-elegant-muted: #5B7187;
            --fc-elegant-blue: #DDF6FF;
            --fc-elegant-surface: rgba(255, 255, 255, 0.90);
        }

        .stApp {
            background:
                radial-gradient(circle at 12% 10%, rgba(117, 210, 255, 0.26), transparent 28rem),
                radial-gradient(circle at 86% 8%, rgba(115, 226, 179, 0.20), transparent 30rem),
                radial-gradient(circle at 50% 105%, rgba(255, 210, 137, 0.16), transparent 28rem),
                linear-gradient(180deg, #F8FDFF 0%, #FFFFFF 52%, #F4FCFF 100%) !important;
            color: #123047 !important;
            font-family: "Trebuchet MS", "Aptos", "Segoe UI", system-ui, sans-serif !important;
        }
        [data-testid="stHeader"] {
            background: linear-gradient(180deg, rgba(248, 253, 255, 0.92), rgba(248, 253, 255, 0.62)) !important;
            backdrop-filter: blur(10px) !important;
        }
        .block-container {
            max-width: 1160px !important;
        }
        section[data-testid="stSidebar"],
        section[data-testid="stSidebar"] > div:first-child,
        section[data-testid="stSidebar"] [data-testid="stSidebarContent"],
        section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] {
            background:
                linear-gradient(180deg, rgba(221, 246, 255, 0.95) 0%, rgba(232, 251, 247, 0.95) 100%) !important;
            border-right: 1px solid rgba(53, 183, 218, 0.28) !important;
        }
        h1, h2, h3, h4, h5, h6 {
            color: #123047 !important;
            font-family: "Trebuchet MS", "Aptos Display", "Segoe UI", system-ui, sans-serif !important;
            letter-spacing: -0.045em !important;
        }
        p, li, label, span, .stMarkdown, .stMarkdown * {
            color: #123047;
        }
        .muted,
        [data-testid="stCaptionContainer"],
        [data-testid="stCaptionContainer"] * {
            color: #5B7187 !important;
        }
        .hero-card {
            position: relative;
            overflow: hidden;
            border: 1px solid rgba(53, 183, 218, 0.20) !important;
            background:
                radial-gradient(circle at 82% 20%, rgba(88, 214, 166, 0.16), transparent 15rem),
                linear-gradient(135deg, rgba(255, 255, 255, 0.96), rgba(225, 249, 255, 0.88)) !important;
            box-shadow: 0 24px 60px rgba(42, 130, 176, 0.16) !important;
            border-radius: 34px !important;
        }
        .hero-card::after {
            content: "❄️";
            position: absolute;
            right: 1.5rem;
            top: 0.9rem;
            font-size: clamp(2.4rem, 6vw, 4.7rem);
            opacity: 0.13;
            transform: rotate(12deg);
        }
        .hero-card h1 {
            text-shadow: 0 1px 0 rgba(255, 255, 255, 0.65);
        }
        .soft-note {
            background: linear-gradient(135deg, #FFF8E8, #ECFBFF) !important;
            border-left-color: #FFB454 !important;
            color: #7A4A08 !important;
            box-shadow: 0 12px 30px rgba(255, 180, 84, 0.10) !important;
        }
        .success-soft {
            background: linear-gradient(135deg, #E9FFF6, #F3FDFF) !important;
            border-left-color: #58D6A6 !important;
            color: #185C49 !important;
        }
        .danger-soft {
            background: linear-gradient(135deg, #FFF7ED, #F3FDFF) !important;
            border-left-color: #F59E0B !important;
            color: #7A3F0B !important;
        }
        .recipe-card,
        div[data-testid="stVerticalBlockBorderWrapper"] {
            background: rgba(255, 255, 255, 0.86) !important;
            border: 1px solid rgba(25, 89, 122, 0.14) !important;
            border-radius: 26px !important;
            box-shadow: 0 18px 46px rgba(42, 130, 176, 0.10) !important;
            backdrop-filter: blur(10px) !important;
        }

        section[data-testid="stSidebar"] details {
            border: 1px solid rgba(53, 183, 218, 0.22) !important;
            border-radius: 17px !important;
            background:
                linear-gradient(180deg, rgba(255,255,255,0.96), rgba(235,250,255,0.94)) !important;
            box-shadow: inset 0 -1px 0 rgba(53, 183, 218, 0.12), 0 8px 22px rgba(42, 130, 176, 0.08) !important;
            overflow: hidden !important;
        }
        section[data-testid="stSidebar"] details > summary {
            background:
                linear-gradient(90deg, rgba(221,246,255,0.94), rgba(255,255,255,0.96)) !important;
            border-bottom: 1px solid rgba(53, 183, 218, 0.12) !important;
            min-height: 2.9rem !important;
            align-items: center !important;
        }
        section[data-testid="stSidebar"] details > summary::before {
            content: "🧊";
            display: inline-flex;
            margin-right: 0.45rem;
            opacity: 0.95;
        }
        section[data-testid="stSidebar"] details[open] {
            background:
                repeating-linear-gradient(180deg, rgba(255,255,255,0.98) 0 3.2rem, rgba(232,249,255,0.88) 3.2rem 3.35rem) !important;
        }
        section[data-testid="stSidebar"] div[data-testid="stCheckbox"] label {
            border-radius: 14px !important;
            padding: 0.25rem 0.15rem !important;
        }
        section[data-testid="stSidebar"] div[data-testid="stCheckbox"] label:hover {
            background: rgba(53, 183, 218, 0.08) !important;
        }
        section[data-testid="stSidebar"] h2::before,
        section[data-testid="stSidebar"] h3::before {
            content: "🧺 ";
        }
        section[data-testid="stSidebar"] label p {
            font-weight: 680 !important;
        }
        textarea, input,
        [data-baseweb="select"] > div,
        [data-testid="stTextInput"] input,
        [data-testid="stTextArea"] textarea,
        [data-testid="stFileUploader"],
        [data-testid="stFileUploaderDropzone"],
        [data-testid="stCameraInput"] {
            background: rgba(248, 251, 255, 0.92) !important;
            border-color: rgba(53, 183, 218, 0.16) !important;
            border-radius: 18px !important;
            color: #123047 !important;
        }
        div.stButton > button {
            border-radius: 17px !important;
            border: 1px solid rgba(53, 183, 218, 0.20) !important;
            background: rgba(255, 255, 255, 0.92) !important;
            color: #123047 !important;
            box-shadow: 0 14px 32px rgba(42, 130, 176, 0.12) !important;
        }
        div.stButton > button:hover {
            border-color: rgba(53, 183, 218, 0.48) !important;
            transform: translateY(-2px) !important;
        }
        div.stButton > button[kind="primary"] {
            background: linear-gradient(135deg, #35B7DA, #138FBA) !important;
            color: #FFFFFF !important;
            border-color: rgba(19, 143, 186, 0.55) !important;
        }
        div[data-baseweb="tab-list"] {
            gap: 0.45rem !important;
            border-bottom-color: rgba(53, 183, 218, 0.20) !important;
        }
        div[data-baseweb="tab"] {
            border-radius: 999px 999px 0 0 !important;
        }
        div[data-baseweb="tab"] p::before {
            content: "🥬 ";
        }
        div[data-baseweb="tab"][aria-selected="true"] p {
            color: #138FBA !important;
            font-weight: 800 !important;
        }
        [data-testid="stFileUploaderDropzone"] button::after,
        [data-testid="stFileUploader"] button::after,
        [data-testid="stCameraInput"] button::after {
            color: #123047 !important;
        }

        @media (max-width: 768px) {
            .block-container {
                padding-top: 4.2rem !important;
                padding-left: 0.95rem !important;
                padding-right: 0.95rem !important;
            }
            .hero-card {
                border-radius: 28px !important;
                padding: 1.35rem !important;
            }
            .hero-card::after {
                right: 0.65rem;
                top: 0.4rem;
                font-size: 3.1rem;
            }
            section[data-testid="stSidebar"] {
                width: min(88vw, 23rem) !important;
                min-width: min(88vw, 23rem) !important;
                max-width: min(88vw, 23rem) !important;
            }
            section[data-testid="stSidebar"] > div:first-child,
            section[data-testid="stSidebar"] [data-testid="stSidebarContent"],
            section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] {
                width: 100% !important;
                max-width: 100% !important;
            }
            section[data-testid="stSidebar"],
            section[data-testid="stSidebar"] > div:first-child,
            section[data-testid="stSidebar"] [data-testid="stSidebarContent"],
            section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] {
                background: linear-gradient(180deg, #DDF6FF 0%, #EBFFF8 100%) !important;
                box-shadow: 14px 0 34px rgba(42, 130, 176, 0.24) !important;
            }
            section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] {
                padding-left: clamp(1rem, 5vw, 1.35rem) !important;
                padding-right: clamp(1rem, 5vw, 1.35rem) !important;
            }
            section[data-testid="stSidebar"] details {
                width: 100% !important;
                max-width: 100% !important;
                border-radius: 20px !important;
            }
            section[data-testid="stSidebar"] details > summary {
                display: flex !important;
                align-items: center !important;
                gap: 0.55rem !important;
                min-height: 3.4rem !important;
                padding: 0.7rem 0.9rem !important;
                box-sizing: border-box !important;
            }
            section[data-testid="stSidebar"] details > summary::before {
                flex: 0 0 2.1rem !important;
                width: 2.1rem !important;
                height: 2.1rem !important;
                margin-right: 0 !important;
                display: inline-flex !important;
                align-items: center !important;
                justify-content: center !important;
                border-radius: 14px !important;
                background: rgba(221, 246, 255, 0.88) !important;
                box-shadow: inset 0 0 0 1px rgba(53, 183, 218, 0.16) !important;
            }
            section[data-testid="stSidebar"] details > summary > * {
                min-width: 0 !important;
            }
            section[data-testid="stSidebar"] details > summary p,
            section[data-testid="stSidebar"] details > summary span {
                flex: 1 1 auto !important;
                width: auto !important;
                max-width: none !important;
                min-width: 0 !important;
                white-space: normal !important;
                overflow-wrap: normal !important;
                word-break: normal !important;
                line-height: 1.35 !important;
                text-align: left !important;
            }
            section[data-testid="stSidebar"] details > summary svg {
                flex: 0 0 auto !important;
                margin-left: auto !important;
            }
            section[data-testid="stSidebar"] div[data-testid="stCheckbox"] label {
                display: flex !important;
                align-items: center !important;
                gap: 0.55rem !important;
                min-height: 2.45rem !important;
                padding: 0.28rem 0.35rem !important;
            }
            section[data-testid="stSidebar"] div[data-testid="stCheckbox"] label p,
            section[data-testid="stSidebar"] div[data-testid="stCheckbox"] label span {
                white-space: normal !important;
                word-break: normal !important;
                line-height: 1.25 !important;
            }
            /*
               The elegant mobile sidebar is wider than the default Streamlit
               sidebar so the fridge-shelf option cards remain readable.
               Streamlit collapses the sidebar by translating it by the saved
               sidebar width; if we force a larger width without handling the
               collapsed state, a strip of the panel remains visible and blocks
               the app.  Only in the elegant mobile theme, when Streamlit marks
               the sidebar as collapsed, we reduce the panel to zero width and
               move it fully outside the viewport. The native expand button is
               kept visible below, so opening it again still works.
            */
            section[data-testid="stSidebar"][aria-expanded="false"] {
                width: 0 !important;
                min-width: 0 !important;
                max-width: 0 !important;
                transform: translateX(-110vw) !important;
                overflow: hidden !important;
                box-shadow: none !important;
                border-right: 0 !important;
                pointer-events: none !important;
            }
            section[data-testid="stSidebar"][aria-expanded="false"] > div:first-child,
            section[data-testid="stSidebar"][aria-expanded="false"] [data-testid="stSidebarContent"],
            section[data-testid="stSidebar"][aria-expanded="false"] [data-testid="stSidebarUserContent"] {
                width: 0 !important;
                min-width: 0 !important;
                max-width: 0 !important;
                padding-left: 0 !important;
                padding-right: 0 !important;
                overflow: hidden !important;
                opacity: 0 !important;
                pointer-events: none !important;
            }
            [data-testid="stSidebarCollapsedControl"],
            [data-testid="collapsedControl"],
            [data-testid="stExpandSidebarButton"],
            [data-testid="stSidebarCollapseButton"],
            section[data-testid="stSidebar"] [data-testid="stSidebarCollapseButton"] {
                background: rgba(255, 255, 255, 0.90) !important;
                color: #123047 !important;
                border: 1px solid rgba(53, 183, 218, 0.18) !important;
            }
            [data-testid="stSidebarCollapsedControl"],
            [data-testid="collapsedControl"],
            [data-testid="stExpandSidebarButton"] {
                pointer-events: auto !important;
                visibility: visible !important;
                opacity: 1 !important;
                z-index: 1000003 !important;
            }
        }
    </style>
    """
