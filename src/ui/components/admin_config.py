"""Admin configuration page component."""

from nicegui import ui

from src.ui.database.repository import ConfigRepository
from src.ui.components.sidebar import create_sidebar, create_header_with_menu


def create_config_card(category: str, title: str, icon: str) -> ui.card:
    """Create a configuration card for a category.

    Args:
        category: The config category to display.
        title: Card title.
        icon: Material icon name.

    Returns:
        The card element.
    """
    with ui.card().classes("w-full") as card:
        with ui.row().classes("items-center gap-2 mb-4"):
            ui.icon(icon).classes("text-2xl text-gray-600")
            ui.label(title).classes("text-lg font-bold text-gray-700")

        configs = ConfigRepository.get_by_category(category)

        for config in configs:
            with ui.column().classes("w-full mb-4 p-3 bg-gray-50 rounded"):
                with ui.row().classes("w-full items-center justify-between"):
                    with ui.column().classes("flex-1"):
                        ui.label(config.key.replace("_", " ").title()).classes(
                            "font-medium"
                        )
                        ui.label(config.description).classes("text-sm text-gray-500")

                    with ui.column().classes("w-48"):
                        if config.value_type == "bool":
                            switch = ui.switch(value=config.value.lower() == "true")

                            def make_bool_handler(key: str):
                                def handler(e):
                                    val = e.args if isinstance(e.args, bool) else e.args
                                    ConfigRepository.set(key, str(val).lower())
                                    ui.notify(f"Updated {key}", type="positive")
                                return handler

                            switch.on("update:model-value", make_bool_handler(config.key))
                        elif config.value_type == "int":
                            number_input = ui.number(
                                value=int(config.value),
                                step=1,
                            ).classes("w-full")

                            def make_int_handler(key: str):
                                def handler(e):
                                    val = e.args if e.args is not None else 0
                                    ConfigRepository.set(key, str(int(val)))
                                    ui.notify(f"Updated {key}", type="positive")
                                return handler

                            number_input.on("update:model-value", make_int_handler(config.key))
                        elif config.value_type == "float":
                            number_input = ui.number(
                                value=float(config.value),
                                step=0.1,
                                format="%.1f",
                            ).classes("w-full")

                            def make_float_handler(key: str):
                                def handler(e):
                                    val = e.args if e.args is not None else 0.0
                                    ConfigRepository.set(key, str(float(val)))
                                    ui.notify(f"Updated {key}", type="positive")
                                return handler

                            number_input.on("update:model-value", make_float_handler(config.key))
                        else:
                            text_input = ui.input(value=config.value).classes("w-full")

                            def make_str_handler(key: str):
                                def handler(e):
                                    val = e.args if e.args is not None else ""
                                    ConfigRepository.set(key, str(val))
                                    ui.notify(f"Updated {key}", type="positive")
                                return handler

                            text_input.on("update:model-value", make_str_handler(config.key))

                # Show default value
                ui.label(f"Default: {config.default_value}").classes(
                    "text-xs text-gray-400 mt-1"
                )

    return card


def create_admin_page() -> None:
    """Create the full admin configuration page."""
    drawer = create_sidebar()
    create_header_with_menu(drawer, "ADMIN SETTINGS")

    with ui.column().classes("w-full max-w-4xl mx-auto p-6 gap-6"):
        # Page description
        with ui.card().classes("w-full bg-blue-50"):
            with ui.row().classes("items-center gap-3"):
                ui.icon("info").classes("text-2xl text-blue-600")
                with ui.column():
                    ui.label("Configuration Settings").classes("font-bold text-blue-800")
                    ui.label(
                        "Changes are saved automatically. Restart a session for detection settings to take effect."
                    ).classes("text-sm text-blue-600")

        # Detection Settings
        create_config_card(
            category="detection",
            title="Detection Settings",
            icon="visibility",
        )

        # Capture Settings
        create_config_card(
            category="capture",
            title="Capture Settings",
            icon="videocam",
        )

        # Printer Settings
        create_config_card(
            category="printer",
            title="Printer Settings",
            icon="print",
        )

        # Reset button
        with ui.row().classes("w-full justify-center mt-4"):

            def reset_all():
                ConfigRepository.reset_to_defaults()
                ui.notify("All settings reset to defaults. Refresh page to see changes.", type="warning")

            ui.button(
                "Reset All to Defaults",
                icon="restart_alt",
                on_click=reset_all,
            ).props("color=negative outline")

        # Help section
        with ui.expansion("Understanding Detection Settings", icon="help").classes("w-full"):
            with ui.column().classes("gap-4 p-4"):
                ui.markdown("""
**hash_threshold** (default: 15)
- Controls how different two frames must be to count as a "new reel"
- Lower values (10-12): More sensitive, may false-trigger on video scene changes
- Higher values (18-25): Less sensitive, may miss similar-looking reels
- Recommended range: 12-20

**min_reel_duration** (default: 0.5s)
- Reels viewed shorter than this are ignored
- Filters out accidental quick scrolls
- Set to 0 to count all reels regardless of view time

**transition_frames** (default: 3)
- Number of mostly-black frames to wait during scroll animation
- Higher values: Better at handling slow scrolls
- Lower values: Faster detection but may misfire

**stable_frames** (default: 2)
- Frames that must match before confirming content is stable
- Prevents false triggers from glitchy frames

**capture_fps** (default: 10)
- Higher FPS = more accurate timing, more CPU usage
- 10 FPS is usually sufficient for reel detection
- Range: 5-30 (higher than 15 rarely needed)
                """)
