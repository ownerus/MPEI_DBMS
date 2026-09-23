import sqlite3
from pathlib import Path
from typing import Optional

from PyQt6.QtSql import QSqlDatabase, QSqlQuery

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = BASE_DIR / "databases" / "grants.db"


def get_db_path() -> Path:
    return DEFAULT_DB_PATH


def init_connection(db_path: Optional[Path] = None) -> QSqlDatabase:
    """Подключение к SQLite через драйвер QtSql с включением foreign keys."""
    target_path = Path(db_path) if db_path else DEFAULT_DB_PATH

    if not target_path.exists():
        raise FileNotFoundError(
            f"База данных не найдена: {target_path}. "
            f"Запустите scripts/etl_import_excel.py для создания базы."
        )

    # Повторное использование существующего соединения при наличии
    db = QSqlDatabase.database("grants_connection", open=False)
    if not db.isValid():
        db = QSqlDatabase.addDatabase("QSQLITE", "grants_connection")

    if not db.isOpen():
        db.setDatabaseName(str(target_path))
        if not db.open():
            err = db.lastError().text()
            raise RuntimeError(f"Не удалось открыть базу данных {target_path}: {err}")

        query = QSqlQuery(db)
        query.exec("PRAGMA foreign_keys = ON;")
        query.exec("PRAGMA journal_mode = WAL;")
        query.exec("PRAGMA busy_timeout = 5000;")

    return db


def get_sqlite_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """Стандартное подключение sqlite3 для сервисных операций и пересчетов."""
    target_path = Path(db_path) if db_path else DEFAULT_DB_PATH
    conn = sqlite3.connect(target_path, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA busy_timeout = 5000;")
    return conn


def recalculate_gr_konk(db_path: Optional[Path] = None) -> None:
    """Пересчет агрегированных финансовых и количественных показателей конкурсов."""
    with get_sqlite_connection(db_path) as conn:
        conn.execute("""
        UPDATE gr_konk
        SET projects_count = (
                SELECT COUNT(*) FROM gr_proj WHERE gr_proj.codkon = gr_konk.codkon
            ),
            plan_fin = COALESCE((
                SELECT SUM(plan_fin) FROM gr_proj WHERE gr_proj.codkon = gr_konk.codkon
            ), 0),
            fact_fin = COALESCE((
                SELECT SUM(fact_fin) FROM gr_proj WHERE gr_proj.codkon = gr_konk.codkon
            ), 0),
            fin_q1 = COALESCE((
                SELECT SUM(fin_q1) FROM gr_proj WHERE gr_proj.codkon = gr_konk.codkon
            ), 0),
            fin_q2 = COALESCE((
                SELECT SUM(fin_q2) FROM gr_proj WHERE gr_proj.codkon = gr_konk.codkon
            ), 0),
            fin_q3 = COALESCE((
                SELECT SUM(fin_q3) FROM gr_proj WHERE gr_proj.codkon = gr_konk.codkon
            ), 0),
            fin_q4 = COALESCE((
                SELECT SUM(fin_q4) FROM gr_proj WHERE gr_proj.codkon = gr_konk.codkon
            ), 0);
        """)
        conn.commit()
