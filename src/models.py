from typing import Optional
from PyQt6.QtCore import Qt, QModelIndex
from PyQt6.QtSql import QSqlDatabase, QSqlTableModel, QSqlQueryModel, QSqlQuery


class FormattedSqlTableModel(QSqlTableModel):
    """Базовый класс для табличных моделей с выравниванием и форматированием чисел."""

    FINANCIAL_COLUMNS = set()

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None

        # Выравнивание чисел по правому краю
        if role == Qt.ItemDataRole.TextAlignmentRole:
            col_name = self.record().fieldName(index.column())
            if col_name in self.FINANCIAL_COLUMNS or col_name.startswith(("cod", "fin_", "plan_", "fact_")):
                return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        # Читаемое представление крупных сумм с разделителями тысяч
        if role == Qt.ItemDataRole.DisplayRole:
            col_name = self.record().fieldName(index.column())
            if col_name in self.FINANCIAL_COLUMNS:
                val = super().data(index, Qt.ItemDataRole.EditRole)
                if val is not None and isinstance(val, (int, float)):
                    return f"{int(val):,}".replace(",", " ")

        return super().data(index, role)

    def select(self) -> bool:
        result = super().select()
        if result:
            while self.canFetchMore():
                self.fetchMore()
        return result


class ProjectsTableModel(FormattedSqlTableModel):
    """Модель данных для таблицы проектов НИР (gr_proj)."""

    FINANCIAL_COLUMNS = {"plan_fin", "fact_fin", "fin_q1", "fin_q2", "fin_q3", "fin_q4"}

    HEADERS = {
        "id": "ID",
        "codproj": "Код НИР",
        "codkon": "Конкурс",
        "codvuz": "Код вуза",
        "vuz_short_name": "Вуз",
        "grnti_code": "ГРНТИ",
        "plan_fin": "План (руб.)",
        "fact_fin": "Факт (руб.)",
        "fin_q1": "1 кв.",
        "fin_q2": "2 кв.",
        "fin_q3": "3 кв.",
        "fin_q4": "4 кв.",
        "leader_fio": "Руководитель",
        "leader_post": "Должность",
        "leader_rank": "Звание",
        "leader_degree": "Степень",
        "proj_name": "Тема НИР",
    }

    def __init__(self, db: QSqlDatabase, parent=None):
        super().__init__(parent=parent, db=db)
        self.setTable("gr_proj")
        self.setEditStrategy(QSqlTableModel.EditStrategy.OnFieldChange)
        self.apply_headers()
        self.select()

    def apply_headers(self) -> None:
        record = self.record()
        for col_idx in range(record.count()):
            field_name = record.fieldName(col_idx)
            header_text = self.HEADERS.get(field_name, field_name)
            self.setHeaderData(col_idx, Qt.Orientation.Horizontal, header_text)

    def apply_filter(self, search_text: str = "", codkon: Optional[int] = None) -> None:
        filters = []
        if codkon is not None and codkon > 0:
            filters.append(f"codkon = {codkon}")
        if search_text:
            escaped = search_text.replace("'", "''").strip()
            variants = {escaped, escaped.lower(), escaped.upper(), escaped.capitalize(), escaped.title()}
            var_filters = []
            for v in variants:
                var_filters.append(
                    f"(proj_name LIKE '%{v}%' OR "
                    f"leader_fio LIKE '%{v}%' OR "
                    f"vuz_short_name LIKE '%{v}%' OR "
                    f"grnti_code LIKE '%{v}%' OR "
                    f"CAST(codproj AS TEXT) LIKE '%{v}%' OR "
                    f"CAST(codvuz AS TEXT) LIKE '%{v}%')"
                )
            filters.append(f"({' OR '.join(var_filters)})")

        self.setFilter(" AND ".join(filters))
        self.select()


class CompetitionsTableModel(FormattedSqlTableModel):
    """Модель данных для таблицы конкурсов (gr_konk)."""

    FINANCIAL_COLUMNS = {"plan_fin", "fact_fin", "fin_q1", "fin_q2", "fin_q3", "fin_q4"}

    HEADERS = {
        "codkon": "Код",
        "konk_name": "Наименование конкурса",
        "plan_fin": "План (руб.)",
        "fact_fin": "Факт (руб.)",
        "fin_q1": "1 кв.",
        "fin_q2": "2 кв.",
        "fin_q3": "3 кв.",
        "fin_q4": "4 кв.",
        "projects_count": "НИР",
    }

    def __init__(self, db: QSqlDatabase, parent=None):
        super().__init__(parent=parent, db=db)
        self.setTable("gr_konk")
        self.setEditStrategy(QSqlTableModel.EditStrategy.OnFieldChange)
        self.apply_headers()
        self.select()

    def apply_headers(self) -> None:
        record = self.record()
        for col_idx in range(record.count()):
            field_name = record.fieldName(col_idx)
            header_text = self.HEADERS.get(field_name, field_name)
            self.setHeaderData(col_idx, Qt.Orientation.Horizontal, header_text)

    def apply_filter(self, search_text: str = "") -> None:
        if search_text:
            escaped = search_text.replace("'", "''").strip()
            variants = {escaped, escaped.lower(), escaped.upper(), escaped.capitalize(), escaped.title()}
            var_filters = []
            for v in variants:
                var_filters.append(
                    f"(konk_name LIKE '%{v}%' OR CAST(codkon AS TEXT) LIKE '%{v}%')"
                )
            self.setFilter(" OR ".join(var_filters))
        else:
            self.setFilter("")
        self.select()


