from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path
from typing import Any, cast

from flask import Flask, jsonify, redirect, render_template, request, session, url_for
import mysql.connector
from mysql.connector import Error, IntegrityError

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DB_HOST = "CHANGWEN919.mysql.eu.pythonanywhere-services.com"
DEFAULT_DB_USER = "CHANGWEN919"
DEFAULT_DB_NAME = "CHANGWEN919$default"

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "change-me-in-production")


def is_missing_table_error(exc: Exception) -> bool:
    return isinstance(exc, Error) and getattr(exc, "errno", None) == 1146


def missing_table_message() -> str:
    return "Database tables are missing. Open /setup and click Create/Reset Schema + Seed Data."


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
            use_pure=True,
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


def ensure_database_seeded(conn: Any) -> bool:
    cfg = db_config()
    rows = query_rows(
        conn,
        """
        SELECT COUNT(*) AS table_count
        FROM information_schema.tables
        WHERE table_schema = %s
          AND table_name IN ('Students', 'Courses', 'StudyGroups', 'GroupMembers')
        """,
        (cfg["database"],),
    )
    table_count = int(rows[0]["table_count"]) if rows else 0
    if table_count < 4:
        run_sql_file(conn, BASE_DIR / "sql" / "schema.sql")
        run_sql_file(conn, BASE_DIR / "sql" / "seed.sql")
        conn.commit()
        return True

    seed_rows = query_rows(conn, "SELECT COUNT(*) AS count FROM Courses")
    if seed_rows and int(seed_rows[0]["count"]) == 0:
        run_sql_file(conn, BASE_DIR / "sql" / "seed.sql")
        conn.commit()
        return True

    return False


def current_student_session() -> dict[str, Any] | None:
    student = session.get("student")
    return student if isinstance(student, dict) else None


def get_request_value(key: str) -> str:
    payload = request.get_json(silent=True)
    if isinstance(payload, dict):
        raw = payload.get(key, "")
        return str(raw).strip() if raw is not None else ""
    return (request.form.get(key) or "").strip()


def get_ready_connection() -> Any:
    conn = get_db_connection()
    ensure_database_seeded(conn)
    return conn


def user_error_message(exc: Exception) -> str:
    if is_missing_table_error(exc):
        return missing_table_message()
    return str(exc)


def api_error(message: str, status: int = 400) -> Any:
    return jsonify({"ok": False, "error": message}), status


def fetch_courses(conn: Any) -> list[dict[str, Any]]:
    return query_rows(conn, "SELECT course_id, course_name FROM Courses ORDER BY course_id")


