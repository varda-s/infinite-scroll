"""Live receipt viewer component."""

from nicegui import ui

from src.ui.database.repository import SessionRepository
from src.ui.services.media_paths import to_media_url
from src.ui.services.replay_service import ensure_session_replay_video
from src.ui.state import app_state


def create_receipt_viewer() -> ui.card:
    """Create the live receipt viewer panel."""
    with ui.card().classes("w-full h-full") as card:
        ui.label("LIVE RECEIPT").classes("text-lg font-bold text-gray-700 mb-2")

        with ui.row().classes("w-full justify-between px-1"):
            current_reel_label = ui.label("Current Reel: #1").classes("text-sm font-medium")
            timer_label = ui.label("Timer: 0.0s").classes("text-sm text-blue-600")

        active_mock_container = ui.column().classes("w-full")
        with active_mock_container:
            with ui.scroll_area().classes("w-full h-64 bg-gray-50 rounded border") as receipt_scroll:
                receipt_list = ui.column().classes("w-full p-2 gap-2")

        active_printer_container = ui.column().classes("w-full items-center justify-center h-64 bg-gray-100 rounded")
        with active_printer_container:
            ui.icon("print").classes("text-4xl text-gray-400")
            ui.label("Printing to thermal printer").classes("text-gray-500")
            ui.label("Receipt preview not available").classes("text-sm text-gray-400")

        inactive_container = ui.column().classes("w-full items-center justify-center h-64 bg-gray-100 rounded")
        with inactive_container:
            ui.icon("receipt_long").classes("text-4xl text-gray-300")
            ui.label("No active session").classes("text-gray-400")

        rendered_reel_count = 0
        last_key: tuple | None = None

        def render_reel_card(reel_number: int, duration_seconds: float, screenshot_path: str | None) -> None:
            screenshot_url = to_media_url(screenshot_path)
            with receipt_list:
                with ui.card().classes("w-full p-2"):
                    with ui.row().classes("items-start gap-3"):
                        if screenshot_url:
                            ui.image(screenshot_url).classes("w-24 h-40 rounded object-cover")
                        else:
                            with ui.column().classes("w-24 h-40 items-center justify-center bg-gray-200 rounded"):
                                ui.icon("image_not_supported").classes("text-gray-400")
                        with ui.column().classes("gap-1"):
                            ui.label(f"Reel #{reel_number}").classes("font-semibold")
                            ui.label(f"Time spent: {duration_seconds:.1f}s").classes("text-sm text-gray-600")

        def update_receipt() -> None:
            nonlocal rendered_reel_count, last_key

            state_key = (
                app_state.session_active,
                app_state.printer_type,
                app_state.current_reel_number,
                round(app_state.current_reel_duration, 2),
                len(app_state.live_reel_receipts),
            )
            if state_key == last_key:
                return
            last_key = state_key

            is_active = app_state.session_active
            is_mock = app_state.printer_type == "mock"
            active_mock_container.set_visibility(is_active and is_mock)
            active_printer_container.set_visibility(is_active and not is_mock)
            inactive_container.set_visibility(not is_active)

            if not is_active:
                rendered_reel_count = 0
                receipt_list.clear()
                return

            current_reel_label.text = f"Current Reel: #{max(1, app_state.current_reel_number)}"
            timer_label.text = f"Timer: {app_state.current_reel_duration:.1f}s"

            if not is_mock:
                return

            # Append only newly completed reels; no full rerender loop.
            reels = app_state.live_reel_receipts
            if len(reels) < rendered_reel_count:
                rendered_reel_count = 0
                receipt_list.clear()
            for reel in reels[rendered_reel_count:]:
                render_reel_card(reel.reel_number, reel.duration_seconds, reel.screenshot_path)
            rendered_reel_count = len(reels)

            # Keep view focused on newest cards.
            try:
                receipt_scroll.scroll_to(percent=1.0)
            except Exception:
                pass

        update_receipt()
        ui.timer(0.05, update_receipt)

    return card


def show_receipt_modal(receipt_content: str, session_info: str = "") -> None:
    """Show a modal with full receipt content."""
    with ui.dialog() as dialog, ui.card().classes("w-full max-w-2xl"):
        with ui.row().classes("w-full items-center justify-between mb-4"):
            ui.label(f"Receipt{f' - {session_info}' if session_info else ''}").classes("text-xl font-bold")
            ui.button(icon="close", on_click=dialog.close).props("flat round")

        with ui.scroll_area().classes("w-full h-96 bg-gray-50 rounded border"):
            with ui.column().classes("w-full p-4 gap-1"):
                for line in receipt_content.split("\n"):
                    ui.label(line).classes("font-mono text-sm text-gray-800 whitespace-pre")

        with ui.row().classes("w-full justify-end mt-4"):
            ui.button("Close", on_click=dialog.close)

    dialog.open()


def show_session_detail_modal(session_id: int, session_info: str = "") -> None:
    """Show session details including replay video and receipt text."""
    session = SessionRepository.get_session(session_id)
    if session is None:
        ui.notify("Session not found", type="warning")
        return

    replay_path = ensure_session_replay_video(session_id)
    replay_url = to_media_url(replay_path)

    with ui.dialog() as dialog, ui.card().classes("w-full max-w-4xl"):
        with ui.row().classes("w-full items-center justify-between mb-4"):
            ui.label(f"Session Details{f' - {session_info}' if session_info else ''}").classes("text-xl font-bold")
            ui.button(icon="close", on_click=dialog.close).props("flat round")

        if replay_url:
            ui.label("Replay").classes("font-semibold text-gray-700")
            ui.video(replay_url).props("controls").classes("w-full max-h-80 rounded border")

        if session.receipt_content:
            ui.label("Receipt Text").classes("font-semibold text-gray-700 mt-2")
            with ui.scroll_area().classes("w-full h-48 bg-gray-50 rounded border"):
                with ui.column().classes("w-full p-3 gap-1"):
                    for line in session.receipt_content.split("\n"):
                        ui.label(line).classes("font-mono text-xs text-gray-800 whitespace-pre")

        with ui.row().classes("w-full justify-end mt-4"):
            ui.button("Close", on_click=dialog.close)

    dialog.open()
