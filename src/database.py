import sqlite3
from pathlib import Path
from PyQt6.QtSql import QSqlDatabase

DB_PATH = Path(__file__).resolve().parent.parent / "databases" / "grants.db"


def sync_contest_aggregates(db_path=None, codkon=None):
    """
    Синхронизация агрегированных показателей таблицы gr_konk по реальным данным gr_proj.
    Гарантирует абсолютную ссылочную и расчетную целостность без накопления погрешностей.
    """
    target_path = str(db_path or DB_PATH)
    conn = sqlite3.connect(target_path)
    cur = conn.cursor()

    sql = """
        UPDATE gr_konk
        SET projects_count = (SELECT COUNT(*) FROM gr_proj WHERE gr_proj.codkon = gr_konk.codkon),
            plan_fin = (SELECT COALESCE(SUM(plan_fin), 0) FROM gr_proj WHERE gr_proj.codkon = gr_konk.codkon),
            fact_fin = (SELECT COALESCE(SUM(fact_fin), 0) FROM gr_proj WHERE gr_proj.codkon = gr_konk.codkon),
            fin_q1 = (SELECT COALESCE(SUM(fin_q1), 0) FROM gr_proj WHERE gr_proj.codkon = gr_konk.codkon),
            fin_q2 = (SELECT COALESCE(SUM(fin_q2), 0) FROM gr_proj WHERE gr_proj.codkon = gr_konk.codkon),
            fin_q3 = (SELECT COALESCE(SUM(fin_q3), 0) FROM gr_proj WHERE gr_proj.codkon = gr_konk.codkon),
            fin_q4 = (SELECT COALESCE(SUM(fin_q4), 0) FROM gr_proj WHERE gr_proj.codkon = gr_konk.codkon)
    """
    if codkon is not None:
        sql += " WHERE codkon = ?"
        cur.execute(sql, (codkon,))
    else:
        cur.execute(sql)

    conn.commit()
    conn.close()


def connect_db():
    """Подключение к локальной базе данных SQLite для PyQt6."""
    db = QSqlDatabase.addDatabase("QSQLITE")
    db.setDatabaseName(str(DB_PATH))
    if not db.open():
        print(f"Не удалось открыть базу данных: {DB_PATH}")
        return False
    return True
