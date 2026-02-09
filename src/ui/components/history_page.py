"""Session history page component."""

from nicegui import ui

from src.printing.base import BasePrinter
from src.ui.database.repository import SessionRepository
from src.ui.components.receipt_viewer import show_receipt_modal


def create_history_page() -> None:
    """Create the session history page."""
    # Simple header
    with ui.header().classes("bg-purple-600 text-white"):
        with ui.row().classes("items-center gap-4"):
            ui.button(icon="arrow_back", on_click=lambda: ui.navigate.to("/")).props("flat color=white")
            ui.label("Session History").classes("text-xl font-bold")

    with ui.column().classes("w-full max-w-6xl mx-auto p-6 gap-6"):
        # Page header
        with ui.row().classes("w-full items-center justify-between"):
            with ui.row().classes("items-center gap-2"):
                ui.icon("history").classes("text-3xl text-gray-600")
                ui.label("Session History").classes("text-2xl font-bold text-gray-700")

            refresh_btn = ui.button(
                "Refresh", icon="refresh", on_click=lambda: ui.navigate.to("/history")
            ).props("outline")

        # Stats cards
        try:
            sessions = SessionRepository.get_all_sessions(limit=100)
        except Exception:
            sessions = []
        total_reels = sum(s.total_reels for s in sessions)
        total_time = sum(s.total_time_seconds for s in sessions)

        with ui.row().classes("w-full gap-4"):

            with ui.card().classes("flex-1 p-4"):
                with ui.column().classes("items-center"):
                    ui.label("Total Sessions").classes("text-gray-500 text-sm")
                    ui.label(str(len(sessions))).classes("text-3xl font-bold text-purple-600")

            with ui.card().classes("flex-1 p-4"):
                with ui.column().classes("items-center"):
                    ui.label("Total Reels").classes("text-gray-500 text-sm")
                    ui.label(str(total_reels)).classes("text-3xl font-bold text-pink-600")

            with ui.card().classes("flex-1 p-4"):
                with ui.column().classes("items-center"):
                    ui.label("Total Time").classes("text-gray-500 text-sm")
                    ui.label(BasePrinter.format_duration(total_time)).classes(
                        "text-3xl font-bold text-blue-600"
                    )

        # Session table
        table_container = ui.column().classes("w-full")

        def update_table():
            table_container.clear()
            with table_container:
                try:
                    sessions = SessionRepository.get_all_sessions(limit=50)
                except Exception:
                    sessions = []

                if not sessions:
                    with ui.card().classes("w-full"):
                        with ui.column().classes("items-center justify-center py-12"):
                            ui.icon("history").classes("text-6xl text-gray-300")
                            ui.label("No sessions yet").classes("text-xl text-gray-400 mt-4")
                            ui.label("Complete a tracking session to see it here").classes(
                                "text-gray-400"
                            )
                    return

                # Create table
                columns = [
                    {"name": "date", "label": "Date/Time", "field": "date", "align": "left", "sortable": True},
                    {"name": "device", "label": "Device", "field": "device", "align": "left"},
                    {"name": "reels", "label": "Reels", "field": "reels", "align": "center", "sortable": True},
                    {"name": "duration", "label": "Duration", "field": "duration", "align": "center"},
                    {"name": "printer", "label": "Printer", "field": "printer", "align": "center"},
                    {"name": "status", "label": "Status", "field": "status", "align": "center"},
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
                        "status": session.status.title(),
                    })

                with ui.card().classes("w-full"):
                    table = ui.table(
                        columns=columns,
                        rows=rows,
                        row_key="id",
                        pagination={"rowsPerPage": 10},
                    ).classes("w-full")

                    # Add slot for status column with badge
                    table.add_slot(
                        "body-cell-status",
                        """
                        <q-td :props="props">
                            <q-badge :color="props.row.status === 'Completed' ? 'green' : 'orange'">
                                {{ props.row.status }}
                            </q-badge>
                        </q-td>
                        """,
                    )

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
                            <q-btn flat round dense icon="delete" color="red"
                                   @click="$parent.$emit('delete', props.row)">
                                <q-tooltip>Delete Session</q-tooltip>
                            </q-btn>
                        </q-td>
                        """,
                    )

                    def handle_view(e):
                        row = e.args
                        if row and row.get("receipt"):
                            session_info = row.get("date", "")
                            show_receipt_modal(row["receipt"], session_info)

                    def handle_delete(e):
                        row = e.args
                        if row:
                            session_id = row.get("id")
                            if session_id:
                                SessionRepository.delete_session(session_id)
                                ui.notify("Session deleted", type="info")
                                update_table()

                    table.on("view", handle_view)
                    table.on("delete", handle_delete)

        # Initial render
        update_table()
