"""UI components for the Instagram Reel Tracker."""

from src.ui.components.header import create_header
from src.ui.components.device_panel import create_device_panel
from src.ui.components.printer_panel import create_printer_panel
from src.ui.components.live_session import create_live_session
from src.ui.components.receipt_viewer import create_receipt_viewer
from src.ui.components.session_history import create_session_history
from src.ui.components.admin_config import create_admin_page
from src.ui.components.auth import create_login_page, create_signup_page
from src.ui.components.sidebar import create_sidebar, create_header_with_menu
from src.ui.components.history_page import create_history_page

__all__ = [
    "create_header",
    "create_device_panel",
    "create_printer_panel",
    "create_live_session",
    "create_receipt_viewer",
    "create_session_history",
    "create_admin_page",
    "create_login_page",
    "create_signup_page",
    "create_sidebar",
    "create_header_with_menu",
    "create_history_page",
]
