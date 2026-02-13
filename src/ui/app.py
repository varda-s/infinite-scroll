"""Main NiceGUI application entry point."""

import asyncio

from nicegui import app, ui

from src.ui.database.connection import init_db
from src.ui.database.repository import ConfigRepository
from src.ui.components.device_panel import create_device_panel
from src.ui.components.printer_panel import create_printer_panel
from src.ui.components.live_session import create_live_session
from src.ui.components.receipt_viewer import create_receipt_viewer
from src.ui.components.admin_config import create_admin_page
from src.ui.components.auth import create_login_page, create_signup_page, require_auth, get_current_user
from src.ui.components.sidebar import create_sidebar, create_header_with_menu
from src.ui.components.history_page import create_history_page
from src.ui.services.device_service import device_service
from src.ui.services.media_paths import OUTPUT_ROOT
from src.ui.services.tracking_service import tracking_service
from src.ui.state import app_state


def create_dashboard() -> None:
    """Create the main dashboard UI layout."""
    # Add custom styles
    ui.add_head_html("""
    <style>
        .animate-pulse {
            animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
        }
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
    </style>
    """)

    # Create sidebar drawer
    with ui.left_drawer(value=False).classes("bg-gray-800") as drawer:
        with ui.column().classes("w-full p-4"):
            ui.label("Navigation").classes("text-white font-bold text-lg mb-4")

            # Dashboard link
            with ui.link(target="/").classes("w-full no-underline"):
                with ui.row().classes(
                    "w-full items-center gap-3 p-3 rounded hover:bg-gray-700 cursor-pointer"
                ):
                    ui.icon("dashboard").classes("text-xl text-gray-300")
                    ui.label("Dashboard").classes("text-gray-200")

            # Session History link
            with ui.link(target="/history").classes("w-full no-underline"):
                with ui.row().classes(
                    "w-full items-center gap-3 p-3 rounded hover:bg-gray-700 cursor-pointer"
                ):
                    ui.icon("history").classes("text-xl text-gray-300")
                    ui.label("Session History").classes("text-gray-200")

            ui.separator().classes("bg-gray-700 my-2")

            # Admin link
            with ui.link(target="/admin").classes("w-full no-underline"):
                with ui.row().classes(
                    "w-full items-center gap-3 p-3 rounded hover:bg-gray-700 cursor-pointer"
                ):
                    ui.icon("settings").classes("text-xl text-gray-300")
                    ui.label("Settings").classes("text-gray-200")

    # Header with hamburger menu
    with ui.header().classes("bg-gradient-to-r from-purple-600 to-pink-500"):
        with ui.row().classes("w-full items-center justify-between px-4"):
            # Left: Hamburger menu
            ui.button(icon="menu", on_click=drawer.toggle).props("flat round color=white")

            # Center: Title
            with ui.row().classes("items-center gap-2"):
                ui.icon("videocam").classes("text-2xl text-white")
                ui.label("Instagram Reel Tracker").classes("text-xl font-bold text-white")
                pairing_badge = ui.label("").classes("text-xs px-2 py-1 rounded bg-white/20 text-white")

                def update_pairing_badge() -> None:
                    if app_state.connected_device:
                        pairing_badge.text = "Device Paired"
                        pairing_badge.classes(
                            remove="bg-red-500/70",
                            add="bg-green-500/70",
                        )
                    elif app_state.uxplay_pairing_code:
                        pairing_badge.text = f"Pairing Ready PIN {app_state.uxplay_pairing_code}"
                        pairing_badge.classes(
                            remove="bg-red-500/70",
                            add="bg-green-500/70",
                        )
                    else:
                        pairing_badge.text = "Pairing Initializing"
                        pairing_badge.classes(
                            remove="bg-green-500/70",
                            add="bg-red-500/70",
                        )

                update_pairing_badge()
                ui.timer(0.5, update_pairing_badge)

            # Right: spacer
            ui.element("div").classes("w-10")

    # Main content
    with ui.column().classes("w-full max-w-6xl mx-auto p-4 gap-4"):
        # Status message for auto-start
        status_label = ui.label("").classes("text-lg text-center w-full")

        def update_status():
            if app_state.session_active:
                status_label.text = "Recording... Scroll through Reels!"
                status_label.classes(remove="text-gray-500 text-yellow-600", add="text-green-600")
            elif app_state.connected_device:
                status_label.text = "ReelTracker mirror connected. Click Start Session, then scroll Reels."
                status_label.classes(remove="text-gray-500 text-green-600", add="text-yellow-600")
            else:
                if app_state.connected_device:
                    status_label.text = "ReelTracker mirror connected. Click Start Session, then scroll Reels."
                elif app_state.uxplay_pairing_code:
                    status_label.text = (
                        "Waiting for ReelTracker mirror... connect via AirPlay "
                        f"with PIN {app_state.uxplay_pairing_code}."
                    )
                else:
                    status_label.text = "Waiting for ReelTracker mirror... starting uxplay."
                status_label.classes(remove="text-yellow-600 text-green-600", add="text-gray-500")

        update_status()
        ui.timer(0.5, update_status)

        # Top row: Device/Printer panels and Live Session
        with ui.row().classes("w-full gap-4"):
            # Left column: Device and Printer panels
            with ui.column().classes("w-72 gap-4"):
                create_device_panel()
                create_printer_panel(
                    on_start_session=on_start_session,
                    on_stop_session=on_stop_session,
                )

            # Right column: Live Session and Receipt
            with ui.column().classes("flex-1 gap-4"):
                with ui.row().classes("w-full gap-4"):
                    with ui.column().classes("flex-1"):
                        create_live_session()
                    with ui.column().classes("flex-1"):
                        create_receipt_viewer()


