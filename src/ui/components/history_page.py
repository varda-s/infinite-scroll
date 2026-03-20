"""Session history page component."""

from nicegui import ui

from src.printing.base import BasePrinter
from src.ui.database.repository import SessionRepository
from src.ui.components.receipt_viewer import show_session_detail_modal
from src.ui.services.media_paths import to_media_url


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

        # Stats cards
        stats_row = ui.row().classes("w-full gap-4 flex-wrap")
        table_container = ui.column().classes("w-full")
        charts_container = ui.column().classes("w-full gap-4")
        last_session_signature: tuple | None = None

        def refresh_history() -> None:
            nonlocal last_session_signature
            try:
                sessions = SessionRepository.get_all_sessions(limit=200)
            except Exception:
                sessions = []

            signature = tuple(
                (
                    s.id,
                    s.total_reels,
                    round(float(s.total_time_seconds), 2),
                    s.status,
                    s.end_time,
                )
                for s in sessions
            )
            if signature == last_session_signature:
                return
            last_session_signature = signature

            total_reels = sum(s.total_reels for s in sessions)
            total_time = sum(s.total_time_seconds for s in sessions)
            average_session_time = total_time / len(sessions) if sessions else 0.0
            average_reels_per_session = total_reels / len(sessions) if sessions else 0.0
            session_receipts: dict[int, list] = {}

            for session in sessions:
                try:
                    session_receipts[session.id] = SessionRepository.get_session_receipts(session.id)
                except Exception:
                    session_receipts[session.id] = []

            stats_row.clear()
            with stats_row:
                with ui.card().classes("flex-1 min-w-[180px] p-4"):
                    with ui.column().classes("items-center"):
                        ui.label("Total Sessions").classes("text-gray-500 text-sm")
                        ui.label(str(len(sessions))).classes("text-3xl font-bold text-purple-600")

                with ui.card().classes("flex-1 min-w-[180px] p-4"):
                    with ui.column().classes("items-center"):
                        ui.label("Total Reels").classes("text-gray-500 text-sm")
                        ui.label(str(total_reels)).classes("text-3xl font-bold text-pink-600")

                with ui.card().classes("flex-1 min-w-[180px] p-4"):
                    with ui.column().classes("items-center"):
                        ui.label("Total Time").classes("text-gray-500 text-sm")
                        ui.label(BasePrinter.format_duration(total_time)).classes(
                            "text-3xl font-bold text-blue-600"
                        )

                with ui.card().classes("flex-1 min-w-[180px] p-4"):
                    with ui.column().classes("items-center"):
                        ui.label("Avg Session Time").classes("text-gray-500 text-sm")
                        ui.label(BasePrinter.format_duration(average_session_time)).classes(
                            "text-3xl font-bold text-emerald-600"
                        )

                with ui.card().classes("flex-1 min-w-[180px] p-4"):
                    with ui.column().classes("items-center"):
                        ui.label("Avg Reels / Session").classes("text-gray-500 text-sm")
                        ui.label(f"{average_reels_per_session:.1f}").classes(
                            "text-3xl font-bold text-amber-600"
                        )

            table_container.clear()
            with table_container:
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
                    {"name": "preview", "label": "Preview", "field": "preview", "align": "center"},
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
                    receipts = session_receipts.get(session.id, [])
                    preview = None
                    for receipt in receipts:
                        if receipt.screenshot_path:
                            preview = to_media_url(receipt.screenshot_path)
                            break

                    rows.append({
                        "id": session.id,
                        "date": date_str,
                        "preview": preview,
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
                        "body-cell-preview",
                        """
                        <q-td :props="props">
                            <q-img v-if="props.row.preview"
                                   :src="props.row.preview"
                                   style="width: 40px; height: 72px; border-radius: 6px;" />
                            <q-icon v-else name="image_not_supported" color="grey-5" />
                        </q-td>
                        """,
                    )

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
                        if row:
                            session_info = row.get("date", "")
                            show_session_detail_modal(row["id"], session_info)

                    def handle_delete(e):
                        row = e.args
                        if row:
                            session_id = row.get("id")
                            if session_id:
                                SessionRepository.delete_session(session_id)
                                ui.notify("Session deleted", type="info")
                                refresh_history()

                    table.on("view", handle_view)
                    table.on("delete", handle_delete)

            charts_container.clear()
            with charts_container:
                if not sessions:
                    return

                sessions_per_day: dict[str, int] = {}
                daily_reels: dict[str, int] = {}
                daily_time_minutes: dict[str, float] = {}
                hour_map: dict[int, float] = {i: 0.0 for i in range(24)}

                for session in sessions:
                    day_key = session.start_time.strftime("%Y-%m-%d")
                    sessions_per_day[day_key] = sessions_per_day.get(day_key, 0) + 1
                    daily_reels[day_key] = daily_reels.get(day_key, 0) + session.total_reels
                    daily_time_minutes[day_key] = daily_time_minutes.get(day_key, 0.0) + (
                        session.total_time_seconds / 60.0
                    )

                    for receipt in session_receipts.get(session.id, []):
                        hour_map[receipt.timestamp.hour] += receipt.duration_seconds / 60.0

                day_labels = sorted(sessions_per_day.keys())
                session_count_values = [sessions_per_day[d] for d in day_labels]
                daily_reel_values = [daily_reels[d] for d in day_labels]
                daily_time_values = [round(daily_time_minutes[d], 2) for d in day_labels]

                recent_sessions = list(reversed(sessions[:20]))
                recent_labels = [s.start_time.strftime("%m-%d %H:%M") for s in recent_sessions]
                recent_time_values = [round(s.total_time_seconds / 60.0, 2) for s in recent_sessions]
                recent_reel_values = [s.total_reels for s in recent_sessions]

                hour_labels = [f"{h:02d}:00" for h in range(24)]
                hour_values = [round(hour_map[h], 2) for h in range(24)]

                with ui.row().classes("w-full gap-4 flex-wrap"):
                    with ui.card().classes("flex-1 min-w-[320px] p-4"):
                        ui.label("Sessions Per Day").classes("text-lg font-semibold text-gray-700 mb-2")
                        ui.echart(
                            {
                                "tooltip": {"trigger": "axis"},
                                "xAxis": {"type": "category", "data": day_labels},
                                "yAxis": {"type": "value", "name": "Sessions"},
                                "series": [{"type": "bar", "data": session_count_values, "itemStyle": {"color": "#8b5cf6"}}],
                            }
                        ).classes("w-full h-72")

                    with ui.card().classes("flex-1 min-w-[320px] p-4"):
                        ui.label("Total Reels Per Day").classes("text-lg font-semibold text-gray-700 mb-2")
                        ui.echart(
                            {
                                "tooltip": {"trigger": "axis"},
                                "xAxis": {"type": "category", "data": day_labels},
                                "yAxis": {"type": "value", "name": "Reels"},
                                "series": [{"type": "bar", "data": daily_reel_values, "itemStyle": {"color": "#ec4899"}}],
                            }
                        ).classes("w-full h-72")

                with ui.row().classes("w-full gap-4 flex-wrap"):
                    with ui.card().classes("flex-1 min-w-[320px] p-4"):
                        ui.label("Time Spent Per Session").classes("text-lg font-semibold text-gray-700 mb-2")
                        ui.echart(
                            {
                                "tooltip": {"trigger": "axis"},
                                "xAxis": {"type": "category", "data": recent_labels, "axisLabel": {"rotate": 30}},
                                "yAxis": {"type": "value", "name": "Minutes"},
                                "series": [{"type": "bar", "data": recent_time_values, "itemStyle": {"color": "#3b82f6"}}],
                            }
                        ).classes("w-full h-72")

                    with ui.card().classes("flex-1 min-w-[320px] p-4"):
                        ui.label("Reels Per Session").classes("text-lg font-semibold text-gray-700 mb-2")
                        ui.echart(
                            {
                                "tooltip": {"trigger": "axis"},
                                "xAxis": {"type": "category", "data": recent_labels, "axisLabel": {"rotate": 30}},
                                "yAxis": {"type": "value", "name": "Reels"},
                                "series": [{"type": "line", "smooth": True, "data": recent_reel_values, "itemStyle": {"color": "#f59e0b"}}],
                            }
                        ).classes("w-full h-72")

                with ui.row().classes("w-full gap-4 flex-wrap"):
                    with ui.card().classes("flex-1 min-w-[320px] p-4"):
                        ui.label("Daily Reel Time").classes("text-lg font-semibold text-gray-700 mb-2")
                        ui.echart(
                            {
                                "tooltip": {"trigger": "axis"},
                                "xAxis": {"type": "category", "data": day_labels},
                                "yAxis": {"type": "value", "name": "Minutes"},
                                "series": [{"type": "bar", "data": daily_time_values, "itemStyle": {"color": "#10b981"}}],
                            }
                        ).classes("w-full h-72")

                    with ui.card().classes("flex-1 min-w-[320px] p-4"):
                        ui.label("Time Of Day Usage").classes("text-lg font-semibold text-gray-700 mb-2")
                        ui.echart(
                            {
                                "tooltip": {"trigger": "axis"},
                                "xAxis": {"type": "category", "data": hour_labels},
                                "yAxis": {"type": "value", "name": "Minutes"},
                                "series": [{"type": "line", "smooth": True, "data": hour_values, "itemStyle": {"color": "#6366f1"}}],
                            }
                        ).classes("w-full h-72")

        refresh_history()
        ui.timer(1.0, refresh_history)
