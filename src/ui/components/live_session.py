"""Live session display component."""

from nicegui import ui

from src.printing.base import BasePrinter
from src.ui.state import app_state


def create_live_session() -> ui.card:
    """Create the live session display panel."""
    with ui.card().classes("w-full h-full") as card:
        ui.label("LIVE SESSION").classes("text-lg font-bold text-gray-700 mb-2")

        with ui.column().classes("w-full gap-3"):
            active_block = ui.column().classes("w-full gap-3")
            with active_block:
                with ui.row().classes("items-center gap-2"):
                    ui.icon("fiber_manual_record").classes("text-red-500 animate-pulse")
                    ui.label("Recording").classes("text-red-500 font-medium")

                ui.separator()

                with ui.row().classes("w-full justify-between"):
                    with ui.column().classes("items-center"):
                        ui.label("Current Reel").classes("text-sm text-gray-500")
                        current_reel_label = ui.label("#1").classes("text-2xl font-bold")

                    with ui.column().classes("items-center"):
                        ui.label("Duration").classes("text-sm text-gray-500")
                        current_duration_label = ui.label("0:00").classes("text-2xl font-bold")

                ui.separator()

                with ui.row().classes("w-full justify-between"):
                    with ui.column().classes("items-center"):
                        ui.label("Total Reels").classes("text-sm text-gray-500")
                        total_reels_label = ui.label("0").classes("text-xl font-medium")

                    with ui.column().classes("items-center"):
                        ui.label("Total Time").classes("text-sm text-gray-500")
                        total_time_label = ui.label("0:00").classes("text-xl font-medium")

            inactive_block = ui.column().classes("w-full items-center justify-center py-8")
            with inactive_block:
                ui.icon("pause_circle").classes("text-6xl text-gray-300")
                ui.label("No Active Session").classes("text-xl text-gray-400 mt-2")
                ui.label("Start a session to begin tracking").classes("text-sm text-gray-400")

        last_key: tuple | None = None

        def update_display() -> None:
            nonlocal last_key
            state_key = (
                app_state.session_active,
                app_state.current_reel_number,
                round(app_state.current_reel_duration, 2),
                app_state.total_reels,
                round(app_state.total_time_seconds, 2),
            )
            if state_key == last_key:
                return
            last_key = state_key

            is_active = app_state.session_active
            active_block.set_visibility(is_active)
            inactive_block.set_visibility(not is_active)
            if not is_active:
                return

            current_reel_label.text = f"#{max(1, app_state.current_reel_number)}"
            current_duration_label.text = BasePrinter.format_duration(app_state.current_reel_duration)
            total_reels_label.text = str(app_state.total_reels)
            total_time_label.text = BasePrinter.format_duration(app_state.total_time_seconds)

        update_display()
        ui.timer(0.05, update_display)

    return card
