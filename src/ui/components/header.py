"""Header component with app branding."""

from nicegui import ui


def create_header() -> None:
    """Create the application header."""
    with ui.header().classes("bg-gradient-to-r from-purple-600 to-pink-500"):
        with ui.row().classes("w-full items-center justify-between px-4"):
            # Left spacer for balance
            ui.element("div").classes("w-24")

            # Center: Logo and title
            with ui.row().classes("items-center gap-2"):
                ui.icon("videocam").classes("text-3xl text-white")
                ui.label("INSTAGRAM REEL TRACKER").classes(
                    "text-2xl font-bold text-white tracking-wide"
                )
                ui.icon("receipt_long").classes("text-3xl text-white")

            # Right: Admin link
            with ui.row().classes("w-24 justify-end"):
                ui.link("Admin", "/admin").classes(
                    "text-white hover:text-gray-200 flex items-center gap-1"
                ).style("text-decoration: none")
                ui.icon("settings").classes("text-white text-xl")
