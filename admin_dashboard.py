"""
Простая админка для просмотра статистики.
Поднимает http.server и читает БД напрямую (только чтение).
"""

from __future__ import annotations

import base64
import html
import logging
import os
import sqlite3
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from config import settings

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)


def resource_path(relative_path):
    """Получить абсолютный путь к ресурсу, работает для разработки и для PyInstaller"""
    base_path = getattr(sys, "_MEIPASS", os.path.abspath("."))
    return os.path.join(base_path, relative_path)


DB_PATH = Path(settings.DB_PATH)
TEMPLATE_PATH = Path(resource_path("templates/dashboard.html"))


def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def _scalar(connection: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> int:
    row = connection.execute(sql, params).fetchone()
    return int(row[0] or 0) if row else 0


def _rows(
    connection: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()
) -> list[dict[str, Any]]:
    return [dict(row) for row in connection.execute(sql, params).fetchall()]


def load_dashboard_data() -> dict[str, Any]:
    """Return dashboard metrics from SQLite, or empty-state data if DB is absent."""
    empty_stats = {
        "total_listings": 0,
        "total_users": 0,
        "total_notifications": 0,
        "accuracy_percent": 0,
        "avg_discount": 0,
        "total_savings": 0,
        "models_count": 0,
    }
    if not DB_PATH.exists():
        return {
            "db_path": str(DB_PATH),
            "db_exists": False,
            "stats": empty_stats,
            "recent_validation": [],
            "recent_listings": [],
            "last_parsed_at": None,
        }

    try:
        with _connect() as connection:
            total_notifications = _scalar(connection, "SELECT COUNT(*) FROM validation_log")
            false_positives = _scalar(
                connection,
                "SELECT COUNT(*) FROM validation_log WHERE is_false_positive = 1",
            )
            accuracy = (
                int((total_notifications - false_positives) / total_notifications * 100)
                if total_notifications
                else 0
            )
            avg_discount_row = connection.execute(
                "SELECT AVG(discount_percent) FROM validation_log"
            ).fetchone()
            last_parsed = connection.execute("SELECT MAX(parsed_at) FROM listings").fetchone()

            total_savings = _scalar(
                connection,
                "SELECT SUM(median_price - price) FROM validation_log WHERE is_false_positive = 0",
            )

            return {
                "db_path": str(DB_PATH),
                "db_exists": True,
                "stats": {
                    "total_listings": _scalar(connection, "SELECT COUNT(*) FROM listings"),
                    "total_users": _scalar(connection, "SELECT COUNT(*) FROM users"),
                    "total_notifications": total_notifications,
                    "accuracy_percent": accuracy,
                    "avg_discount": int(avg_discount_row[0] or 0) if avg_discount_row else 0,
                    "total_savings": total_savings,
                    "models_count": _scalar(connection, "SELECT COUNT(*) FROM models"),
                },
                "recent_validation": _rows(
                    connection,
                    """
                    SELECT notified_at, listing_id, model_name, price, median_price,
                           discount_percent, is_false_positive
                    FROM validation_log
                    ORDER BY notified_at DESC, log_id DESC
                    LIMIT 50
                    """,
                ),
                "recent_listings": _rows(
                    connection,
                    """
                    SELECT l.parsed_at, l.listing_id, l.title, l.price, l.city, l.url,
                           l.discount_percent, l.image_url, m.name AS model_name
                    FROM listings l
                    INNER JOIN models m ON m.model_id = l.model_id
                    ORDER BY l.parsed_at DESC, l.rowid DESC
                    LIMIT 50
                    """,
                ),
                "recent_reports": _rows(
                    connection,
                    """
                    SELECT r.created_at, r.user_id, r.listing_id, r.reason,
                           l.title, l.url
                    FROM reports r
                    LEFT JOIN listings l ON r.listing_id = l.listing_id
                    ORDER BY r.created_at DESC
                    LIMIT 10
                    """,
                ),
                "all_models": _rows(connection, "SELECT model_id, name FROM models ORDER BY name"),
                "all_cities": _rows(connection, "SELECT DISTINCT city FROM listings ORDER BY city"),
                "last_parsed_at": last_parsed[0] if last_parsed else None,
            }
    except sqlite3.Error as exc:
        return {
            "db_path": str(DB_PATH),
            "db_exists": True,
            "db_error": str(exc),
            "stats": empty_stats,
            "recent_validation": [],
            "recent_listings": [],
            "last_parsed_at": None,
        }


def _escape(value: Any) -> str:
    return html.escape(str(value if value is not None else ""))


def _render_validation_rows(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return '<tr><td colspan="6" class="empty-cell">Уведомлений пока нет.</td></tr>'

    rendered = []
    for item in rows:
        status_badge = (
            '<span class="badge red">● false positive</span>'
            if item["is_false_positive"]
            else '<span class="badge green">● ok</span>'
        )
        discount = item["discount_percent"]
        discount_class = "green" if discount >= 10 else "neutral"

        row_class = "good-deal" if discount >= 15 else ""

        rendered.append(
            f'<tr class="{row_class}">'
            f'<td class="muted">{_escape(item["notified_at"])}</td>'
            f"<td><div>{_escape(item['model_name'])}</div>"
            f'<div class="muted">{_escape(item["listing_id"])}</div></td>'
            f'<td class="price" data-value="{item["price"]}">{_escape(item["price"])} RUB</td>'
            f'<td class="muted" data-value="{item["median_price"]}">'
            f"{_escape(item['median_price'])} RUB</td>"
            f'<td data-value="{discount}"><span class="discount-label {discount_class}">'
            f"{_escape(discount)}%</span></td>"
            f"<td>{status_badge}</td>"
            "</tr>"
        )
    return "\n".join(rendered)


def _render_listing_rows(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return '<tr><td colspan="5" class="empty-cell">Объявлений пока нет.</td></tr>'

    rendered = []
    icon_svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" '
        'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
        'stroke-linecap="round" stroke-linejoin="round" style="vertical-align: middle;">'
        '<path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path>'
        '<polyline points="15 3 21 3 21 9"></polyline>'
        '<line x1="10" y1="14" x2="21" y2="3"></line></svg>'
    )

    for item in rows:
        price = item["price"]
        discount = item["discount_percent"]
        raw_url = item.get("url") or ""
        url = _escape(raw_url) if (raw_url.startswith("http://") or raw_url.startswith("https://")) else "#"
        raw_img = item.get("image_url") or ""
        img_url = _escape(raw_img) if (raw_img.startswith("http://") or raw_img.startswith("https://") or raw_img.startswith("//")) else ""

        price_style = ""
        discount_class = "neutral"
        discount_str = f"{discount}%"

        if discount > 0:
            price_style = "color: #10b981;"
            discount_class = "green"
            discount_str = f"+{discount}%"
        elif discount <= -10:
            price_style = "color: #f43f5e;"
            discount_class = "red"

        img_tag = ""
        if img_url:
            img_tag = (
                f'<img src="{img_url}" style="width: 60px; height: 45px; '
                f'object-fit: cover; border-radius: 4px; border: 1px solid #4a5568;">'
            )

        title_with_link = (
            f'<div style="display: flex; align-items: center; gap: 15px;">'
            f"{img_tag}"
            f'<div style="display: flex; flex-direction: column; gap: 4px;">'
            f"<span>{_escape(item['title'])}</span>"
            f'<a href="{url}" target="_blank" class="link-icon" title="Открыть на Avito" '
            f'style="font-size: 14px; text-decoration: none; color: #48bb78;">'
            f"{icon_svg} Открыть</a>"
            f"</div>"
            f"</div>"
        )

        rendered.append(
            "<tr>"
            f'<td class="muted">{_escape(item["parsed_at"])}</td>'
            f"<td><div>{_escape(item['model_name'])}</div>"
            f'<div class="muted">{_escape(item["city"])}</div></td>'
            f"<td>{title_with_link}</td>"
            f'<td class="price" style="{price_style}" data-value="{price}">'
            f"{_escape(price)} RUB</td>"
            f'<td data-value="{discount}"><span class="discount-label {discount_class}">'
            f"{_escape(discount_str)}</span></td>"
            "</tr>"
        )
    return "\n".join(rendered)


def _render_report_rows(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return '<tr><td colspan="4" class="empty-cell">Жалоб пока нет.</td></tr>'

    rendered = []
    for item in rows:
        title = item["title"] or "Неизвестно"
        raw_url = item.get("url") or ""
        url = _escape(raw_url) if (raw_url.startswith("http://") or raw_url.startswith("https://")) else "#"
        rendered.append(
            "<tr>"
            f'<td class="muted">{_escape(item["created_at"])}</td>'
            f"<td>{_escape(item['user_id'])}</td>"
            f'<td><a href="{url}" target="_blank" style="color: #48bb78;">{_escape(title)}</a></td>'
            f"<td>{_escape(item['reason'])}</td>"
            "</tr>"
        )
    return "\n".join(rendered)


def _render_options(items: list[dict], value_key: str, label_key: str) -> str:
    return "\n".join(
        [
            f'<option value="{_escape(item[value_key])}">{_escape(item[label_key])}</option>'
            for item in items
        ]
    )


def render_dashboard() -> bytes:
    data = load_dashboard_data()
    stats = data["stats"]
    db_error = data.get("db_error")
    db_status = "DB error" if db_error else "DB connected" if data["db_exists"] else "DB not found"
    db_status_class = "error" if db_error or not data["db_exists"] else "ok"
    error_block = (
        f'<section class="panel"><div class="empty">{_escape(db_error)}</div></section>'
        if db_error
        else ""
    )

    model_options = _render_options(data.get("all_models", []), "name", "name")
    city_options = _render_options(data.get("all_cities", []), "city", "city")

    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    html_text = template
    replacements = {
        "{{DB_PATH}}": _escape(data["db_path"]),
        "{{DB_STATUS}}": db_status,
        "{{DB_STATUS_CLASS}}": db_status_class,
        "{{DB_ERROR_BLOCK}}": error_block,
        "{{TOTAL_LISTINGS}}": _escape(stats["total_listings"]),
        "{{TOTAL_NOTIFICATIONS}}": _escape(stats["total_notifications"]),
        "{{ACCURACY_PERCENT}}": _escape(stats["accuracy_percent"]),
        "{{TOTAL_USERS}}": _escape(stats["total_users"]),
        "{{AVG_DISCOUNT}}": _escape(stats["avg_discount"]),
        "{{TOTAL_SAVINGS}}": f"{stats['total_savings']:,}".replace(",", " "),
        "{{MODELS_COUNT}}": _escape(stats["models_count"]),
        "{{LAST_PARSED_AT}}": _escape(data["last_parsed_at"] or "нет данных"),
        "{{MODEL_OPTIONS}}": model_options,
        "{{CITY_OPTIONS}}": city_options,
        "{{VALIDATION_ROWS}}": _render_validation_rows(data["recent_validation"]),
        "{{LISTING_ROWS}}": _render_listing_rows(data["recent_listings"]),
        "{{REPORT_ROWS}}": _render_report_rows(data.get("recent_reports", [])),
    }
    for key, value in replacements.items():
        html_text = html_text.replace(key, value)
    return html_text.encode("utf-8")


class DashboardHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        user = settings.DASHBOARD_USER
        password = settings.DASHBOARD_PASS
        if user and password:
            auth_header = self.headers.get("Authorization")
            if not auth_header:
                self.send_response(HTTPStatus.UNAUTHORIZED)
                self.send_header("WWW-Authenticate", 'Basic realm="Admin Dashboard"')
                self.end_headers()
                self.wfile.write(b"Unauthorized")
                return

            try:
                auth_type, auth_data = auth_header.split(None, 1)
                if auth_type.lower() != "basic":
                    raise ValueError
                decoded = base64.b64decode(auth_data).decode("utf-8")
                req_user, req_pass = decoded.split(":", 1)
                import secrets
                if not (secrets.compare_digest(req_user, user) and secrets.compare_digest(req_pass, password)):
                    raise ValueError
            except Exception:
                self.send_response(HTTPStatus.UNAUTHORIZED)
                self.send_header("WWW-Authenticate", 'Basic realm="Admin Dashboard"')
                self.end_headers()
                self.wfile.write(b"Unauthorized")
                return

        if self.path not in {"/", "/health"}:
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        if self.path == "/health":
            body = b"ok"
            content_type = "text/plain; charset=utf-8"
        else:
            body = render_dashboard()
            content_type = "text/html; charset=utf-8"

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        return


def main() -> None:
    host = settings.DASHBOARD_HOST
    port = settings.DASHBOARD_PORT

    if not settings.DASHBOARD_USER or not settings.DASHBOARD_PASS:
        logger.warning(
            "⚠️ SECURITY WARNING: Dashboard is running WITHOUT password protection! "
            "Anyone who can connect to this port will have read access to the database metrics "
            "and logs. Please configure DASHBOARD_USER and DASHBOARD_PASS in your .env file."
        )
    else:
        logger.info("🔐 Dashboard is protected with Basic Authentication.")

    server = ThreadingHTTPServer((host, port), DashboardHandler)
    logger.info(f"Admin dashboard: http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
