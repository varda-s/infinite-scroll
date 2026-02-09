"""Sidebar navigation component with hamburger menu."""

from nicegui import ui, app

from src.ui.components.auth import get_current_user, logout


def create_sidebar() -> ui.left_drawer:
    """Create the sidebar navigation drawer.

    Returns:
        The drawer element.
    """
    user = get_current_user()

    with ui.left_drawer(value=False).classes("bg-gray-800") as drawer:
        # User info section
        with ui.column().classes("w-full p-4 bg-gray-900"):
            with ui.row().classes("items-center gap-3"):
                ui.icon("account_circle").classes("text-4xl text-purple-400")
                with ui.column().classes("gap-0"):
                    ui.label(user.get("display_name", "User")).classes(
                        "text-white font-medium"
                    )
                    ui.label(f"@{user.get('user_id', '')}").classes(
                        "text-gray-400 text-sm"
                    )

        ui.separator().classes("bg-gray-700")

        # Navigation links
        with ui.column().classes("w-full p-2 gap-1"):
            # Dashboard
            with ui.link(target="/").classes("w-full no-underline"):
                with ui.row().classes(
                    "w-full items-center gap-3 p-3 rounded hover:bg-gray-700 cursor-pointer"
                ):
                    ui.icon("dashboard").classes("text-xl text-gray-300")
                    ui.label("Dashboard").classes("text-gray-200")

            # Session History
            with ui.link(target="/history").classes("w-full no-underline"):
                with ui.row().classes(
                    "w-full items-center gap-3 p-3 rounded hover:bg-gray-700 cursor-pointer"
                ):
                    ui.icon("history").classes("text-xl text-gray-300")
                    ui.label("Session History").classes("text-gray-200")

            ui.separator().classes("bg-gray-700 my-2")

            # Admin (only for admins)
            if user.get("is_admin"):
                with ui.link(target="/admin").classes("w-full no-underline"):
                    with ui.row().classes(
                        "w-full items-center gap-3 p-3 rounded hover:bg-gray-700 cursor-pointer"
                    ):
                        ui.icon("admin_panel_settings").classes("text-xl text-orange-400")
                        ui.label("Admin Settings").classes("text-gray-200")

                ui.separator().classes("bg-gray-700 my-2")

        # Spacer
        ui.element("div").classes("flex-grow")

        # Logout button at bottom
        with ui.column().classes("w-full p-2"):
            ui.button("Logout", icon="logout", on_click=logout).classes(
                "w-full"
            ).props("flat color=red")

    return drawer


def create_header_with_menu(drawer: ui.left_drawer, title: str = "INSTAGRAM REEL TRACKER") -> None:
    """Create the application header with hamburger menu.

    Args:
        drawer: The sidebar drawer to toggle.
        title: Header title text.
    """
    user = get_current_user()

    with ui.header().classes("bg-gradient-to-r from-purple-600 to-pink-500"):
        with ui.row().classes("w-full items-center justify-between px-4"):
            # Left: Hamburger menu
            with ui.row().classes("items-center gap-2"):
                ui.button(icon="menu", on_click=drawer.toggle).props(
                    "flat round color=white"
                )

            # Center: Logo and title
            with ui.row().classes("items-center gap-2"):
                ui.icon("videocam").classes("text-3xl text-white")
                ui.label(title).classes("text-2xl font-bold text-white tracking-wide")

            # Right: User info
            with ui.row().classes("items-center gap-2"):
                ui.label(user.get("display_name", "")).classes("text-white")
                ui.icon("account_circle").classes("text-2xl text-white")