def fetch_search_groups(
    conn: Any,
    course_filter: str,
    location_filter: str,
    meeting_after_sql: str | None,
) -> list[dict[str, Any]]:
    return query_rows(
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
          AND (%s IS NULL OR sg.meeting_time >= %s)
        GROUP BY sg.group_id, c.course_id, c.course_name, sg.meeting_time, sg.location, sg.notes, host.name
        ORDER BY sg.meeting_time ASC
        """,
        (
            course_filter,
            course_filter,
            course_filter,
            location_filter,
            location_filter,
            meeting_after_sql,
            meeting_after_sql,
        ),
    )


def fetch_group_members(conn: Any, group_id: int) -> list[dict[str, Any]]:
    return query_rows(
        conn,
        """
        SELECT s.student_id, s.name, s.email, s.major
        FROM GroupMembers gm
        JOIN Students s ON s.student_id = gm.student_id
        WHERE gm.group_id = %s
        ORDER BY s.name ASC
        """,
        (group_id,),
    )


def fetch_hosted_groups(conn: Any, host_student_id: int) -> list[dict[str, Any]]:
    return query_rows(
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


def fetch_my_joined_groups(conn: Any, student_id: int) -> list[dict[str, Any]]:
    return query_rows(
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
        (student_id,),
    )


def fetch_group_size_report(conn: Any, min_members: int) -> list[dict[str, Any]]:
    return query_rows(
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


def unwrap_endpoint_result(result: Any) -> tuple[Any, int]:
    if isinstance(result, tuple):
        body = result[0]
        status = int(result[1]) if len(result) > 1 and isinstance(result[1], int) else 200
        return body, status
    return result, 200


def run_legacy_action(action: str) -> tuple[bool, str]:
    handlers = {
        "register": api_register,
        "login": api_login,
        "logout": api_logout,
        "update_major": api_update_major,
        "create_group": api_create_group,
        "join_group": api_join_group,
        "leave_group": api_leave_group,
    }

    handler = handlers.get(action)
    if handler is None:
        return False, "Unsupported action for compatibility mode."

    body, status = unwrap_endpoint_result(handler())
    payload = body.get_json(silent=True) if hasattr(body, "get_json") else None

    if isinstance(payload, dict):
        if payload.get("ok") is True and status < 400:
            return True, str(payload.get("message", "Request completed."))
        return False, str(payload.get("error", f"Request failed ({status})."))

    if status < 400:
        return True, "Request completed."
    return False, f"Request failed ({status})."


@app.route("/", methods=["GET", "POST"])
def index() -> Any:
    if request.method == "POST":
        action = (request.form.get("action") or "").strip()
        if action != "":
            ok, message = run_legacy_action(action)
            if ok:
                return redirect(url_for("index", legacy_message=message), code=303)
            return redirect(url_for("index", legacy_error=message), code=303)
        return redirect(url_for("index"), code=303)

    return render_template("index.html")


@app.get("/api/bootstrap")
def api_bootstrap() -> Any:
    conn: Any | None = None
    try:
        conn = get_ready_connection()
        current_student = current_student_session()
        initial_groups = fetch_search_groups(conn, "", "", None)
        my_groups: list[dict[str, Any]] = []
        if current_student is not None:
            my_groups = fetch_my_joined_groups(conn, int(current_student["student_id"]))

        config = db_config()
        return jsonify(
            {
                "ok": True,
                "config": {"host": config["host"], "database": config["database"]},
                "current_student": current_student,
                "courses": fetch_courses(conn),
                "groups": initial_groups,
                "my_joined_groups": my_groups,
            }
        )
    except Exception as exc:
        return api_error(user_error_message(exc), 500)
    finally:
        if conn is not None:
            conn.close()


@app.get("/api/search-groups")
def api_search_groups() -> Any:
    conn: Any | None = None
    course_filter = (request.args.get("course_filter") or "").strip()
    location_filter = (request.args.get("location_filter") or "").strip()
    meeting_after_input = (request.args.get("meeting_after") or "").strip()

    meeting_after_sql: str | None = None
    if meeting_after_input != "":
        try:
            meeting_after_sql = parse_datetime_local(meeting_after_input)
        except ValueError:
            return api_error("Meeting After filter has invalid date/time format.")

    try:
        conn = get_ready_connection()
        groups = fetch_search_groups(conn, course_filter, location_filter, meeting_after_sql)
        return jsonify({"ok": True, "groups": groups})
    except Exception as exc:
        return api_error(user_error_message(exc), 500)
    finally:
        if conn is not None:
            conn.close()


@app.get("/api/group-members")
def api_group_members() -> Any:
    conn: Any | None = None
    group_id = parse_positive_int((request.args.get("group_id") or "").strip())
    if group_id is None:
        return api_error("Group members query failed: invalid group_id.")

    try:
        conn = get_ready_connection()
        return jsonify({"ok": True, "group_members": fetch_group_members(conn, group_id)})
    except Exception as exc:
        return api_error(user_error_message(exc), 500)
    finally:
        if conn is not None:
            conn.close()


@app.get("/api/hosted-groups")
def api_hosted_groups() -> Any:
    conn: Any | None = None
    host_student_id = parse_positive_int((request.args.get("host_student_id") or "").strip())
    if host_student_id is None:
        return api_error("Hosted groups query failed: invalid host_student_id.")

    try:
        conn = get_ready_connection()
        return jsonify({"ok": True, "hosted_groups": fetch_hosted_groups(conn, host_student_id)})
    except Exception as exc:
        return api_error(user_error_message(exc), 500)
    finally:
        if conn is not None:
            conn.close()


@app.get("/api/my-groups")
def api_my_groups() -> Any:
    conn: Any | None = None
    current_student = current_student_session()
    if current_student is None:
        return jsonify({"ok": True, "my_joined_groups": []})

    try:
        conn = get_ready_connection()
        return jsonify(
            {
                "ok": True,
                "my_joined_groups": fetch_my_joined_groups(conn, int(current_student["student_id"])),
            }
        )
    except Exception as exc:
        return api_error(user_error_message(exc), 500)
    finally:
        if conn is not None:
            conn.close()


@app.get("/api/group-size-report")
def api_group_size_report() -> Any:
    conn: Any | None = None
    min_members_input = (request.args.get("min_members") or "").strip()
    min_members = parse_non_negative_int(min_members_input)
    if min_members is None:
        min_members = 0

    try:
        conn = get_ready_connection()
        return jsonify({"ok": True, "group_size_report": fetch_group_size_report(conn, min_members)})
    except Exception as exc:
        return api_error(user_error_message(exc), 500)
    finally:
        if conn is not None:
            conn.close()


@app.post("/api/register")
def api_register() -> Any:
    conn: Any | None = None
    student_id = parse_positive_int(get_request_value("student_id"))
    name = get_request_value("name")
    email = get_request_value("email")
    major = get_request_value("major")

    if student_id is None or name == "" or email == "" or major == "":
        return api_error("Register failed: student_id, name, email, and major are required.")

    try:
        conn = get_ready_connection()
        assert conn is not None
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO Students (student_id, name, email, major) VALUES (%s, %s, %s, %s)",
                (student_id, name, email, major),
            )
            conn.commit()
        finally:
            cursor.close()

        return jsonify({"ok": True, "message": "Student registered successfully."})
    except IntegrityError as exc:
        if exc.errno == 1062:
            return api_error("Register failed: student_id or email already exists.")
        return api_error(f"Database operation failed: {exc}", 500)
    except Exception as exc:
        return api_error(user_error_message(exc), 500)
    finally:
        if conn is not None:
            conn.close()


@app.post("/api/login")
def api_login() -> Any:
    conn: Any | None = None
    student_id = parse_positive_int(get_request_value("student_id"))
    email = get_request_value("email")

    if student_id is None or email == "":
        return api_error("Login failed: student_id and email are required.")

    try:
        conn = get_ready_connection()
        rows = query_rows(
            conn,
            "SELECT student_id, name, email, major FROM Students WHERE student_id = %s AND email = %s",
            (student_id, email),
        )

        if len(rows) != 1:
            return api_error("Login failed: student_id/email combination not found.", 404)

        session["student"] = {
            "student_id": int(rows[0]["student_id"]),
            "name": rows[0]["name"],
            "email": rows[0]["email"],
            "major": rows[0]["major"],
        }

        return jsonify({"ok": True, "message": "Login successful.", "current_student": session["student"]})
    except Exception as exc:
        return api_error(user_error_message(exc), 500)
    finally:
        if conn is not None:
            conn.close()


@app.post("/api/logout")
def api_logout() -> Any:
    session.clear()
    return jsonify({"ok": True, "message": "You are logged out."})


@app.post("/api/update-major")
def api_update_major() -> Any:
    conn: Any | None = None
    current_student = current_student_session()
    if current_student is None:
        return api_error("Update failed: please log in first.", 401)

    major = get_request_value("major")
    if major == "":
        return api_error("Update failed: major cannot be empty.")

    try:
        conn = get_ready_connection()
        assert conn is not None
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
        return jsonify({"ok": True, "message": "Major updated successfully.", "current_student": session["student"]})
    except Exception as exc:
        return api_error(user_error_message(exc), 500)
    finally:
        if conn is not None:
            conn.close()


@app.post("/api/create-group")
def api_create_group() -> Any:
    conn: Any | None = None
    current_student = current_student_session()
    if current_student is None:
        return api_error("Create group failed: please log in first.", 401)

    course_id = parse_positive_int(get_request_value("course_id"))
    meeting_time_input = get_request_value("meeting_time")
    location = get_request_value("location")
    notes = get_request_value("notes")

    if course_id is None or meeting_time_input == "" or location == "":
        return api_error("Create group failed: course, meeting time, and location are required.")

    try:
        meeting_time = parse_datetime_local(meeting_time_input)
    except ValueError:
        return api_error("Create group failed: invalid meeting time format.")

    try:
        conn = get_ready_connection()
        assert conn is not None
        host_student_id = int(current_student["student_id"])
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO StudyGroups (course_id, host_student_id, meeting_time, location, notes)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (course_id, host_student_id, meeting_time, location, notes),
            )
            new_group_id = int(cursor.lastrowid)

            cursor.execute(
                "INSERT INTO GroupMembers (group_id, student_id) VALUES (%s, %s)",
                (new_group_id, host_student_id),
            )
            conn.commit()
        finally:
            cursor.close()

        return jsonify(
            {
                "ok": True,
                "message": f"Study group created successfully (group_id: {new_group_id}).",
                "group_id": new_group_id,
            }
        )
    except Exception as exc:
        if conn is not None:
            conn.rollback()
        return api_error(user_error_message(exc), 500)
    finally:
        if conn is not None:
            conn.close()


@app.post("/api/join-group")
def api_join_group() -> Any:
    conn: Any | None = None
    current_student = current_student_session()
    if current_student is None:
        return api_error("Join group failed: please log in first.", 401)

    group_id = parse_positive_int(get_request_value("group_id"))
    if group_id is None:
        return api_error("Join group failed: invalid group_id.")

    try:
        conn = get_ready_connection()
        assert conn is not None
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

        return jsonify({"ok": True, "message": f"You joined group {group_id} successfully."})
    except IntegrityError as exc:
        if exc.errno == 1062:
            return api_error("Join group failed: you are already a member of this group.")
        return api_error(f"Database operation failed: {exc}", 500)
    except Exception as exc:
        return api_error(user_error_message(exc), 500)
    finally:
        if conn is not None:
            conn.close()


@app.post("/api/leave-group")
def api_leave_group() -> Any:
    conn: Any | None = None
    current_student = current_student_session()
    if current_student is None:
        return api_error("Leave group failed: please log in first.", 401)

    group_id = parse_positive_int(get_request_value("group_id"))
    if group_id is None:
        return api_error("Leave group failed: invalid group_id.")

    try:
        conn = get_ready_connection()
        assert conn is not None
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
            return jsonify({"ok": True, "message": f"No membership existed for group {group_id}."})
        return jsonify({"ok": True, "message": f"You left group {group_id}."})
    except Exception as exc:
        return api_error(user_error_message(exc), 500)
    finally:
        if conn is not None:
            conn.close()


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
        if is_missing_table_error(exc):
            errors.append(missing_table_message())
        else:
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
