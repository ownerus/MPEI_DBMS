"""Привести ключ НИР к паре (код конкурса, код НИР)."""

import argparse
import sqlite3
from pathlib import Path


DEFAULT_DB = Path(__file__).resolve().parent.parent / "databases" / "grants.db"
MONEY = ("plan_fin", "fact_fin", "fin_q1", "fin_q2", "fin_q3", "fin_q4")


def repair_duplicate_keys(conn):
    maximum = dict(conn.execute("SELECT codkon, MAX(codproj) FROM gr_proj GROUP BY codkon"))
    seen = set()
    fixed = []
    for row_id, contest, code in conn.execute(
        "SELECT id, codkon, codproj FROM gr_proj ORDER BY id"
    ).fetchall():
        key = (contest, code)
        if key in seen:
            maximum[contest] += 1
            new_code = maximum[contest]
            conn.execute("UPDATE gr_proj SET codproj = ? WHERE id = ?", (new_code, row_id))
            fixed.append((contest, code, new_code))
        else:
            seen.add(key)
    return fixed


def execute_script_in_transaction(conn, path):
    statement = ""
    for line in path.read_text().splitlines(keepends=True):
        statement += line
        if sqlite3.complete_statement(statement):
            conn.execute(statement)
            statement = ""
    if statement.strip():
        raise ValueError(f"Незавершенная SQL-команда в {path}")


def migrate(db_path):
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("BEGIN IMMEDIATE")
        columns = conn.execute("PRAGMA table_info(gr_proj)").fetchall()
        if not columns:
            raise ValueError("Таблица gr_proj не найдена")

        primary_key = [row[1] for row in sorted(columns, key=lambda row: row[5]) if row[5]]
        fixed = []
        if primary_key != ["codkon", "codproj"]:
            fixed = repair_duplicate_keys(conn)
            conn.execute("""
                CREATE TABLE gr_proj_new (
                    codkon INTEGER NOT NULL,
                    codproj INTEGER NOT NULL,
                    codvuz INTEGER NOT NULL,
                    vuz_short_name TEXT NOT NULL,
                    grnti_code TEXT NOT NULL,
                    plan_fin INTEGER NOT NULL DEFAULT 0,
                    fact_fin INTEGER NOT NULL DEFAULT 0,
                    fin_q1 INTEGER NOT NULL DEFAULT 0,
                    fin_q2 INTEGER NOT NULL DEFAULT 0,
                    fin_q3 INTEGER NOT NULL DEFAULT 0,
                    fin_q4 INTEGER NOT NULL DEFAULT 0,
                    leader_fio TEXT NOT NULL,
                    leader_post TEXT,
                    leader_rank TEXT,
                    leader_degree TEXT,
                    proj_name TEXT NOT NULL,
                    PRIMARY KEY (codkon, codproj),
                    FOREIGN KEY (codkon) REFERENCES gr_konk(codkon),
                    FOREIGN KEY (codvuz) REFERENCES vuz(codvuz)
                )
            """)
            conn.execute("""
                INSERT INTO gr_proj_new (
                    codkon, codproj, codvuz, vuz_short_name, grnti_code,
                    plan_fin, fact_fin, fin_q1, fin_q2, fin_q3, fin_q4,
                    leader_fio, leader_post, leader_rank, leader_degree, proj_name
                ) SELECT
                    codkon, codproj, codvuz, vuz_short_name, grnti_code,
                    plan_fin, fact_fin, fin_q1, fin_q2, fin_q3, fin_q4,
                    leader_fio, leader_post, leader_rank, leader_degree, proj_name
                FROM gr_proj
            """)
            conn.execute("DROP TABLE gr_proj")
            conn.execute("ALTER TABLE gr_proj_new RENAME TO gr_proj")

        aggregate = ", ".join(
            f"{field} = COALESCE((SELECT SUM({field}) FROM gr_proj "
            f"WHERE codkon = gr_konk.codkon), 0)" for field in MONEY
        )
        conn.execute(
            "UPDATE gr_konk SET projects_count = "
            "(SELECT COUNT(*) FROM gr_proj WHERE codkon = gr_konk.codkon), " + aggregate
        )
        execute_script_in_transaction(
            conn, Path(__file__).resolve().parent.parent / "databases" / "project_integrity.sql"
        )
        errors = conn.execute("PRAGMA foreign_key_check").fetchall()
        if errors:
            raise ValueError(f"Нарушены внешние ключи: {errors[:5]}")
        conn.commit()
        conn.execute("PRAGMA foreign_keys = ON")
        return fixed
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("db", nargs="?", type=Path, default=DEFAULT_DB)
    args = parser.parse_args()
    changes = migrate(args.db)
    print(f"Ключи НИР проверены. Исправлено повторов: {len(changes)}")
    for contest, old, new in changes:
        print(f"Конкурс {contest}: {old} → {new}")
