import sqlite3
from pathlib import Path
import pandas as pd
import xlrd

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "Источники" / "файлы данных"
DB_DIR = BASE_DIR / "databases"
DB_PATH = DB_DIR / "grants.db"


def clean_and_import_data():
    """Простой скрипт загрузки и нормализации данных Варианта 7 в SQLite."""
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("PRAGMA foreign_keys = ON;")

    print("1. Загрузка справочника вузов (VUZ.XLS)...")
    wb_vuz = xlrd.open_workbook(DATA_DIR / "VUZ.XLS", encoding_override="cp1251")
    sh_vuz = wb_vuz.sheet_by_index(0)
    vuz_headers = [str(sh_vuz.cell_value(0, c)).strip().lower() for c in range(sh_vuz.ncols)]

    cur.execute("DROP TABLE IF EXISTS gr_proj;")
    cur.execute("DROP TABLE IF EXISTS gr_konk;")
    cur.execute("DROP TABLE IF EXISTS vuz;")

    cur.execute("""
    CREATE TABLE vuz (
        codvuz INTEGER PRIMARY KEY,
        vuz_name TEXT NOT NULL,
        vuz_full_name TEXT NOT NULL,
        vuz_short_name TEXT NOT NULL,
        status TEXT,
        city TEXT,
        region TEXT,
        obl_code TEXT,
        obl_name TEXT,
        department TEXT,
        profile TEXT
    );
    """)

    vuz_short_map = {}
    vuz_rows = []
    for r in range(1, sh_vuz.nrows):
        row = dict(zip(vuz_headers, [sh_vuz.cell_value(r, c) for c in range(sh_vuz.ncols)]))
        codvuz = int(str(row["codvuz"]).strip())
        short_name = str(row.get("z2", "")).strip()
        vuz_short_map[codvuz] = short_name

        vuz_rows.append((
            codvuz,
            str(row.get("z1", "")).strip(),
            str(row.get("z1full", "")).strip(),
            short_name,
            str(row.get("status", "")).strip(),
            str(row.get("city", "")).strip(),
            str(row.get("region", "")).strip(),
            str(row.get("obl", "")).strip(),
            str(row.get("oblname", "")).strip(),
            str(row.get("gr_ved", "")).strip(),
            str(row.get("prof", "")).strip(),
        ))

    cur.executemany("INSERT INTO vuz VALUES (?,?,?,?,?,?,?,?,?,?,?);", vuz_rows)
    print(f"   Загружено вузов: {len(vuz_rows)}")

    print("2. Загрузка проектов НИР (Gr_prog.xlsx)...")
    df_proj = pd.read_excel(DATA_DIR / "Gr_prog.xlsx", sheet_name="Gr_pr")

    cur.execute("""
    CREATE TABLE gr_proj (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        codproj INTEGER NOT NULL,
        codkon INTEGER NOT NULL,
        codvuz INTEGER NOT NULL,
        vuz_short_name TEXT NOT NULL,
        grnti_code TEXT NOT NULL,
        plan_fin INTEGER NOT NULL,
        fact_fin INTEGER NOT NULL,
        fin_q1 INTEGER NOT NULL,
        fin_q2 INTEGER NOT NULL,
        fin_q3 INTEGER NOT NULL,
        fin_q4 INTEGER NOT NULL,
        leader_fio TEXT NOT NULL,
        leader_post TEXT,
        leader_rank TEXT,
        leader_degree TEXT,
        proj_name TEXT NOT NULL
    );
    """)

    # Сортируем по конкурсу и коду НИР, чтобы найти дубликат
    df_proj = df_proj.sort_values(by=["codkon", "g1"]).reset_index(drop=True)

    seen_keys = set()
    proj_rows = []

    for _, row in df_proj.iterrows():
        codkon = int(row["codkon"])
        codproj = int(row["g1"])

        # Устранение дубликата по правилу Полотнова: если ключ уже был, ставим MAX + 1 (121)
        if (codkon, codproj) in seen_keys:
            max_in_konk = df_proj[df_proj["codkon"] == codkon]["g1"].max()
            new_codproj = max_in_konk + 1
            print(f"   Устранен дубликат: конкурс {codkon}, проект {codproj} -> изменен на {new_codproj}")
            codproj = new_codproj

        seen_keys.add((codkon, codproj))

        codvuz = int(row["codvuz"])
        # Заполняем краткое название вуза из справочника
        vuz_short = vuz_short_map.get(codvuz, "")

        proj_rows.append((
            codproj,
            codkon,
            codvuz,
            vuz_short,
            str(row["g7"]).strip(),
            int(row["g5"]),
            int(row["g2"]),
            int(row["g21"]),
            int(row["g22"]),
            int(row["g23"]),
            int(row["g24"]),
            str(row["g8"]).strip(),
            str(row.get("g9", "")).strip() if pd.notna(row.get("g9")) else "",
            str(row.get("g10", "")).strip() if pd.notna(row.get("g10")) else "",
            str(row.get("g11", "")).strip() if pd.notna(row.get("g11")) else "",
            str(row["g6"]).strip(),
        ))

    cur.executemany("""
    INSERT INTO gr_proj (
        codproj, codkon, codvuz, vuz_short_name, grnti_code,
        plan_fin, fact_fin, fin_q1, fin_q2, fin_q3, fin_q4,
        leader_fio, leader_post, leader_rank, leader_degree, proj_name
    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?);
    """, proj_rows)
    print(f"   Загружено проектов НИР: {len(proj_rows)}")

    print("3. Загрузка конкурсов (gr_konk.XLS) и расчет показателей...")
    df_konk = pd.read_excel(DATA_DIR / "gr_konk.XLS", sheet_name="gr_konk")

    cur.execute("""
    CREATE TABLE gr_konk (
        codkon INTEGER PRIMARY KEY,
        konk_name TEXT NOT NULL,
        plan_fin INTEGER NOT NULL DEFAULT 0,
        fact_fin INTEGER NOT NULL DEFAULT 0,
        fin_q1 INTEGER NOT NULL DEFAULT 0,
        fin_q2 INTEGER NOT NULL DEFAULT 0,
        fin_q3 INTEGER NOT NULL DEFAULT 0,
        fin_q4 INTEGER NOT NULL DEFAULT 0,
        projects_count INTEGER NOT NULL DEFAULT 0
    );
    """)

    konk_rows = []
    for _, row in df_konk.iterrows():
        codkon = int(row["codkon"])
        name = str(row["k2"]).strip()

        # Считаем количество НИР и плановое финансирование по таблице проектов
        cur.execute("""
        SELECT COUNT(*), COALESCE(SUM(plan_fin), 0)
        FROM gr_proj WHERE codkon = ?;
        """, (codkon,))
        count_nir, plan_sum = cur.fetchone()

        konk_rows.append((codkon, name, plan_sum, 0, 0, 0, 0, 0, count_nir))

    cur.executemany("INSERT INTO gr_konk VALUES (?,?,?,?,?,?,?,?,?);", konk_rows)
    print(f"   Загружено конкурсов: {len(konk_rows)}")

    conn.commit()
    conn.close()
    print("\nБаза данных успешно создана: databases/grants.db")


if __name__ == "__main__":
    clean_and_import_data()
