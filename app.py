from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path
from typing import Any, cast

from flask import Flask, render_template, request, session
import mysql.connector
from mysql.connector import Error, IntegrityError

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DB_HOST = "CHANGWEN919.mysql.eu.pythonanywhere-services.com"
DEFAULT_DB_USER = "CHANGWEN919"
DEFAULT_DB_NAME = "CHANGWEN919$default"

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "change-me-in-production")


def read_db_config_file(path: Path) -> dict[str, Any]:
    namespace: dict[str, Any] = {}
    exec(path.read_text(encoding="utf-8"), namespace)
    loaded = namespace.get("DB_CONFIG")
    return loaded if isinstance(loaded, dict) else {}


def file_db_config() -> dict[str, Any]:
    for file_name in ("db_credentials.py", "db.credentials.py"):
        path = BASE_DIR / file_name
        if path.exists():
            return read_db_config_file(path)
    return {}


def db_config() -> dict[str, Any]:
    file_cfg = file_db_config()
    return {
        "host": os.getenv("DB_HOST") or str(file_cfg.get("host", DEFAULT_DB_HOST)),
        "user": os.getenv("DB_USER") or str(file_cfg.get("user", DEFAULT_DB_USER)),
        "password": os.getenv("DB_PASS") or str(file_cfg.get("pass", "")),
        "database": os.getenv("DB_NAME") or str(file_cfg.get("name", DEFAULT_DB_NAME)),
        "port": int(os.getenv("DB_PORT") or file_cfg.get("port", 3306)),
    }


def get_db_connection() -> Any:
    cfg = db_config()
    if cfg["user"] == "" or cfg["database"] == "":
        raise RuntimeError(
            "Missing DB credentials. Set DB_USER/DB_PASS/DB_NAME or create db_credentials.py."
        )

    try:
        connection = mysql.connector.connect(
            host=cfg["host"],
            user=cfg["user"],
            password=cfg["password"],
            database=cfg["database"],
            port=cfg["port"],
            autocommit=False,
        )
    except Error as exc:
        raise RuntimeError(f"Database connection failed: {exc}") from exc

    if not connection.is_connected():
        raise RuntimeError("Database connection failed: connection not established")

    return connection


def parse_positive_int(value: str) -> int | None:
    value = (value or "").strip()
    if not value.isdigit():
        return None
    parsed = int(value)
    return parsed if parsed > 0 else None


def parse_non_negative_int(value: str) -> int | None:
    value = (value or "").strip()
    if not value.isdigit():
        return None
    parsed = int(value)
    return parsed if parsed >= 0 else None


def parse_datetime_local(value: str) -> str:
    value = (value or "").strip()
    if value == "":
        return ""

    # Supports HTML datetime-local format like 2026-04-12T17:30.
    return datetime.fromisoformat(value).strftime("%Y-%m-%d %H:%M:%S")


def query_rows(
    conn: Any,
    sql: str,
    params: tuple[Any, ...] = (),
) -> list[dict[str, Any]]:
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(sql, params)
        return cast(list[dict[str, Any]], cursor.fetchall())
    finally:
        cursor.close()


def run_sql_file(conn: Any, file_path: Path) -> None:
    sql = file_path.read_text(encoding="utf-8")
    cursor = conn.cursor()
    try:
        statements = [part.strip() for part in sql.split(";") if part.strip()]
        for statement in statements:
            cursor.execute(statement)
    finally:
        cursor.close()


