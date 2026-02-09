"""Device connection panel component."""

from nicegui import ui

from src.capture.base import DeviceType
from src.ui.services.device_service import device_service
from src.ui.state import app_state


def create_device_panel() -> ui.card:
    """Create the device connection panel.

    Returns:
        The device panel card element.
    """
    with ui.card().classes("w-full") as card:
        ui.label("DEVICES").classes("text-lg font-bold text-gray-700 mb-2")

        device_container = ui.column().classes("w-full gap-2")
        last_key: tuple | None = None

        def update_device_display() -> None:
            nonlocal last_key
            device = app_state.connected_device
            state_key = (
                device.device_id if device else None,
                device.device_name if device else None,
                device.model if device else None,
                app_state.uxplay_pairing_code if device is None else None,
            )
            if state_key == last_key:
                return
            last_key = state_key

            device_container.clear()
            with device_container:
                if device:
                    with ui.row().classes("items-center gap-2 p-2 bg-green-50 rounded"):
                        if device.device_type == DeviceType.IOS:
                            ui.icon("phone_iphone").classes("text-2xl text-green-600")
                        else:
                            ui.icon("devices").classes("text-2xl text-green-600")

                        with ui.column().classes("gap-0"):
                            ui.label(device.device_name).classes("font-medium")
                            model_str = f"via {device.model}" if device.model else "Screen Mirror"
                            ui.label(model_str).classes("text-sm text-gray-500")

                        with ui.column().classes("ml-auto items-end gap-1"):
                            ui.icon("check_circle").classes("text-green-600")
                            ui.label("Device Paired").classes("text-xs text-green-700 font-medium")
                else:
                    with ui.row().classes("items-center gap-2 p-2 bg-gray-50 rounded"):
                        ui.icon("phone_disabled").classes("text-2xl text-gray-400")
                        with ui.column().classes("gap-0"):
                            ui.label("No ReelTracker mirror connected").classes(
                                "font-medium text-gray-500"
                            )
                            ui.label("Connect to ReelTracker via iPhone Screen Mirroring").classes(
                                "text-sm text-gray-400"
                            )
                            if app_state.uxplay_pairing_code:
                                ui.label(f"Pairing PIN: {app_state.uxplay_pairing_code}").classes(
                                    "text-sm text-blue-600 font-medium"
                                )
                            ui.label("Only one mirrored device is supported at a time").classes(
                                "text-xs text-gray-400"
                            )

                if not app_state.session_active:
                    def _reset_pairing() -> None:
                        app_state.set_device(None)
                        if device_service.prime_next_user_pairing():
                            ui.notify("Pairing reset. Use the new PIN to connect.", type="info")
                        else:
                            ui.notify("Failed to reset pairing.", type="negative")

                    ui.button(
                        "Reset Pairing",
                        icon="sync",
                        on_click=_reset_pairing,
                    ).classes("w-full mt-1")

        update_device_display()
        ui.timer(0.5, update_device_display)

    return card
