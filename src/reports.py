from pathlib import Path
from typing import Optional

from src.database import get_sqlite_connection, recalculate_gr_konk


def generate_vuz_funding_statement(db_path: Optional[Path] = None) -> list[dict]:
    """Формирование сводной ведомости финансирования НИР по вузам."""
    conn = get_sqlite_connection(db_path)
    cur = conn.cursor()
    cur.execute("""
    SELECT 
        v.codvuz,
        v.vuz_short_name,
        v.city,
        COUNT(p.id) AS proj_count,
        SUM(p.plan_fin) AS total_plan,
        SUM(p.fact_fin) AS total_fact,
        SUM(p.fin_q1) AS q1,
        SUM(p.fin_q2) AS q2,
        SUM(p.fin_q3) AS q3,
        SUM(p.fin_q4) AS q4
    FROM vuz v
    JOIN gr_proj p ON v.codvuz = p.codvuz
    GROUP BY v.codvuz, v.vuz_short_name, v.city
    ORDER BY total_plan DESC;
    """)
    rows = cur.fetchall()
    conn.close()

    return [dict(r) for r in rows]


def apply_funding_order(percent: float = 100.0, db_path: Optional[Path] = None) -> dict:
    """Выпуск распоряжения о финансировании: начисление фактических сумм и поквартальная разбивка.
    
    Сумма факта начисляется как процент от планового финансирования.
    Разбивка по кварталам: 1 кв (20%), 2 кв (25%), 3 кв (25%), 4 кв (остаток).
    """
    if not (0.0 <= percent <= 100.0):
        raise ValueError(f"Процент финансирования должен быть от 0 до 100, получено: {percent}")

    ratio = percent / 100.0
    conn = get_sqlite_connection(db_path)
    cur = conn.cursor()

    cur.execute("SELECT id, plan_fin FROM gr_proj;")
    projects = cur.fetchall()

    updates = []
    total_allocated = 0

    for proj in projects:
        pid = proj["id"]
        plan = proj["plan_fin"]
        fact = int(round(plan * ratio))
        q1 = int(round(fact * 0.20))
        q2 = int(round(fact * 0.25))
        q3 = int(round(fact * 0.25))
        q4 = fact - (q1 + q2 + q3)
        updates.append((fact, q1, q2, q3, q4, pid))
        total_allocated += fact

    cur.executemany("""
    UPDATE gr_proj
    SET fact_fin = ?, fin_q1 = ?, fin_q2 = ?, fin_q3 = ?, fin_q4 = ?
    WHERE id = ?;
    """, updates)

    conn.commit()
    conn.close()

    # Обязательный пересчет конкурсов после изменения финансирования per Полотнов
    recalculate_gr_konk(db_path)

    return {
        "projects_updated": len(updates),
        "total_allocated": total_allocated,
        "percent": percent,
    }


def reset_funding(db_path: Optional[Path] = None) -> None:
    """Сброс фактического финансирования в ноль."""
    conn = get_sqlite_connection(db_path)
    cur = conn.cursor()
    cur.execute("""
    UPDATE gr_proj
    SET fact_fin = 0, fin_q1 = 0, fin_q2 = 0, fin_q3 = 0, fin_q4 = 0;
    """)
    conn.commit()
    conn.close()
    recalculate_gr_konk(db_path)