@app.route("/", methods=["GET", "POST"])
def index() -> str:
    messages: list[str] = []
    errors: list[str] = []

    config = db_config()
    current_student = session.get("student")

    connection_ok = False
    conn: Any | None = None

    courses: list[dict[str, Any]] = []
    search_groups: list[dict[str, Any]] = []
    group_members: list[dict[str, Any]] = []
    hosted_groups: list[dict[str, Any]] = []
    my_joined_groups: list[dict[str, Any]] = []
    group_size_report: list[dict[str, Any]] = []

    selected_members_group = (request.args.get("members_group_id") or "").strip()
    selected_host_student = (request.args.get("host_student_id") or "").strip()
    min_members_input = (request.args.get("min_members") or "").strip()
    search_course_filter = (request.args.get("course_filter") or "").strip()
    search_location_filter = (request.args.get("location_filter") or "").strip()
    meeting_after_input = (request.args.get("meeting_after") or "").strip()

    meeting_after_sql = ""
    if meeting_after_input != "":
        try:
            meeting_after_sql = parse_datetime_local(meeting_after_input)
        except ValueError:
            errors.append("Meeting After filter has invalid date/time format.")

    try:
        conn = get_db_connection()
        connection_ok = True
    except Exception as exc:
        errors.append(str(exc))

    if connection_ok and conn is not None and request.method == "POST":
        action = (request.form.get("action") or "").strip()
        transaction_started = False

        try:
            if action == "register":
                student_id = parse_positive_int((request.form.get("student_id") or ""))
                name = (request.form.get("name") or "").strip()
                email = (request.form.get("email") or "").strip()
                major = (request.form.get("major") or "").strip()

                if student_id is None or name == "" or email == "" or major == "":
                    raise RuntimeError("Register failed: student_id, name, email, and major are required.")

                cursor = conn.cursor()
                try:
                    cursor.execute(
                        "INSERT INTO Students (student_id, name, email, major) VALUES (%s, %s, %s, %s)",
                        (student_id, name, email, major),
                    )
                    conn.commit()
                finally:
                    cursor.close()

                messages.append("Student registered successfully.")

            elif action == "login":
                student_id = parse_positive_int((request.form.get("student_id") or ""))
                email = (request.form.get("email") or "").strip()

                if student_id is None or email == "":
                    raise RuntimeError("Login failed: student_id and email are required.")

                rows = query_rows(
                    conn,
                    "SELECT student_id, name, email, major FROM Students WHERE student_id = %s AND email = %s",
                    (student_id, email),
                )

                if len(rows) != 1:
                    raise RuntimeError("Login failed: student_id/email combination not found.")

                session["student"] = {
                    "student_id": int(rows[0]["student_id"]),
                    "name": rows[0]["name"],
                    "email": rows[0]["email"],
                    "major": rows[0]["major"],
                }
                current_student = session["student"]
                messages.append("Login successful.")

            elif action == "logout":
                session.clear()
                current_student = None
                messages.append("You are logged out.")

            elif action == "create_group":
                if current_student is None:
                    raise RuntimeError("Create group failed: please log in first.")

                course_id = parse_positive_int((request.form.get("course_id") or ""))
                meeting_time_input = (request.form.get("meeting_time") or "").strip()
                location = (request.form.get("location") or "").strip()
                notes = (request.form.get("notes") or "").strip()

                if course_id is None or meeting_time_input == "" or location == "":
                    raise RuntimeError("Create group failed: course, meeting time, and location are required.")

                try:
                    meeting_time = parse_datetime_local(meeting_time_input)
                except ValueError as exc:
                    raise RuntimeError("Create group failed: invalid meeting time format.") from exc

                host_student_id = int(current_student["student_id"])

                conn.start_transaction()
                transaction_started = True

                cursor = conn.cursor()
                try:
                    cursor.execute(
                        """
                        INSERT INTO StudyGroups (course_id, host_student_id, meeting_time, location, notes)
                        VALUES (%s, %s, %s, %s, %s)
                        """,
                        (course_id, host_student_id, meeting_time, location, notes),
                    )
                    new_group_id = cursor.lastrowid

                    cursor.execute(
                        "INSERT INTO GroupMembers (group_id, student_id) VALUES (%s, %s)",
                        (new_group_id, host_student_id),
                    )

                    conn.commit()
                    transaction_started = False
                finally:
                    cursor.close()

                messages.append(f"Study group created successfully (group_id: {new_group_id}).")

            elif action == "join_group":
                if current_student is None:
                    raise RuntimeError("Join group failed: please log in first.")

                group_id = parse_positive_int((request.form.get("group_id") or ""))
                if group_id is None:
                    raise RuntimeError("Join group failed: invalid group_id.")

                student_id = int(current_student["student_id"])
                cursor = conn.cursor()
                try:
                    cursor.execute(
                        "INSERT INTO GroupMembers (group_id, student_id) VALUES (%s, %s)",
                        (group_id, student_id),
                    )
                    conn.commit()
                finally:
                    cursor.close()

                messages.append(f"You joined group {group_id} successfully.")

            elif action == "leave_group":
                if current_student is None:
                    raise RuntimeError("Leave group failed: please log in first.")

                group_id = parse_positive_int((request.form.get("group_id") or ""))
                if group_id is None:
                    raise RuntimeError("Leave group failed: invalid group_id.")

                student_id = int(current_student["student_id"])
                cursor = conn.cursor()
                try:
                    cursor.execute(
                        "DELETE FROM GroupMembers WHERE group_id = %s AND student_id = %s",
                        (group_id, student_id),
                    )
                    deleted_rows = cursor.rowcount
                    conn.commit()
                finally:
                    cursor.close()

                if deleted_rows == 0:
                    messages.append(f"No membership existed for group {group_id}.")
                else:
                    messages.append(f"You left group {group_id}.")

            elif action == "update_major":
                if current_student is None:
                    raise RuntimeError("Update failed: please log in first.")

                major = (request.form.get("major") or "").strip()
                if major == "":
                    raise RuntimeError("Update failed: major cannot be empty.")

                student_id = int(current_student["student_id"])
                cursor = conn.cursor()
                try:
                    cursor.execute(
                        "UPDATE Students SET major = %s WHERE student_id = %s",
                        (major, student_id),
                    )
                    conn.commit()
                finally:
                    cursor.close()

                session["student"]["major"] = major
                current_student = session["student"]
                messages.append("Major updated successfully.")

        except IntegrityError as exc:
            if transaction_started:
                conn.rollback()

            if exc.errno == 1062:
                if action == "register":
                    errors.append("Register failed: student_id or email already exists.")
                elif action == "join_group":
                    errors.append("Join group failed: you are already a member of this group.")
                else:
                    errors.append(f"Database operation failed: {exc}")
            else:
                errors.append(f"Database operation failed: {exc}")

        except Exception as exc:
            if transaction_started:
                conn.rollback()
            errors.append(str(exc))

    if connection_ok and conn is not None:
        courses = query_rows(conn, "SELECT course_id, course_name FROM Courses ORDER BY course_id")

        search_groups = query_rows(
            conn,
            """
            SELECT
                sg.group_id,
                c.course_id,
                c.course_name,
                sg.meeting_time,
                sg.location,
                sg.notes,
                host.name AS host_name,
                COUNT(gm.student_id) AS member_count
            FROM StudyGroups sg
            JOIN Courses c ON c.course_id = sg.course_id
            JOIN Students host ON host.student_id = sg.host_student_id
            LEFT JOIN GroupMembers gm ON gm.group_id = sg.group_id
            WHERE (%s = '' OR c.course_name LIKE CONCAT('%', %s, '%') OR CAST(c.course_id AS CHAR) = %s)
              AND (%s = '' OR sg.location LIKE CONCAT('%', %s, '%'))
              AND (%s = '' OR sg.meeting_time >= %s)
            GROUP BY sg.group_id, c.course_id, c.course_name, sg.meeting_time, sg.location, sg.notes, host.name
            ORDER BY sg.meeting_time ASC
            """,
            (
                search_course_filter,
                search_course_filter,
                search_course_filter,
                search_location_filter,
                search_location_filter,
                meeting_after_sql,
                meeting_after_sql,
            ),
        )

        members_group_id = parse_positive_int(selected_members_group)
        if members_group_id is not None:
            group_members = query_rows(
                conn,
                """
                SELECT s.student_id, s.name, s.email, s.major
                FROM GroupMembers gm
                JOIN Students s ON s.student_id = gm.student_id
                WHERE gm.group_id = %s
                ORDER BY s.name ASC
                """,
                (members_group_id,),
            )

        host_student_id = parse_positive_int(selected_host_student)
        if host_student_id is not None:
            hosted_groups = query_rows(
                conn,
                """
                SELECT sg.group_id, c.course_name, sg.meeting_time, sg.location
                FROM StudyGroups sg
                JOIN Courses c ON c.course_id = sg.course_id
                WHERE sg.host_student_id = %s
                ORDER BY sg.meeting_time ASC
                """,
                (host_student_id,),
            )

        if current_student is not None:
            my_joined_groups = query_rows(
                conn,
                """
                SELECT sg.group_id, c.course_name, sg.meeting_time, sg.location, host.name AS host_name
                FROM GroupMembers gm
                JOIN StudyGroups sg ON sg.group_id = gm.group_id
                JOIN Courses c ON c.course_id = sg.course_id
                JOIN Students host ON host.student_id = sg.host_student_id
                WHERE gm.student_id = %s
                ORDER BY sg.meeting_time ASC
                """,
                (int(current_student["student_id"]),),
            )

        min_members = parse_non_negative_int(min_members_input)
        if min_members is None:
            min_members = 0

        group_size_report = query_rows(
            conn,
            """
            SELECT c.course_name, sg.group_id, COUNT(gm.student_id) AS member_total
            FROM StudyGroups sg
            JOIN Courses c ON c.course_id = sg.course_id
            LEFT JOIN GroupMembers gm ON gm.group_id = sg.group_id
            GROUP BY c.course_name, sg.group_id
            HAVING COUNT(gm.student_id) >= %s
            ORDER BY member_total DESC, c.course_name ASC
            """,
            (min_members,),
        )

    if conn is not None:
        conn.close()

    return render_template(
        "index.html",
        config=config,
        connection_ok=connection_ok,
        current_student=current_student,
        messages=messages,
        errors=errors,
        courses=courses,
        search_groups=search_groups,
        group_members=group_members,
        hosted_groups=hosted_groups,
        my_joined_groups=my_joined_groups,
        group_size_report=group_size_report,
        selected_members_group=selected_members_group,
        selected_host_student=selected_host_student,
        min_members_input=min_members_input,
        search_course_filter=search_course_filter,
        search_location_filter=search_location_filter,
        meeting_after_input=meeting_after_input,
    )