class UniversitiesTableModel(FormattedSqlTableModel):
    """Модель данных для справочника вузов (vuz)."""

    HEADERS = {
        "codvuz": "Код",
        "vuz_name": "Наименование",
        "vuz_full_name": "Полное наименование",
        "vuz_short_name": "Аббревиатура",
        "status": "Статус",
        "city": "Город",
        "region": "Фед. округ",
        "obl_code": "Код суб.",
        "obl_name": "Субъект РФ",
        "department": "Ведомство",
        "profile": "Профиль",
    }

    def __init__(self, db: QSqlDatabase, parent=None):
        super().__init__(parent=parent, db=db)
        self.setTable("vuz")
        self.setEditStrategy(QSqlTableModel.EditStrategy.OnFieldChange)
        self.apply_headers()
        self.select()

    def apply_headers(self) -> None:
        record = self.record()
        for col_idx in range(record.count()):
            field_name = record.fieldName(col_idx)
            header_text = self.HEADERS.get(field_name, field_name)
            self.setHeaderData(col_idx, Qt.Orientation.Horizontal, header_text)

    def apply_filter(self, search_text: str = "") -> None:
        if search_text:
            escaped = search_text.replace("'", "''").strip()
            variants = {escaped, escaped.lower(), escaped.upper(), escaped.capitalize(), escaped.title()}
            var_filters = []
            for v in variants:
                var_filters.append(
                    f"(vuz_name LIKE '%{v}%' OR "
                    f"vuz_short_name LIKE '%{v}%' OR "
                    f"city LIKE '%{v}%' OR "
                    f"region LIKE '%{v}%' OR "
                    f"CAST(codvuz AS TEXT) LIKE '%{v}%' OR "
                    f"obl_code LIKE '%{v}%')"
                )
            self.setFilter(" OR ".join(var_filters))
        else:
            self.setFilter("")
        self.select()


class AnalysisQueryModel(QSqlQueryModel):
    """Модель для аналитических сводных запросов."""

    def __init__(self, query_str: str, headers: list[str], db: QSqlDatabase, parent=None):
        super().__init__(parent=parent)
        self.setQuery(QSqlQuery(query_str, db))
        for col_idx, header in enumerate(headers):
            self.setHeaderData(col_idx, Qt.Orientation.Horizontal, header)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None

        # Выравнивание чисел в аналитических отчетах
        if role == Qt.ItemDataRole.TextAlignmentRole:
            val = super().data(index, Qt.ItemDataRole.DisplayRole)
            if isinstance(val, (int, float)) or (isinstance(val, str) and val.replace(" ", "").isdigit()):
                return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        if role == Qt.ItemDataRole.DisplayRole:
            val = super().data(index, role)
            if isinstance(val, int) and val >= 10000:
                return f"{val:,}".replace(",", " ")

        return super().data(index, role)


def get_vuz_distribution_model(db: QSqlDatabase, parent=None) -> AnalysisQueryModel:
    """Сводка распределения НИР по вузам."""
    sql = """
    SELECT 
        v.vuz_short_name,
        v.city,
        COUNT(p.id) AS proj_cnt,
        SUM(p.plan_fin) AS total_plan,
        SUM(p.fact_fin) AS total_fact
    FROM gr_proj p
    JOIN vuz v ON p.codvuz = v.codvuz
    GROUP BY v.codvuz, v.vuz_short_name, v.city
    ORDER BY proj_cnt DESC, total_plan DESC;
    """
    headers = ["Вуз", "Город", "Кол-во проектов", "План (руб.)", "Факт (руб.)"]
    return AnalysisQueryModel(sql, headers, db, parent)


def get_konk_distribution_model(db: QSqlDatabase, parent=None) -> AnalysisQueryModel:
    """Сводка распределения НИР по конкурсам."""
    sql = """
    SELECT 
        codkon,
        konk_name,
        projects_count,
        plan_fin,
        fact_fin,
        ROUND(CAST(plan_fin AS FLOAT) / CASE WHEN projects_count = 0 THEN 1 ELSE projects_count END, 0) AS avg_grant
    FROM gr_konk
    ORDER BY codkon;
    """
    headers = ["Код", "Конкурс", "Проектов", "План (руб.)", "Факт (руб.)", "Средний грант (руб.)"]
    return AnalysisQueryModel(sql, headers, db, parent)


def get_region_distribution_model(db: QSqlDatabase, parent=None) -> AnalysisQueryModel:
    """Сводка распределения НИР по регионам (федеральным округам)."""
    sql = """
    SELECT 
        COALESCE(NULLIF(v.region, ''), 'Не указан') AS region_name,
        COUNT(DISTINCT v.codvuz) AS vuz_cnt,
        COUNT(p.id) AS proj_cnt,
        SUM(p.plan_fin) AS total_plan
    FROM gr_proj p
    JOIN vuz v ON p.codvuz = v.codvuz
    GROUP BY region_name
    ORDER BY proj_cnt DESC;
    """
    headers = ["Федеральный округ", "Вузов-участников", "Кол-во проектов", "План (руб.)"]
    return AnalysisQueryModel(sql, headers, db, parent)


def get_vuz_funding_statement_model(db: QSqlDatabase, parent=None) -> AnalysisQueryModel:
    """Сводная ведомость поквартального финансирования НИР по вузам."""
    sql = """
    SELECT 
        v.codvuz,
        v.vuz_short_name,
        v.city,
        COUNT(p.id) AS proj_cnt,
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
    """
    headers = [
        "Код вуза", "Вуз", "Город", "Проектов",
        "План (руб.)", "Факт (руб.)",
        "1 кв. (руб.)", "2 кв. (руб.)", "3 кв. (руб.)", "4 кв. (руб.)"
    ]
    return AnalysisQueryModel(sql, headers, db, parent)

