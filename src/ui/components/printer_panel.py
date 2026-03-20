"""Printer selection panel component."""

from nicegui import ui

from src.ui.state import app_state


def check_rongta_connected() -> bool:
    """Check if a Rongta printer is connected via USB.

    Returns:
        True if a Rongta printer is detected.
    """
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

    # Fast path: USB device scan.
    try:
        import usb.core

        for vendor_id, product_id in known_usb_ids:
            device = usb.core.find(idVendor=vendor_id, idProduct=product_id)
            if device is not None:
                return True
    except Exception:
        pass

    # Fallback path: attempt actual ESC/POS USB open (closer to print reality).
    try:
        from escpos.printer import Usb

        for vendor_id, product_id in known_usb_ids:
            printer = None
            try:
                printer = Usb(vendor_id, product_id)
                return True
            except Exception:
                continue
            finally:
                try:
                    if printer is not None:
                        printer.close()
                except Exception:
                    pass
    except Exception:
        pass

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
        app_state.set_printer_connected(rongta_available)

        with ui.row().classes("items-center gap-2 mb-1"):
            printer_status_icon = ui.icon("circle")
            printer_status_label = ui.label("")

            def update_printer_status() -> None:
                connected = check_rongta_connected()
                app_state.set_printer_connected(connected)
                if connected:
                    printer_status_icon.props("color=positive")
                    printer_status_label.text = "Rongta: Connected"
                    printer_status_label.classes(remove="text-red-600", add="text-green-700")
                else:
                    printer_status_icon.props("color=negative")
                    printer_status_label.text = "Rongta: Not detected"
                    printer_status_label.classes(remove="text-green-700", add="text-red-600")

            update_printer_status()
            ui.timer(1.0, update_printer_status)

        # Printer type selection (single radio group for mutual exclusivity)
        with ui.column().classes("w-full gap-2"):
            # Keep both options visible; USB probing can be flaky.
            printer_options = {
                "mock": "Mock (Console)",
                "rongta": "Rongta (Thermal)",
            }

            selected_printer = app_state.printer_type
            if selected_printer not in printer_options:
                selected_printer = "mock"
                app_state.set_printer_type("mock")

            printer_radio = ui.radio(
                options=printer_options,
                value=selected_printer,
            ).classes("w-full")

            if not rongta_available:
                with ui.row().classes("items-center gap-2 text-gray-400 text-sm"):
                    ui.icon("usb_off").classes("text-gray-400")
                    ui.label("Rongta USB not detected. Start will fail if printer is unavailable.")

        def on_printer_change(e):
            if app_state.session_active:
                printer_radio.value = app_state.printer_type
                return

            selected = getattr(e, "value", None)
            if not isinstance(selected, str):
                args = getattr(e, "args", None)
                if isinstance(args, str):
                    selected = args
                elif isinstance(args, dict):
                    for key in ("value", "model-value", "modelValue"):
                        value = args.get(key)
                        if isinstance(value, str):
                            selected = value
                            break

            if selected in {"mock", "rongta"}:
                app_state.set_printer_type(selected)

        printer_radio.on("update:model-value", on_printer_change)

        def on_start_click() -> None:
            # Force-sync selected UI value before starting session.
            selected = printer_radio.value
            if selected in {"mock", "rongta"}:
                app_state.set_printer_type(selected)
            on_start_session()

        ui.separator().classes("my-3")

        # Session control buttons (stable elements to avoid listener churn warnings)
        with ui.column().classes("w-full gap-2"):
            start_btn = ui.button(
                "Start Session",
                icon="play_arrow",
                on_click=on_start_click,
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
                printer_radio.disable()
            else:
                stop_btn.set_visibility(False)
                start_btn.set_visibility(True)
                # Keep Start enabled so booth operators can click once and let
                # tracking service wait for/attach to the ReelTracker mirror.
                start_btn.enable()
                start_btn.props("color=positive" if has_device else "color=primary")
                printer_radio.enable()

        update_buttons()
        ui.timer(0.1, update_buttons)

    return card
