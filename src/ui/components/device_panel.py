"""Device connection panel component."""

from nicegui import ui

from src.capture.base import DeviceType
from src.ui.state import app_state


def create_device_panel() -> ui.card:
    """Create the device connection panel.

    Returns:
        The device panel card element.
    """
    with ui.card().classes("w-full") as card:
        ui.label("DEVICES").classes("text-lg font-bold text-gray-700 mb-2")

        device_container = ui.column().classes("w-full gap-2")

        def update_device_display():
            device_container.clear()
            with device_container:
                device = app_state.connected_device
                if device:
                    # Show connected device
                    with ui.row().classes("items-center gap-2 p-2 bg-green-50 rounded"):
                        if device.device_type == DeviceType.IOS:
                            ui.icon("phone_iphone").classes("text-2xl text-green-600")
                        else:
                            ui.icon("devices").classes("text-2xl text-green-600")

                        with ui.column().classes("gap-0"):
                            ui.label(device.device_name).classes("font-medium")
                            model_str = f"via {device.model}" if device.model else "iPhone Mirror"
                            ui.label(model_str).classes("text-sm text-gray-500")

                        # Show connection type badge
                        with ui.column().classes("ml-auto items-end gap-1"):
                            ui.icon("check_circle").classes("text-green-600")
                            with ui.row().classes("items-center gap-1"):
                                ui.icon("cast").classes("text-xs text-purple-600")
                                ui.label("Screen Mirror").classes("text-xs text-purple-600")
                else:
                    # Show no device connected
                    with ui.row().classes("items-center gap-2 p-2 bg-gray-50 rounded"):
                        ui.icon("phone_disabled").classes("text-2xl text-gray-400")
                        with ui.column().classes("gap-0"):
                            ui.label("No iPhone connected").classes(
                                "font-medium text-gray-500"
                            )
                            ui.label("Start iPhone Mirroring or uxplay").classes("text-sm text-gray-400")

        # Initial render
        update_device_display()

        # Register for state updates
        app_state.add_update_callback(update_device_display)

    return card
