"""Live receipt viewer component."""

from nicegui import ui

from src.ui.state import app_state


def create_receipt_viewer() -> ui.card:
    """Create the live receipt viewer panel.

    Returns:
        The receipt viewer card element.
    """
    with ui.card().classes("w-full h-full") as card:
        ui.label("LIVE RECEIPT").classes("text-lg font-bold text-gray-700 mb-2")

        # Receipt display area with monospace font
        receipt_container = ui.column().classes("w-full")

        def update_receipt():
            receipt_container.clear()
            with receipt_container:
                if app_state.session_active and app_state.printer_type == "mock":
                    if app_state.live_receipt_lines:
                        # Create scrollable receipt area
                        with ui.scroll_area().classes("w-full h-64 bg-gray-900 rounded"):
                            with ui.column().classes("w-full p-2"):
                                for line in app_state.live_receipt_lines[-50:]:  # Last 50 lines
                                    ui.label(line).classes(
                                        "font-mono text-xs text-green-400 whitespace-pre"
                                    )
                    else:
                        with ui.column().classes("items-center justify-center h-64 bg-gray-100 rounded"):
                            ui.icon("receipt").classes("text-4xl text-gray-300")
                            ui.label("Waiting for reels...").classes("text-gray-400")

                elif app_state.session_active and app_state.printer_type != "mock":
                    with ui.column().classes("items-center justify-center h-64 bg-gray-100 rounded"):
                        ui.icon("print").classes("text-4xl text-gray-400")
                        ui.label("Printing to thermal printer").classes("text-gray-500")
                        ui.label("Receipt preview not available").classes(
                            "text-sm text-gray-400"
                        )

                else:
                    with ui.column().classes("items-center justify-center h-64 bg-gray-100 rounded"):
                        ui.icon("receipt_long").classes("text-4xl text-gray-300")
                        ui.label("No active session").classes("text-gray-400")

        # Initial render
        update_receipt()

        # Register for state updates
        app_state.add_update_callback(update_receipt)

    return card


def show_receipt_modal(receipt_content: str, session_info: str = "") -> None:
    """Show a modal with full receipt content.

    Args:
        receipt_content: The full receipt text.
        session_info: Optional session info for the title.
    """
    with ui.dialog() as dialog, ui.card().classes("w-full max-w-2xl"):
        with ui.row().classes("w-full items-center justify-between mb-4"):
            ui.label(f"Receipt{f' - {session_info}' if session_info else ''}").classes(
                "text-xl font-bold"
            )
            ui.button(icon="close", on_click=dialog.close).props("flat round")

        with ui.scroll_area().classes("w-full h-96 bg-gray-900 rounded"):
            with ui.column().classes("w-full p-4"):
                for line in receipt_content.split("\n"):
                    ui.label(line).classes("font-mono text-sm text-green-400 whitespace-pre")

        with ui.row().classes("w-full justify-end mt-4"):
            ui.button("Close", on_click=dialog.close)

    dialog.open()
