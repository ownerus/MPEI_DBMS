from pathlib import Path
from PyQt6.QtSql import QSqlDatabase

DB_PATH = Path(__file__).resolve().parent.parent / "databases" / "grants.db"


def connect_db():
    """Подключение к локальной базе данных SQLite для PyQt6."""
    db = QSqlDatabase.addDatabase("QSQLITE")
    db.setDatabaseName(str(DB_PATH))
    if not db.open():
        print(f"Не удалось открыть базу данных: {DB_PATH}")
        return False
    return True
