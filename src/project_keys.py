"""Создание НИР с кодом, уникальным в пределах конкурса."""

import re
import sqlite3


PROJECT_FIELDS = (
    "codkon", "codproj", "codvuz", "vuz_short_name", "grnti_code",
    "plan_fin", "fact_fin", "fin_q1", "fin_q2", "fin_q3", "fin_q4",
    "leader_fio", "leader_post", "leader_rank", "leader_degree", "proj_name",
)
MONEY_FIELDS = ("plan_fin", "fact_fin", "fin_q1", "fin_q2", "fin_q3", "fin_q4")


def add_project(conn: sqlite3.Connection, project: dict) -> int:
    """Добавить НИР. При повторе кода взять MAX(codproj) + 1 в том же конкурсе."""
    if conn.in_transaction:
        raise ValueError("Добавление НИР требует отдельной транзакции")

    contest = project["codkon"]
    university = project["codvuz"]
    code = project.get("codproj")
    if type(contest) is not int or contest <= 0:
        raise ValueError("Код конкурса должен быть положительным целым числом")
    if type(university) is not int or university <= 0:
        raise ValueError("Код вуза должен быть положительным целым числом")
    if code is not None and (type(code) is not int or code <= 0):
        raise ValueError("Код НИР должен быть положительным целым числом")

    values = {field: project.get(field, 0) for field in MONEY_FIELDS}
    if any(type(value) is not int or value < 0 for value in values.values()):
        raise ValueError("Финансирование должно быть неотрицательным целым числом")
    if not re.fullmatch(
        r"\d{2}\.\d{2}\.\d{2}(?:,\s*\d{2}\.\d{2}\.\d{2})?",
        project["grnti_code"],
    ):
        raise ValueError("Код ГРНТИ должен иметь формат XX.YY.ZZ")
    if not project["leader_fio"].strip() or not project["proj_name"].strip():
        raise ValueError("Руководитель и тема НИР обязательны")

    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("BEGIN IMMEDIATE")
    try:
        if conn.execute("SELECT 1 FROM gr_konk WHERE codkon = ?", (contest,)).fetchone() is None:
            raise ValueError(f"Конкурс {contest} не найден")
        row = conn.execute(
            "SELECT vuz_short_name FROM vuz WHERE codvuz = ?", (university,)
        ).fetchone()
        if row is None:
            raise ValueError(f"Вуз {university} не найден")

        if code is None or conn.execute(
            "SELECT 1 FROM gr_proj WHERE codkon = ? AND codproj = ?", (contest, code)
        ).fetchone():
            code = conn.execute(
                "SELECT COALESCE(MAX(codproj), 0) + 1 FROM gr_proj WHERE codkon = ?",
                (contest,),
            ).fetchone()[0]

        data = {
            **values,
            "codkon": contest,
            "codproj": code,
            "codvuz": university,
            "vuz_short_name": row[0],
            "grnti_code": project["grnti_code"],
            "leader_fio": project["leader_fio"],
            "leader_post": project.get("leader_post"),
            "leader_rank": project.get("leader_rank"),
            "leader_degree": project.get("leader_degree"),
            "proj_name": project["proj_name"],
        }
        columns = ", ".join(PROJECT_FIELDS)
        placeholders = ", ".join("?" for _ in PROJECT_FIELDS)
        conn.execute(
            f"INSERT INTO gr_proj ({columns}) VALUES ({placeholders})",
            tuple(data[field] for field in PROJECT_FIELDS),
        )
        conn.commit()
        return code
    except Exception:
        conn.rollback()
        raise
