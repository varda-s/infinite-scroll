"""Single-page kiosk UI matching the updated booth design."""

from collections.abc import Callable
from pathlib import Path

from PIL import Image
from nicegui import ui

from src.ui.components.printer_panel import check_rongta_connected
from src.ui.services.device_service import device_service
from src.ui.state import app_state


def create_session_page(
    on_start_session: Callable[[], None],
    on_stop_session: Callable[[], None],
) -> None:
    """Render the simplified one-page session UI."""
    # Homepage kiosk flow always uses the physical Rongta printer.
    if not app_state.session_active and app_state.printer_type != "rongta":
        app_state.set_printer_type("rongta")

    hero_image_file = Path(__file__).resolve().parent.parent / "assets" / "images" / "thank-you-for-your-time.png"
    hero_image_url = "/assets/images/thank-you-for-your-time.png"
    page_bg = _get_image_corner_bg(hero_image_file)

    style_template = """
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;600;700;800&display=swap');

            body {
                background: __PAGE_BG__;
                font-family: 'Manrope', sans-serif;
                color: #171717;
            }

            .kiosk-shell {
                min-height: 100vh;
                background: __PAGE_BG__;
            }

            .kiosk-main {
                width: 100%;
                max-width: 1380px;
                margin: 0 auto;
                padding: 2.25rem 2rem 2.75rem;
                display: grid;
                gap: 2rem;
                align-items: start;
                grid-template-columns: 1fr;
            }

            @media (min-width: 1200px) {
                .kiosk-main {
                    grid-template-columns: minmax(0, 1.6fr) minmax(360px, 1fr);
                }
            }

            .hero-image {
                width: min(100%, 880px);
                display: block;
            }

            .readiness-card {
                background: #2c2c2c;
                color: #f4f4f4;
                border-radius: 12px;
                box-shadow: 0 20px 40px rgba(0, 0, 0, 0.2);
            }

            .devices-card {
                border: 1px solid #d8d8d8;
                box-shadow: 0 8px 20px rgba(17, 17, 17, 0.07);
            }

            .setup-copy {
                font-size: clamp(1rem, 1.2vw, 1.12rem);
                line-height: 1.4;
            }
        </style>
    """
    ui.add_head_html(style_template.replace("__PAGE_BG__", page_bg))

    with ui.column().classes("kiosk-shell w-full"):
        with ui.element("section").classes("kiosk-main"):
            with ui.column().classes("w-full gap-8 min-w-0"):
                if hero_image_file.exists():
                    ui.image(hero_image_url).classes("hero-image")
                else:
                    ui.label("Hero image missing: add /src/ui/assets/images/thank-you-for-your-time.png").classes(
                        "text-red-700 font-semibold"
                    )

                with ui.row().classes("w-full gap-6 items-start flex-wrap"):
                    with ui.column().classes("flex-1 min-w-64 max-w-lg gap-3"):
                        ui.label("To participate in this experience, you will need an iPhone and Instagram.").classes(
                            "setup-copy text-zinc-900"
                        )
                        ui.label("SETUP INSTRUCTIONS").classes("text-2xl font-semibold tracking-wide")
                        ui.label(
                            "1. Connect your phone to tiat-guest (password: artandtechnology).\n"
                            "2. Turn on Bluetooth. Open your iPhone's Control Center and tap Screen Mirroring.\n"
                            "3. Select \"ReelTracker\" and enter the PIN shown on screen.\n"
                            "4. Your phone screen should now be mirrored on the laptop."
                        ).classes("whitespace-pre-wrap setup-copy text-zinc-800")

                    with ui.card().classes("devices-card w-full max-w-sm bg-white rounded-xl p-5 gap-3"):
                        ui.label("DEVICES").classes("text-xl font-extrabold text-zinc-700 tracking-wide")
                        connection_label = ui.label("").classes("font-semibold")
                        detail_label = ui.label("").classes("text-sm text-zinc-500")
                        pairing_label = ui.label("").classes("text-base font-bold text-blue-600")
                        limit_label = ui.label("Only one mirrored device is supported at a time").classes(
                            "text-xs text-zinc-400"
                        )
                        reset_button = ui.button(
                            "Reset Pairing",
                            on_click=lambda: _on_reset_pairing(),
                        ).classes("w-full mt-2 text-lg font-semibold bg-fuchsia-500 text-white")

                        def update_device_display() -> None:
                            device = app_state.connected_device
                            if device:
                                connection_label.text = f"{device.device_name} connected"
                                detail_label.text = (
                                    f"Mirror source: {device.model}" if device.model else "Mirror source: Screen Mirroring"
                                )
                                pairing_label.set_visibility(False)
                            else:
                                connection_label.text = "No ReelTracker mirror connected"
                                detail_label.text = "Connect to ReelTracker via iPhone Screen Mirroring"
                                if app_state.uxplay_pairing_code:
                                    pairing_label.text = f"Pairing PIN: {app_state.uxplay_pairing_code}"
                                    pairing_label.set_visibility(True)
                                else:
                                    pairing_label.text = "Waiting for pairing PIN..."
                                    pairing_label.set_visibility(True)

                            if app_state.session_active:
                                reset_button.disable()
                                limit_label.text = "Pairing reset is disabled during an active session"
                            else:
                                reset_button.enable()
                                limit_label.text = "Only one mirrored device is supported at a time"

                        update_device_display()
                        ui.timer(0.4, update_device_display)

            with ui.card().classes("readiness-card w-full p-7 md:p-10 gap-6"):
                with ui.row().classes(
                    "w-full items-start gap-3 rounded-lg border border-red-300 bg-red-50 px-4 py-3 text-red-800"
                ) as printer_issue_banner:
                    ui.icon("warning_amber").classes("text-2xl")
                    with ui.column().classes("gap-1"):
                        ui.label("Printer connection issue").classes("text-lg font-bold")
                        printer_issue_text = ui.label(
                            "Rongta printer not detected. Connect it before starting the session."
                        ).classes("text-sm leading-snug")

                ui.label("Ready to start scrolling?").classes("text-4xl font-extrabold")
                ui.label(
                    "1. Take a seat.\n\n"
                    "2. Once your phone is connected and your screen is mirrored on the laptop, open Instagram.\n\n"
                    "3. Click on the Reels tab and select a reel to begin.\n\n"
                    "4. Press Start Session, and then scroll as you normally would.\n\n"
                    "5. Click Stop Session when you're done."
                ).classes("text-2xl whitespace-pre-wrap leading-relaxed")

                session_hint = ui.label("").classes("text-base text-zinc-300")
                session_button = ui.button(
                    "Start Session",
                    on_click=lambda: _on_session_toggle(on_start_session, on_stop_session),
                ).classes("w-full text-2xl font-bold py-3")

                def update_session_button() -> None:
                    has_device = app_state.connected_device is not None
                    if app_state.session_active:
                        session_button.text = "Stop Session"
                        session_button.props(remove="color=positive", add="color=negative")
                        session_hint.text = "Session is active. Stop when participant is done."
                    else:
                        session_button.text = "Start Session"
                        session_button.props(remove="color=negative", add="color=positive")
                        if has_device:
                            session_hint.text = "Mirror connected. Start when participant opens Reels."
                        elif app_state.uxplay_pairing_code:
                            session_hint.text = (
                                f"Waiting for mirror connection. Pair with PIN {app_state.uxplay_pairing_code}."
                            )
                        else:
                            session_hint.text = "Starting pairing service..."

                last_printer_connected: bool | None = None

                def update_printer_banner() -> None:
                    nonlocal last_printer_connected
                    connected = check_rongta_connected()
                    if connected != last_printer_connected:
                        app_state.set_printer_connected(connected)
                        last_printer_connected = connected
                    printer_issue_banner.set_visibility(not connected)
                    if connected:
                        return
                    if app_state.session_active:
                        printer_issue_text.text = (
                            "Rongta printer appears disconnected. Session can continue, "
                            "but printing may fail."
                        )
                    else:
                        printer_issue_text.text = (
                            "Rongta printer not detected. Connect it before starting the session."
                        )

                update_printer_banner()
                update_session_button()
                ui.timer(1.0, update_printer_banner)
                ui.timer(0.3, update_session_button)


