"""Live session display component."""

from nicegui import ui

from src.printing.base import BasePrinter
from src.ui.state import app_state


def create_live_session() -> ui.card:
    """Create the live session display panel.

    Returns:
        The live session card element.
    """
    with ui.card().classes("w-full h-full") as card:
        ui.label("LIVE SESSION").classes("text-lg font-bold text-gray-700 mb-2")

        status_container = ui.column().classes("w-full gap-3")

        def update_display():
            status_container.clear()
            with status_container:
                if app_state.session_active:
                    # Status indicator
                    with ui.row().classes("items-center gap-2"):
                        ui.icon("fiber_manual_record").classes("text-red-500 animate-pulse")
                        ui.label("Recording").classes("text-red-500 font-medium")

                    ui.separator()

                    # Current reel stats
                    with ui.row().classes("w-full justify-between"):
                        with ui.column().classes("items-center"):
                            ui.label("Current Reel").classes("text-sm text-gray-500")
                            ui.label(f"#{app_state.current_reel_number}").classes(
                                "text-2xl font-bold"
                            )

                        with ui.column().classes("items-center"):
                            ui.label("Duration").classes("text-sm text-gray-500")
                            duration_str = BasePrinter.format_duration(
                                app_state.current_reel_duration
                            )
                            ui.label(duration_str).classes("text-2xl font-bold")

                    ui.separator()

                    # Session totals
                    with ui.row().classes("w-full justify-between"):
                        with ui.column().classes("items-center"):
                            ui.label("Total Reels").classes("text-sm text-gray-500")
                            ui.label(str(app_state.total_reels)).classes("text-xl font-medium")

                        with ui.column().classes("items-center"):
                            ui.label("Total Time").classes("text-sm text-gray-500")
                            total_str = BasePrinter.format_duration(app_state.total_time_seconds)
                            ui.label(total_str).classes("text-xl font-medium")

                else:
                    # No active session
                    with ui.column().classes("items-center justify-center py-8"):
                        ui.icon("pause_circle").classes("text-6xl text-gray-300")
                        ui.label("No Active Session").classes("text-xl text-gray-400 mt-2")
                        ui.label("Start a session to begin tracking").classes(
                            "text-sm text-gray-400"
                        )

        # Initial render
        update_display()

        # Register for state updates
        app_state.add_update_callback(update_display)

    return card
