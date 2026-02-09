"""Authentication pages - Login and Signup."""

from nicegui import ui, app

from src.ui.database.repository import UserRepository


def create_login_page() -> None:
    """Create the login page."""
    # Check if already logged in
    if app.storage.user.get("authenticated"):
        ui.navigate.to("/")
        return

    with ui.column().classes("absolute-center items-center gap-6"):
        # Logo and title
        with ui.card().classes("w-96 p-8"):
            with ui.column().classes("items-center gap-4 w-full"):
                ui.icon("videocam").classes("text-6xl text-purple-600")
                ui.label("Instagram Reel Tracker").classes(
                    "text-2xl font-bold text-gray-700"
                )
                ui.label("Sign in to continue").classes("text-gray-500")

            ui.separator().classes("my-4")

            # Login form
            user_id_input = ui.input(
                label="User ID",
                placeholder="Enter your user ID",
            ).classes("w-full")

            password_input = ui.input(
                label="Password",
                placeholder="Enter your password",
                password=True,
                password_toggle_button=True,
            ).classes("w-full")

            error_label = ui.label("").classes("text-red-500 text-sm hidden")

            def do_login():
                user_id = user_id_input.value
                password = password_input.value

                if not user_id or not password:
                    error_label.text = "Please enter both user ID and password"
                    error_label.classes(remove="hidden")
                    return

                user = UserRepository.authenticate(user_id, password)
                if user:
                    app.storage.user["authenticated"] = True
                    app.storage.user["user_id"] = user.user_id
                    app.storage.user["display_name"] = user.display_name
                    app.storage.user["is_admin"] = user.is_admin
                    app.storage.user["db_id"] = user.id
                    ui.navigate.to("/")
                else:
                    error_label.text = "Invalid user ID or password"
                    error_label.classes(remove="hidden")

            ui.button("Sign In", on_click=do_login).classes("w-full mt-4").props(
                "color=purple"
            )

            # Handle enter key
            password_input.on("keydown.enter", do_login)

            ui.separator().classes("my-4")

            with ui.row().classes("w-full justify-center gap-1"):
                ui.label("Don't have an account?").classes("text-gray-500")
                ui.link("Sign up", "/signup").classes("text-purple-600 font-medium")


def create_signup_page() -> None:
    """Create the signup page."""
    # Check if already logged in
    if app.storage.user.get("authenticated"):
        ui.navigate.to("/")
        return

    with ui.column().classes("absolute-center items-center gap-6"):
        with ui.card().classes("w-96 p-8"):
            with ui.column().classes("items-center gap-4 w-full"):
                ui.icon("person_add").classes("text-6xl text-purple-600")
                ui.label("Create Account").classes("text-2xl font-bold text-gray-700")
                ui.label("Sign up to get started").classes("text-gray-500")

            ui.separator().classes("my-4")

            # Signup form
            user_id_input = ui.input(
                label="User ID",
                placeholder="Choose a unique user ID",
            ).classes("w-full")

            display_name_input = ui.input(
                label="Display Name",
                placeholder="Your display name (optional)",
            ).classes("w-full")

            password_input = ui.input(
                label="Password",
                placeholder="Choose a password",
                password=True,
                password_toggle_button=True,
            ).classes("w-full")

            confirm_password_input = ui.input(
                label="Confirm Password",
                placeholder="Confirm your password",
                password=True,
                password_toggle_button=True,
            ).classes("w-full")

            error_label = ui.label("").classes("text-red-500 text-sm hidden")
            success_label = ui.label("").classes("text-green-500 text-sm hidden")

            def do_signup():
                user_id = user_id_input.value
                display_name = display_name_input.value
                password = password_input.value
                confirm_password = confirm_password_input.value

                # Validation
                if not user_id or not password:
                    error_label.text = "User ID and password are required"
                    error_label.classes(remove="hidden")
                    success_label.classes(add="hidden")
                    return

                if len(user_id) < 3:
                    error_label.text = "User ID must be at least 3 characters"
                    error_label.classes(remove="hidden")
                    success_label.classes(add="hidden")
                    return

                if len(password) < 4:
                    error_label.text = "Password must be at least 4 characters"
                    error_label.classes(remove="hidden")
                    success_label.classes(add="hidden")
                    return

                if password != confirm_password:
                    error_label.text = "Passwords do not match"
                    error_label.classes(remove="hidden")
                    success_label.classes(add="hidden")
                    return

                if UserRepository.user_exists(user_id):
                    error_label.text = "User ID already taken"
                    error_label.classes(remove="hidden")
                    success_label.classes(add="hidden")
                    return

                # Create user (first user is admin)
                is_first_user = UserRepository.get_user_count() == 0
                user = UserRepository.create_user(
                    user_id=user_id,
                    password=password,
                    display_name=display_name,
                    is_admin=is_first_user,
                )

                if user:
                    # Auto-login after signup
                    app.storage.user["authenticated"] = True
                    app.storage.user["user_id"] = user.user_id
                    app.storage.user["display_name"] = user.display_name
                    app.storage.user["is_admin"] = user.is_admin
                    app.storage.user["db_id"] = user.id

                    success_label.text = "Account created! Logging you in..."
                    success_label.classes(remove="hidden")
                    error_label.classes(add="hidden")
                    ui.timer(1.0, lambda: ui.navigate.to("/"), once=True)
                else:
                    error_label.text = "Failed to create account"
                    error_label.classes(remove="hidden")
                    success_label.classes(add="hidden")

            ui.button("Create Account", on_click=do_signup).classes("w-full mt-4").props(
                "color=purple"
            )

            ui.separator().classes("my-4")

            with ui.row().classes("w-full justify-center gap-1"):
                ui.label("Already have an account?").classes("text-gray-500")
                ui.link("Sign in", "/login").classes("text-purple-600 font-medium")


def require_auth() -> bool:
    """Check if user is authenticated, redirect to login if not.

    Returns:
        True if authenticated, False if redirected.
    """
    if not app.storage.user.get("authenticated"):
        ui.navigate.to("/login")
        return False
    return True


def get_current_user() -> dict:
    """Get current logged-in user info."""
    return {
        "user_id": app.storage.user.get("user_id"),
        "display_name": app.storage.user.get("display_name"),
        "is_admin": app.storage.user.get("is_admin", False),
        "db_id": app.storage.user.get("db_id"),
    }


def logout() -> None:
    """Log out the current user."""
    app.storage.user.clear()
    ui.navigate.to("/login")