def _on_session_toggle(
    on_start_session: Callable[[], None],
    on_stop_session: Callable[[], None],
) -> None:
    """Toggle session state with a single primary button."""
    if app_state.session_active:
        on_stop_session()
    else:
        # Ensure homepage starts always target Rongta.
        app_state.set_printer_type("rongta")
        on_start_session()


def _on_reset_pairing() -> None:
    """Reset pairing pin for the next participant."""
    app_state.set_device(None)
    if device_service.prime_next_user_pairing():
        ui.notify("Pairing reset. Use the new PIN to connect.", type="info")
    else:
        ui.notify("Failed to reset pairing.", type="negative")


def _get_image_corner_bg(image_file: Path) -> str:
    """Use average corner color so page background matches hero asset."""
    default_color = "#e8e8e8"
    if not image_file.exists():
        return default_color
    try:
        image = Image.open(image_file).convert("RGB")
        pixels = [
            image.getpixel((0, 0)),
            image.getpixel((image.width - 1, 0)),
            image.getpixel((0, image.height - 1)),
            image.getpixel((image.width - 1, image.height - 1)),
        ]
        r = sum(px[0] for px in pixels) // 4
        g = sum(px[1] for px in pixels) // 4
        b = sum(px[2] for px in pixels) // 4
        return f"rgb({r}, {g}, {b})"
    except Exception:
        return default_color
