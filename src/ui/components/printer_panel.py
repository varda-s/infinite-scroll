"""Printer selection panel component."""

from nicegui import ui

from src.ui.state import app_state


def check_rongta_connected() -> bool:
    """Check if a Rongta printer is connected via USB.

    Returns:
        True if a Rongta printer is detected.
    """
    try:
        import usb.core

        # Known tested/compatible ESC-POS USB ID pairs.
        known_usb_ids = [
            (0x0FE6, 0x811E),  # Legacy tested booth printer
            (0x0483, 0x5743),  # RP58
            (0x0483, 0x5740),  # RP80
            (0x0483, 0x5720),  # Generic
            (0x6868, 0x0500),  # ACE V1
            (0x6868, 0x0200),  # Alternative
            (0x0416, 0x5011),  # Some Rongta models
            (0x0483, 0x070B),  # RP328
        ]

        for vendor_id, product_id in known_usb_ids:
            device = usb.core.find(idVendor=vendor_id, idProduct=product_id)
            if device is not None:
                return True
        return False
    except ImportError:
        # pyusb not installed
        return False
    except Exception:
        return False


def create_printer_panel(
    on_start_session: callable,
    on_stop_session: callable,
) -> ui.card:
    """Create the printer selection panel.

    Args:
        on_start_session: Callback when start session is clicked.
        on_stop_session: Callback when stop session is clicked.

    Returns:
        The printer panel card element.
    """
    with ui.card().classes("w-full") as card:
        ui.label("PRINTER").classes("text-lg font-bold text-gray-700 mb-2")

        # Check if Rongta is connected
        rongta_available = check_rongta_connected()

        # Printer type selection
        with ui.column().classes("w-full gap-2"):
            # Mock option (always available)
            mock_radio = ui.radio(
                options={"mock": "Mock (Console)"},
                value="mock" if app_state.printer_type == "mock" else None,
            ).classes("w-full")

            # Rongta option (only if connected)
            with ui.row().classes("w-full items-center"):
                if rongta_available:
                    rongta_radio = ui.radio(
                        options={"rongta": "Rongta (Thermal)"},
                        value="rongta" if app_state.printer_type == "rongta" else None,
                    ).classes("flex-1")
                else:
                    with ui.row().classes("items-center gap-2 text-gray-400"):
                        ui.radio(
                            options={"rongta": "Rongta (Thermal)"},
                            value=None,
                        ).classes("flex-1").props("disable")
                        ui.icon("usb_off").classes("text-gray-400")
                    ui.tooltip("Connect printer via USB first")

        def on_mock_change(e):
            if app_state.session_active:
                mock_radio.value = "mock" if app_state.printer_type == "mock" else None
                return
            if e.args:
                app_state.set_printer_type("mock")
                if rongta_available:
                    rongta_radio.value = None

        def on_rongta_change(e):
            if app_state.session_active:
                if rongta_available:
                    rongta_radio.value = "rongta" if app_state.printer_type == "rongta" else None
                return
            if e.args and rongta_available:
                app_state.set_printer_type("rongta")
                mock_radio.value = None

        mock_radio.on("update:model-value", on_mock_change)
        if rongta_available:
            rongta_radio.on("update:model-value", on_rongta_change)

        ui.separator().classes("my-3")

        # Session control buttons (stable elements to avoid listener churn warnings)
        with ui.column().classes("w-full gap-2"):
            start_btn = ui.button(
                "Start Session",
                icon="play_arrow",
                on_click=on_start_session,
            ).classes("w-full")
            stop_btn = ui.button(
                "Stop Session",
                icon="stop",
                on_click=on_stop_session,
            ).classes("w-full bg-red-500").props("color=negative")

        last_state: tuple[bool, bool] | None = None

        def update_buttons() -> None:
            nonlocal last_state
            has_device = app_state.connected_device is not None
            current_state = (app_state.session_active, has_device)
            if current_state == last_state:
                return
            last_state = current_state

            if app_state.session_active:
                start_btn.set_visibility(False)
                stop_btn.set_visibility(True)
                mock_radio.disable()
                if rongta_available:
                    rongta_radio.disable()
            else:
                stop_btn.set_visibility(False)
                start_btn.set_visibility(True)
                # Keep Start enabled so booth operators can click once and let
                # tracking service wait for/attach to the ReelTracker mirror.
                start_btn.enable()
                start_btn.props("color=positive" if has_device else "color=primary")
                mock_radio.enable()
                if rongta_available:
                    rongta_radio.enable()

        update_buttons()
        ui.timer(0.1, update_buttons)

    return card