@app.route("/setup", methods=["GET", "POST"])
def setup() -> str:
    status: list[str] = []
    errors: list[str] = []
    config = db_config()

    conn: Any | None = None
    try:
        conn = get_db_connection()
        if conn is None:
            raise RuntimeError("Database connection failed: connection not established")
        status.append("Connected to MySQL server successfully.")

        if request.method == "POST" and (request.form.get("action") or "") == "setup_db":
            run_sql_file(conn, BASE_DIR / "sql" / "schema.sql")
            run_sql_file(conn, BASE_DIR / "sql" / "seed.sql")
            conn.commit()
            status.append("Schema and sample data loaded from sql/schema.sql and sql/seed.sql.")

        count_rows = query_rows(
            conn,
            """
            SELECT
                (SELECT COUNT(*) FROM Students) AS students,
                (SELECT COUNT(*) FROM Courses) AS courses,
                (SELECT COUNT(*) FROM StudyGroups) AS study_groups,
                (SELECT COUNT(*) FROM GroupMembers) AS group_members
            """,
        )
        if count_rows:
            row = count_rows[0]
            status.append(
                "Current rows -> "
                f"Students: {row['students']}, "
                f"Courses: {row['courses']}, "
                f"StudyGroups: {row['study_groups']}, "
                f"GroupMembers: {row['group_members']}"
            )

    except Exception as exc:
        errors.append(str(exc))

    finally:
        if conn is not None:
            conn.close()

    return render_template("setup.html", config=config, status=status, errors=errors)


@app.route("/test-connection")
def test_connection() -> str:
    config = db_config()
    connection_message = ""
    error_message = ""
    server_time = ""
    current_database = ""

    conn: Any | None = None
    try:
        conn = get_db_connection()
        connection_message = "Connection to MySQL succeeded."

        rows = query_rows(conn, "SELECT NOW() AS server_time, DATABASE() AS current_database")
        if rows:
            server_time = str(rows[0].get("server_time", ""))
            current_database = str(rows[0].get("current_database", ""))

    except Exception as exc:
        error_message = str(exc)

    finally:
        if conn is not None:
            conn.close()

    return render_template(
        "test_connection.html",
        config=config,
        connection_message=connection_message,
        error_message=error_message,
        server_time=server_time,
        current_database=current_database,
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8000")), debug=os.getenv("FLASK_DEBUG") == "1")
