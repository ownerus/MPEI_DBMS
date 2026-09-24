import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts.migrate_project_keys import migrate, repair_duplicate_keys
from src.project_keys import add_project


DB_PATH = Path(__file__).resolve().parent.parent / "databases" / "grants.db"


class ProjectKeyTests(unittest.TestCase):
    def test_legacy_duplicates_take_max_plus_one_within_contest(self):
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE gr_proj (id INTEGER PRIMARY KEY, codkon INTEGER, codproj INTEGER)")
        conn.executemany(
            "INSERT INTO gr_proj VALUES (?, ?, ?)",
            [(1, 1, 2), (2, 1, 2), (3, 1, 5), (4, 7, 2), (5, 7, 2)],
        )
        self.assertEqual(repair_duplicate_keys(conn), [(1, 2, 6), (7, 2, 3)])
        self.assertEqual(
            conn.execute("SELECT codkon, codproj FROM gr_proj ORDER BY id").fetchall(),
            [(1, 2), (1, 6), (1, 5), (7, 2), (7, 3)],
        )
        conn.close()

    def test_migration_and_new_project_keep_keys_and_totals_consistent(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Path(folder) / "grants.db"
            shutil.copy2(DB_PATH, db)
            migrate(db)
            conn = sqlite3.connect(db)
            conn.execute("PRAGMA foreign_keys = ON")

            pk = sorted(
                (row[5], row[1]) for row in conn.execute("PRAGMA table_info(gr_proj)") if row[5]
            )
            self.assertEqual(pk, [(1, "codkon"), (2, "codproj")])
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM gr_proj").fetchone()[0], 400)
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    "UPDATE gr_proj SET codproj = 2 WHERE codkon = 1 AND codproj = 121"
                )
            conn.rollback()
            self.assertEqual(
                conn.execute("SELECT codproj FROM gr_proj WHERE codkon = 1 AND proj_name LIKE 'Разработка методов упрочнения материалов%' ").fetchone()[0],
                121,
            )
            self.assertEqual(
                conn.execute("SELECT codproj FROM gr_proj WHERE codkon = 7 AND proj_name LIKE 'Природа стеклообразного состояния%' ").fetchone()[0],
                471,
            )

            before = conn.execute(
                "SELECT projects_count, plan_fin FROM gr_konk WHERE codkon = 1"
            ).fetchone()
            code = add_project(conn, {
                "codkon": 1,
                "codproj": 2,
                "codvuz": 53,
                "grnti_code": "55.22.01",
                "plan_fin": 100,
                "leader_fio": "Тестовый руководитель",
                "proj_name": "Тестовый проект",
            })
            self.assertEqual(code, 122)
            self.assertEqual(
                conn.execute("SELECT projects_count, plan_fin FROM gr_konk WHERE codkon = 1").fetchone(),
                (before[0] + 1, before[1] + 100),
            )
            self.assertEqual(
                conn.execute("SELECT vuz_short_name FROM gr_proj WHERE codkon = 1 AND codproj = 122").fetchone()[0],
                conn.execute("SELECT vuz_short_name FROM vuz WHERE codvuz = 53").fetchone()[0],
            )

            conn.execute("UPDATE gr_proj SET codkon = 2, plan_fin = 150 WHERE codkon = 1 AND codproj = 122")
            self.assertEqual(
                conn.execute("SELECT projects_count, plan_fin FROM gr_konk WHERE codkon = 1").fetchone(),
                before,
            )
            conn.execute("DELETE FROM gr_proj WHERE codkon = 2 AND codproj = 122")
            conn.commit()
            self.assertEqual(conn.execute("PRAGMA foreign_key_check").fetchall(), [])
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM gr_proj GROUP BY codkon, codproj HAVING COUNT(*) > 1").fetchall(),
                [],
            )
            conn.close()


if __name__ == "__main__":
    unittest.main()
