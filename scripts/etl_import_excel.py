import sqlite3
from pathlib import Path
import pandas as pd
import xlrd

BASE_DIR = Path(__file__).resolve().parent.parent
SOURCES_DIR = BASE_DIR / "Источники" / "файлы данных"
DB_DIR = BASE_DIR / "databases"
DB_PATH = DB_DIR / "grants.db"


def recalculate_competitions(conn: sqlite3.Connection) -> None:
    """Пересчет агрегированных показателей в gr_konk на основе gr_proj."""
    cur = conn.cursor()
    cur.execute("""
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


def init_schema(conn: sqlite3.Connection) -> None:
    """Создание реляционной схемы базы данных."""
    cur = conn.cursor()
    cur.execute("PRAGMA foreign_keys = ON;")

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

    # Первичный логический ключ - (codkon, codproj).
    # Суррогатный id обеспечивает совместимость с QSqlTableModel в PyQt6.
    cur.execute("""
    CREATE TABLE gr_proj (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        codproj INTEGER NOT NULL,
        codkon INTEGER NOT NULL,
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
        UNIQUE (codkon, codproj),
        FOREIGN KEY (codkon) REFERENCES gr_konk(codkon) ON UPDATE CASCADE ON DELETE RESTRICT,
        FOREIGN KEY (codvuz) REFERENCES vuz(codvuz) ON UPDATE CASCADE ON DELETE RESTRICT
    );
    """)

    # Триггеры для гарантированного автоматического поддержания целостности агрегатов gr_konk
    cur.execute("""
    CREATE TRIGGER IF NOT EXISTS trg_proj_insert AFTER INSERT ON gr_proj
    BEGIN
        UPDATE gr_konk
        SET projects_count = (SELECT COUNT(*) FROM gr_proj WHERE codkon = NEW.codkon),
            plan_fin = COALESCE((SELECT SUM(plan_fin) FROM gr_proj WHERE codkon = NEW.codkon), 0),
            fact_fin = COALESCE((SELECT SUM(fact_fin) FROM gr_proj WHERE codkon = NEW.codkon), 0),
            fin_q1 = COALESCE((SELECT SUM(fin_q1) FROM gr_proj WHERE codkon = NEW.codkon), 0),
            fin_q2 = COALESCE((SELECT SUM(fin_q2) FROM gr_proj WHERE codkon = NEW.codkon), 0),
            fin_q3 = COALESCE((SELECT SUM(fin_q3) FROM gr_proj WHERE codkon = NEW.codkon), 0),
            fin_q4 = COALESCE((SELECT SUM(fin_q4) FROM gr_proj WHERE codkon = NEW.codkon), 0)
        WHERE codkon = NEW.codkon;
    END;
    """)

    cur.execute("""
    CREATE TRIGGER IF NOT EXISTS trg_proj_delete AFTER DELETE ON gr_proj
    BEGIN
        UPDATE gr_konk
        SET projects_count = (SELECT COUNT(*) FROM gr_proj WHERE codkon = OLD.codkon),
            plan_fin = COALESCE((SELECT SUM(plan_fin) FROM gr_proj WHERE codkon = OLD.codkon), 0),
            fact_fin = COALESCE((SELECT SUM(fact_fin) FROM gr_proj WHERE codkon = OLD.codkon), 0),
            fin_q1 = COALESCE((SELECT SUM(fin_q1) FROM gr_proj WHERE codkon = OLD.codkon), 0),
            fin_q2 = COALESCE((SELECT SUM(fin_q2) FROM gr_proj WHERE codkon = OLD.codkon), 0),
            fin_q3 = COALESCE((SELECT SUM(fin_q3) FROM gr_proj WHERE codkon = OLD.codkon), 0),
            fin_q4 = COALESCE((SELECT SUM(fin_q4) FROM gr_proj WHERE codkon = OLD.codkon), 0)
        WHERE codkon = OLD.codkon;
    END;
    """)

    cur.execute("""
    CREATE TRIGGER IF NOT EXISTS trg_proj_update AFTER UPDATE ON gr_proj
    BEGIN
        UPDATE gr_konk
        SET projects_count = (SELECT COUNT(*) FROM gr_proj WHERE codkon = NEW.codkon),
            plan_fin = COALESCE((SELECT SUM(plan_fin) FROM gr_proj WHERE codkon = NEW.codkon), 0),
            fact_fin = COALESCE((SELECT SUM(fact_fin) FROM gr_proj WHERE codkon = NEW.codkon), 0),
            fin_q1 = COALESCE((SELECT SUM(fin_q1) FROM gr_proj WHERE codkon = NEW.codkon), 0),
            fin_q2 = COALESCE((SELECT SUM(fin_q2) FROM gr_proj WHERE codkon = NEW.codkon), 0),
            fin_q3 = COALESCE((SELECT SUM(fin_q3) FROM gr_proj WHERE codkon = NEW.codkon), 0),
            fin_q4 = COALESCE((SELECT SUM(fin_q4) FROM gr_proj WHERE codkon = NEW.codkon), 0)
        WHERE codkon = NEW.codkon;

        UPDATE gr_konk
        SET projects_count = (SELECT COUNT(*) FROM gr_proj WHERE codkon = OLD.codkon),
            plan_fin = COALESCE((SELECT SUM(plan_fin) FROM gr_proj WHERE codkon = OLD.codkon), 0),
            fact_fin = COALESCE((SELECT SUM(fact_fin) FROM gr_proj WHERE codkon = OLD.codkon), 0),
            fin_q1 = COALESCE((SELECT SUM(fin_q1) FROM gr_proj WHERE codkon = OLD.codkon), 0),
            fin_q2 = COALESCE((SELECT SUM(fin_q2) FROM gr_proj WHERE codkon = OLD.codkon), 0),
            fin_q3 = COALESCE((SELECT SUM(fin_q3) FROM gr_proj WHERE codkon = OLD.codkon), 0),
            fin_q4 = COALESCE((SELECT SUM(fin_q4) FROM gr_proj WHERE codkon = OLD.codkon), 0)
        WHERE codkon = OLD.codkon AND OLD.codkon != NEW.codkon;
    END;
    """)

    conn.commit()


def import_data(db_path: Path = DB_PATH) -> None:
    """Импорт и очистка данных из исходных файлов Excel в SQLite."""
    DB_DIR.mkdir(parents=True, exist_ok=True)

    vuz_file = SOURCES_DIR / "VUZ.XLS"
    konk_file = SOURCES_DIR / "gr_konk.XLS"
    proj_file = SOURCES_DIR / "Gr_prog.xlsx"

    if not vuz_file.exists():
        raise FileNotFoundError(f"Файл не найден: {vuz_file}")
    if not konk_file.exists():
        raise FileNotFoundError(f"Файл не найден: {konk_file}")
    if not proj_file.exists():
        raise FileNotFoundError(f"Файл не найден: {proj_file}")

    print(f"Инициализация базы данных: {db_path}")
    conn = sqlite3.connect(db_path)
    init_schema(conn)

    # 1. Чтение и нормализация справочника вузов (VUZ.XLS, cp1251)
    wb_vuz = xlrd.open_workbook(vuz_file, encoding_override="cp1251")
    sh_vuz = wb_vuz.sheet_by_index(0)
    vuz_headers = [str(sh_vuz.cell_value(0, c)).strip() for c in range(sh_vuz.ncols)]

    vuz_records = []
    vuz_short_map = {}
    for r in range(1, sh_vuz.nrows):
        row = [sh_vuz.cell_value(r, c) for c in range(sh_vuz.ncols)]
        d = dict(zip(vuz_headers, row))
        # Очистка лидирующих пробелов: пробел незначим, ноль значим
        codvuz = int(str(d["codvuz"]).strip())
        short_name = str(d.get("z2", "")).strip()
        vuz_short_map[codvuz] = short_name

        vuz_records.append({
            "codvuz": codvuz,
            "vuz_name": str(d.get("z1", "")).strip(),
            "vuz_full_name": str(d.get("z1full", "")).strip(),
            "vuz_short_name": short_name,
            "status": str(d.get("status", "")).strip(),
            "city": str(d.get("city", "")).strip(),
            "region": str(d.get("region", "")).strip(),
            "obl_code": str(d.get("obl", "")).strip(),
            "obl_name": str(d.get("oblname", "")).strip(),
            "department": str(d.get("gr_ved", "")).strip(),
            "profile": str(d.get("prof", "")).strip(),
        })

    # 2. Чтение справочника конкурсов (gr_konk.XLS)
    wb_konk = xlrd.open_workbook(konk_file)
    sh_konk = wb_konk.sheet_by_index(0)
    konk_headers = [str(sh_konk.cell_value(0, c)).strip() for c in range(sh_konk.ncols)]

    konk_records = []
    for r in range(1, sh_konk.nrows):
        row = [sh_konk.cell_value(r, c) for c in range(sh_konk.ncols)]
        d = dict(zip(konk_headers, row))
        konk_records.append({
            "codkon": int(d["codkon"]),
            "konk_name": str(d.get("k2", "")).strip(),
            "plan_fin": int(d.get("k12", 0)),
            "fact_fin": int(d.get("k4", 0)),
            "fin_q1": int(d.get("k41", 0)),
            "fin_q2": int(d.get("k42", 0)),
            "fin_q3": int(d.get("k43", 0)),
            "fin_q4": int(d.get("k44", 0)),
            "projects_count": int(d.get("npr", 0)),
        })

    # 3. Чтение проектов НИР (Gr_prog.xlsx) и устранение дубликатов ключа
    df_proj = pd.read_excel(proj_file, sheet_name="Gr_pr")
    # Сортировка по конкурсу и коду НИР per Полотнов
    df_proj = df_proj.sort_values(by=["codkon", "g1"], kind="mergesort")

    # Максимальный код НИР в рамках каждого конкурса
    max_proj_per_konk = df_proj.groupby("codkon")["g1"].max().to_dict()

    seen_keys = set()
    resolved_duplicates = []
    proj_records = []

    def clean_text(val):
        if pd.isna(val):
            return ""
        return str(val).strip()

    for _, row in df_proj.iterrows():
        codkon = int(row["codkon"])
        codproj = int(row["g1"])
        codvuz = int(row["codvuz"])

        # Обнаружение дубликата составного ключа (codkon, codproj)
        if (codkon, codproj) in seen_keys:
            old_codproj = codproj
            # Правило Полотнова: kodkon не меняется, codproj = MAX + 1 в рамках конкурса
            max_proj_per_konk[codkon] += 1
            codproj = max_proj_per_konk[codkon]
            resolved_duplicates.append((codkon, old_codproj, codproj, clean_text(row["g8"])))

        seen_keys.add((codkon, codproj))

        # Денормализация Z2: заполнение аббревиатуры вуза по codvuz
        vuz_short = vuz_short_map.get(codvuz, "")

        proj_records.append({
            "codproj": codproj,
            "codkon": codkon,
            "codvuz": codvuz,
            "vuz_short_name": vuz_short,
            "grnti_code": clean_text(row["g7"]),
            "plan_fin": int(row["g5"]),
            "fact_fin": int(row["g2"]),
            "fin_q1": int(row["g21"]),
            "fin_q2": int(row["g22"]),
            "fin_q3": int(row["g23"]),
            "fin_q4": int(row["g24"]),
            "proj_name": clean_text(row["g6"]),
            "leader_fio": clean_text(row["g8"]),
            "leader_post": clean_text(row["g9"]),
            "leader_rank": clean_text(row["g10"]),
            "leader_degree": clean_text(row["g11"]),
        })

    # Вставка записей в БД
    cur = conn.cursor()
    cur.executemany("""
    INSERT INTO vuz (codvuz, vuz_name, vuz_full_name, vuz_short_name, status, city, region, obl_code, obl_name, department, profile)
    VALUES (:codvuz, :vuz_name, :vuz_full_name, :vuz_short_name, :status, :city, :region, :obl_code, :obl_name, :department, :profile)
    """, vuz_records)

    cur.executemany("""
    INSERT INTO gr_konk (codkon, konk_name, plan_fin, fact_fin, fin_q1, fin_q2, fin_q3, fin_q4, projects_count)
    VALUES (:codkon, :konk_name, :plan_fin, :fact_fin, :fin_q1, :fin_q2, :fin_q3, :fin_q4, :projects_count)
    """, konk_records)

    cur.executemany("""
    INSERT INTO gr_proj (codproj, codkon, codvuz, vuz_short_name, grnti_code, plan_fin, fact_fin, fin_q1, fin_q2, fin_q3, fin_q4, leader_fio, leader_post, leader_rank, leader_degree, proj_name)
    VALUES (:codproj, :codkon, :codvuz, :vuz_short_name, :grnti_code, :plan_fin, :fact_fin, :fin_q1, :fin_q2, :fin_q3, :fin_q4, :leader_fio, :leader_post, :leader_rank, :leader_degree, :proj_name)
    """, proj_records)

    conn.commit()

    # Пересчет агрегатов для gr_konk
    recalculate_competitions(conn)

    print("Импорт завершен успешно:")
    print(f"  Вузов добавлено: {len(vuz_records)}")
    print(f"  Конкурсов добавлено: {len(konk_records)}")
    print(f"  Проектов добавлено: {len(proj_records)}")
    print(f"  Устранено дубликатов ключей: {len(resolved_duplicates)}")
    for d in resolved_duplicates:
        print(f"    Конкурс {d[0]}: код НИР {d[1]} -> {d[2]} (Руководитель: {d[3]})")

    cur.execute("SELECT SUM(projects_count), SUM(plan_fin) FROM gr_konk;")
    total_proj, total_plan = cur.fetchone()
    print(f"  Сводные показатели gr_konk: проектов={total_proj}, плановый бюджет={total_plan:,} руб.")

    conn.close()


if __name__ == "__main__":
    import_data()