def on_start_session() -> None:
    """Handle start session button click."""
    # Start session without user association (booth mode)
    success = tracking_service.start_session(user_id=None)
    if success:
        ui.notify("Session started. Scroll Reels to track timings and print live receipt.", type="positive")
    else:
        ui.notify("Failed to start session. Connect ReelTracker mirror first.", type="negative")


def on_stop_session() -> None:
    """Handle stop session button click."""
    tracking_service.stop_session()
    ui.notify("Session stopped", type="info")


async def startup() -> None:
    """Application startup tasks."""
    # Initialize database
    init_db()

    # Initialize default config values
    ConfigRepository.init_defaults()

    # Start device polling
    await device_service.start()


async def shutdown() -> None:
    """Application shutdown tasks."""
    # Stop device polling
    await device_service.stop()

    # Stop any active session
    tracking_service.stop_session()


def run(host: str = "127.0.0.1", port: int = 8080) -> None:
    """Run the NiceGUI application.

    Args:
        host: Host to bind to.
        port: Port to bind to.
    """
    # Enable storage for user sessions
    app.storage.secret = "instagram-reel-tracker-secret-key"

    # Ensure pairing is ready before serving UI so users immediately see a PIN.
    if not device_service.ensure_pairing_ready(timeout_seconds=3.0):
        raise RuntimeError(
            "Failed to initialize ReelTracker pairing within 3 seconds. "
            "Check uxplay availability and try again."
        )

    # Serve output media (screenshots/replays) as browser-accessible static files.
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    app.add_static_files("/output", str(OUTPUT_ROOT))

    # Register startup/shutdown handlers
    app.on_startup(startup)
    app.on_shutdown(shutdown)

    # Main dashboard (no auth for booth mode)
    @ui.page("/")
    def index():
        create_dashboard()

    # Session history page
    @ui.page("/history")
    def history():
        create_history_page()

    # Admin page
    @ui.page("/admin")
    def admin():
        create_admin_page()

    # Run the app
    ui.run(
        host=host,
        port=port,
        title="Instagram Reel Tracker",
        favicon="🎬",
        reload=False,
        storage_secret="instagram-reel-tracker-secret",
    )


if __name__ == "__main__":
    run()
