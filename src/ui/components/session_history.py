"""Session history table component."""

from nicegui import ui

from src.printing.base import BasePrinter
from src.ui.database.repository import SessionRepository
from src.ui.components.receipt_viewer import show_receipt_modal


def create_session_history() -> ui.card:
    """Create the session history table.

    Returns:
        The session history card element.
    """
    with ui.card().classes("w-full") as card:
        with ui.row().classes("w-full items-center justify-between mb-4"):
            ui.label("SESSION HISTORY").classes("text-lg font-bold text-gray-700")
            refresh_btn = ui.button(icon="refresh", on_click=lambda: update_table()).props(
                "flat round"
            )
            refresh_btn.tooltip("Refresh history")

        table_container = ui.column().classes("w-full")

        def update_table():
            table_container.clear()
            with table_container:
                sessions = SessionRepository.get_all_sessions(limit=20)

                if not sessions:
                    with ui.column().classes("items-center justify-center py-8"):
                        ui.icon("history").classes("text-4xl text-gray-300")
                        ui.label("No sessions yet").classes("text-gray-400")
                        ui.label("Complete a session to see it here").classes(
                            "text-sm text-gray-400"
                        )
                    return

                # Create table
                columns = [
                    {"name": "date", "label": "Date/Time", "field": "date", "align": "left"},
                    {"name": "device", "label": "Device", "field": "device", "align": "left"},
                    {"name": "reels", "label": "Reels", "field": "reels", "align": "center"},
                    {"name": "duration", "label": "Duration", "field": "duration", "align": "center"},
                    {"name": "printer", "label": "Printer", "field": "printer", "align": "center"},
                    {"name": "actions", "label": "Actions", "field": "actions", "align": "center"},
                ]

                rows = []
                for session in sessions:
                    date_str = session.start_time.strftime("%Y-%m-%d %H:%M")
                    duration_str = BasePrinter.format_duration(session.total_time_seconds)

                    rows.append({
                        "id": session.id,
                        "date": date_str,
                        "device": f"{session.device_name} ({session.device_type})",
                        "reels": session.total_reels,
                        "duration": duration_str,
                        "printer": session.printer_type.title(),
                        "receipt": session.receipt_content,
                        "status": session.status,
                    })

                table = ui.table(
                    columns=columns,
                    rows=rows,
                    row_key="id",
                ).classes("w-full")

                # Add slot for actions column
                table.add_slot(
                    "body-cell-actions",
                    """
                    <q-td :props="props">
                        <q-btn flat round dense icon="visibility"
                               @click="$parent.$emit('view', props.row)"
                               :disable="!props.row.receipt">
                            <q-tooltip>View Receipt</q-tooltip>
                        </q-btn>
                    </q-td>
                    """,
                )

                def handle_view(e):
                    row = e.args
                    if row and row.get("receipt"):
                        session_info = row.get("date", "")
                        show_receipt_modal(row["receipt"], session_info)

                table.on("view", handle_view)

        # Initial render
        update_table()

    return card
