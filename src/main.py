from pathlib import Path
import re
import sys
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PyQt6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHeaderView,
    QInputDialog,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QSpinBox,
    QTableView,
    QTextEdit,
    QVBoxLayout,
)

from src.database import get_db_path, get_sqlite_connection, init_connection, recalculate_gr_konk
from src.models import (
    CompetitionsTableModel,
    ProjectsTableModel,
    UniversitiesTableModel,
    get_konk_distribution_model,
    get_region_distribution_model,
    get_vuz_distribution_model,
    get_vuz_funding_statement_model,
)
from src.reports import apply_funding_order, reset_funding
from src.ui.main_window_ui import Ui_MainWindow


class ProjectEditDialog(QDialog):
    """Диалог добавления и редактирования записи НИР."""

    GRNTI_PATTERN = re.compile(r"^\s*\d{2}(?:\.\d{2}){1,2}(?:\s*[,;]\s*\d{2}(?:\.\d{2}){1,2})*\s*$")

    def __init__(self, db_path: Path, project_id: Optional[int] = None, parent=None):
        super().__init__(parent)
        self.db_path = db_path
        self.project_id = project_id
        self.setWindowTitle("Редактирование проекта НИР" if project_id else "Новый проект НИР")
        self.setMinimumWidth(560)

        self._build_ui()
        self._load_combos()
        if project_id:
            self._load_project_data(project_id)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.combo_konk = QComboBox()
        self.combo_vuz = QComboBox()
        self.edit_grnti = QLineEdit()
        self.edit_grnti.setPlaceholderText("Например: 55.35.41")
        self.spin_plan = QSpinBox()
        self.spin_plan.setRange(0, 100_000_000)
        self.spin_plan.setSingleStep(50_000)
        self.spin_plan.setValue(500_000)
        self.spin_plan.setSuffix(" руб.")

        self.edit_fio = QLineEdit()
        self.edit_post = QLineEdit()
        self.edit_rank = QLineEdit()
        self.edit_degree = QLineEdit()
        self.text_title = QTextEdit()
        self.text_title.setMaximumHeight(80)

        form.addRow("Конкурс:", self.combo_konk)
        form.addRow("Вуз-исполнитель:", self.combo_vuz)
        form.addRow("Код ГРНТИ:", self.edit_grnti)
        form.addRow("План финансирования:", self.spin_plan)
        form.addRow("Руководитель (ФИО):", self.edit_fio)
        form.addRow("Должность:", self.edit_post)
        form.addRow("Ученое звание:", self.edit_rank)
        form.addRow("Ученая степень:", self.edit_degree)
        form.addRow("Тема НИР:", self.text_title)

        layout.addLayout(form)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.accepted.connect(self._validate_and_accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def _load_combos(self) -> None:
        conn = get_sqlite_connection(self.db_path)
        cur = conn.cursor()

        cur.execute("SELECT codkon, konk_name FROM gr_konk ORDER BY codkon;")
        for row in cur.fetchall():
            self.combo_konk.addItem(f"{row['codkon']} — {row['konk_name']}", row["codkon"])

        cur.execute("SELECT codvuz, vuz_short_name, city FROM vuz ORDER BY vuz_short_name;")
        for row in cur.fetchall():
            label = f"{row['vuz_short_name']} ({row['city']}, код {row['codvuz']})"
            self.combo_vuz.addItem(label, (row["codvuz"], row["vuz_short_name"]))

        conn.close()

    def _load_project_data(self, project_id: int) -> None:
        conn = get_sqlite_connection(self.db_path)
        cur = conn.cursor()
        cur.execute("""
        SELECT codkon, codvuz, grnti_code, plan_fin, leader_fio, leader_post,
               leader_rank, leader_degree, proj_name
        FROM gr_proj
        WHERE id = ?;
        """, (project_id,))
        row = cur.fetchone()
        conn.close()

        if not row:
            return

        for idx in range(self.combo_konk.count()):
            if self.combo_konk.itemData(idx) == row["codkon"]:
                self.combo_konk.setCurrentIndex(idx)
                break

        for idx in range(self.combo_vuz.count()):
            vuz_data = self.combo_vuz.itemData(idx)
            if vuz_data and vuz_data[0] == row["codvuz"]:
                self.combo_vuz.setCurrentIndex(idx)
                break

        self.edit_grnti.setText(row["grnti_code"] or "")
        self.spin_plan.setValue(int(row["plan_fin"] or 0))
        self.edit_fio.setText(row["leader_fio"] or "")
        self.edit_post.setText(row["leader_post"] or "")
        self.edit_rank.setText(row["leader_rank"] or "")
        self.edit_degree.setText(row["leader_degree"] or "")
        self.text_title.setPlainText(row["proj_name"] or "")

    def _validate_and_accept(self) -> None:
        if self.combo_konk.currentData() is None:
            QMessageBox.warning(self, "Ошибка", "Выберите конкурс из списка.")
            return

        if self.combo_vuz.currentData() is None:
            QMessageBox.warning(self, "Ошибка", "Выберите вуз из списка.")
            return

        fio = self.edit_fio.text().strip()
        title = self.text_title.toPlainText().strip()
        grnti = self.edit_grnti.text().strip()

        if not fio:
            QMessageBox.warning(self, "Ошибка", "Укажите ФИО руководителя НИР.")
            self.edit_fio.setFocus()
            return
        if not title:
            QMessageBox.warning(self, "Ошибка", "Укажите тему проекта НИР.")
            self.text_title.setFocus()
            return
        if not grnti:
            QMessageBox.warning(self, "Ошибка", "Укажите код тематики по рубрикатору ГРНТИ.")
            self.edit_grnti.setFocus()
            return
        if not self.GRNTI_PATTERN.match(grnti):
            QMessageBox.warning(
                self,
                "Ошибка формата ГРНТИ",
                "Код рубрикатора ГРНТИ должен иметь формат XX.YY.ZZ или XX.YY "
                "(допускается перечисление кодов через запятую).\n"
                "Пример: 55.35.41"
            )
            self.edit_grnti.setFocus()
            return

        self.accept()

    def get_data(self) -> dict:
        vuz_info = self.combo_vuz.currentData() or (0, "")
        return {
            "codkon": self.combo_konk.currentData(),
            "codvuz": vuz_info[0],
            "vuz_short_name": vuz_info[1],
            "grnti_code": self.edit_grnti.text().strip(),
            "plan_fin": self.spin_plan.value(),
            "leader_fio": self.edit_fio.text().strip(),
            "leader_post": self.edit_post.text().strip(),
            "leader_rank": self.edit_rank.text().strip(),
            "leader_degree": self.edit_degree.text().strip(),
            "proj_name": self.text_title.toPlainText().strip(),
        }


class ReportViewerDialog(QDialog):
    """Окно просмотра сводных аналитических отчетов."""

    def __init__(self, title: str, model, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(850, 500)

        layout = QVBoxLayout(self)
        self.view = QTableView()
        self.view.setModel(model)
        self.view.setAlternatingRowColors(True)
        self.view.setSortingEnabled(True)
        self.view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.view.horizontalHeader().setStretchLastSection(True)

        layout.addWidget(self.view)

        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btn_box.rejected.connect(self.close)
        layout.addWidget(btn_box)


class MainWindow(QMainWindow):
    """Главное окно приложения сопровождения грантов."""

    def __init__(self, db_path: Path):
        super().__init__()
        self.db_path = db_path
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)

        self.db = init_connection(self.db_path)

        # Модели таблиц
        self.model_projects = ProjectsTableModel(self.db, parent=self)
        self.model_competitions = CompetitionsTableModel(self.db, parent=self)
        self.model_universities = UniversitiesTableModel(self.db, parent=self)

        self.current_table = "projects"

        # Защита от случайного редактирования ячеек напрямую в таблице (без валидации)
        self.ui.tableView.setEditTriggers(QTableView.EditTrigger.NoEditTriggers)

        self._init_nav_buttons()
        self._init_competition_filter()
        self._connect_signals()

        # Стартовое отображение таблицы проектов
        self.show_projects_view()

    def _init_nav_buttons(self) -> None:
        self.nav_group = QButtonGroup(self)
        self.nav_group.addButton(self.ui.btnNavProjects, 0)
        self.nav_group.addButton(self.ui.btnNavCompetitions, 1)
        self.nav_group.addButton(self.ui.btnNavUniversities, 2)
        self.nav_group.setExclusive(True)

    def _init_competition_filter(self) -> None:
        self.ui.comboKonkFilter.addItem("Все конкурсы (1-17)", 0)
        conn = get_sqlite_connection(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT codkon, konk_name FROM gr_konk ORDER BY codkon;")
        for row in cur.fetchall():
            self.ui.comboKonkFilter.addItem(
                f"{row['codkon']} — {row['konk_name']}", row["codkon"]
            )
        conn.close()

    def _connect_signals(self) -> None:
        # Переключение разделов данных через кнопки
        self.ui.btnNavProjects.clicked.connect(self.show_projects_view)
        self.ui.btnNavCompetitions.clicked.connect(self.show_competitions_view)
        self.ui.btnNavUniversities.clicked.connect(self.show_universities_view)

        # Меню "Данные"
        self.ui.actionProjects.triggered.connect(self.show_projects_view)
        self.ui.actionCompetitions.triggered.connect(self.show_competitions_view)
        self.ui.actionUniversities.triggered.connect(self.show_universities_view)

        # Меню "Анализ"
        self.ui.actionAnalysisVuz.triggered.connect(self.show_vuz_analysis)
        self.ui.actionAnalysisKonk.triggered.connect(self.show_konk_analysis)
        self.ui.actionAnalysisRegion.triggered.connect(self.show_region_analysis)

        # Меню "Финансирование"
        self.ui.actionFundingOrder.triggered.connect(self.execute_funding_order)
        self.ui.actionFundingStatement.triggered.connect(self.show_funding_statement)
        self.ui.actionResetFunding.triggered.connect(self.reset_all_funding)

        # Меню "Справка" и "Выход"
        self.ui.actionAbout.triggered.connect(self.show_about_dialog)
        self.ui.actionExit.triggered.connect(self.close)

        # Фильтрация и поиск
        self.ui.btnFilter.clicked.connect(self.apply_filter)
        self.ui.editSearch.returnPressed.connect(self.apply_filter)
        self.ui.btnReset.clicked.connect(self.reset_filter)
        self.ui.comboKonkFilter.currentIndexChanged.connect(self.apply_filter)

        # Переключение детализации полей
        self.ui.chkDetailedFields.toggled.connect(self._on_detailed_fields_toggled)

        # CRUD операции
        self.ui.btnAdd.clicked.connect(self.add_record)
        self.ui.btnEdit.clicked.connect(self.edit_record)
        self.ui.btnDelete.clicked.connect(self.delete_record)
        self.ui.btnRecalculate.clicked.connect(self.recalculate_data)

        # Двойной клик по строке открывает диалог редактирования
        self.ui.tableView.doubleClicked.connect(self._on_table_double_clicked)

    def _on_table_double_clicked(self) -> None:
        if self.current_table == "projects":
            self.edit_record()

    def _on_detailed_fields_toggled(self, _checked: bool) -> None:
        if self.current_table == "projects":
            self.show_projects_view()

    def show_projects_view(self) -> None:
        self.current_table = "projects"
        self.ui.btnNavProjects.setChecked(True)
        self.ui.tableView.setModel(self.model_projects)

        # Сначала отображаем все столбцы модели
        for col in range(self.model_projects.columnCount()):
            self.ui.tableView.showColumn(col)

        # Скрываем суррогатный id (колонка 0)
        self.ui.tableView.hideColumn(0)

        # Если детальный режим выключен, скрываем вторичные колонки (кварталы и звания),
        # оставляя 9 ключевых колонок per Полотнов для просмотра без горизонтального скролла
        if not self.ui.chkDetailedFields.isChecked():
            for col in (8, 9, 10, 11, 13, 14, 15):
                self.ui.tableView.hideColumn(col)

        header = self.ui.tableView.horizontalHeader()
        for col in range(1, 16):
            if not self.ui.tableView.isColumnHidden(col):
                header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(16, QHeaderView.ResizeMode.Stretch)

        self.ui.lblKonkFilter.show()
        self.ui.comboKonkFilter.show()
        self.ui.chkDetailedFields.show()
        self.ui.btnAdd.setEnabled(True)
        self.ui.btnEdit.setEnabled(True)
        self.ui.btnDelete.setEnabled(True)

        self._update_stats_label()

    def show_competitions_view(self) -> None:
        self.current_table = "competitions"
        self.ui.btnNavCompetitions.setChecked(True)
        self.ui.tableView.setModel(self.model_competitions)

        # Восстанавливаем видимость всех столбцов
        for col in range(self.model_competitions.columnCount()):
            self.ui.tableView.showColumn(col)

        header = self.ui.tableView.horizontalHeader()
        for col in range(self.model_competitions.columnCount()):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

        self.ui.lblKonkFilter.hide()
        self.ui.comboKonkFilter.hide()
        self.ui.chkDetailedFields.hide()
        self.ui.btnAdd.setEnabled(False)
        self.ui.btnEdit.setEnabled(False)
        self.ui.btnDelete.setEnabled(False)

        self._update_stats_label()

    def show_universities_view(self) -> None:
        self.current_table = "universities"
        self.ui.btnNavUniversities.setChecked(True)
        self.ui.tableView.setModel(self.model_universities)

        # Восстанавливаем видимость всех столбцов
        for col in range(self.model_universities.columnCount()):
            self.ui.tableView.showColumn(col)

        header = self.ui.tableView.horizontalHeader()
        for col in range(self.model_universities.columnCount()):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)

        self.ui.lblKonkFilter.hide()
        self.ui.comboKonkFilter.hide()
        self.ui.chkDetailedFields.hide()
        self.ui.btnAdd.setEnabled(False)
        self.ui.btnEdit.setEnabled(False)
        self.ui.btnDelete.setEnabled(False)

        self._update_stats_label()

    def apply_filter(self) -> None:
        search_text = self.ui.editSearch.text().strip()
        if self.current_table == "projects":
            codkon = self.ui.comboKonkFilter.currentData()
            self.model_projects.apply_filter(search_text, codkon)
        elif self.current_table == "competitions":
            self.model_competitions.apply_filter(search_text)
        elif self.current_table == "universities":
            self.model_universities.apply_filter(search_text)

        self._update_stats_label()

    def reset_filter(self) -> None:
        self.ui.editSearch.clear()
        self.ui.comboKonkFilter.setCurrentIndex(0)
        if self.current_table == "projects":
            self.model_projects.apply_filter("", 0)
        elif self.current_table == "competitions":
            self.model_competitions.apply_filter("")
        elif self.current_table == "universities":
            self.model_universities.apply_filter("")

        self._update_stats_label()

    def _update_stats_label(self) -> None:
        if self.current_table == "projects":
            cnt = self.model_projects.rowCount()
            flt = self.model_projects.filter()
            conn = get_sqlite_connection(self.db_path)
            cur = conn.cursor()
            sql = "SELECT COALESCE(SUM(plan_fin), 0), COALESCE(SUM(fact_fin), 0) FROM gr_proj"
            if flt:
                sql += f" WHERE {flt}"
            cur.execute(sql)
            total_plan, total_fact = cur.fetchone()
            conn.close()
            plan_str = f"{total_plan:,}".replace(",", " ")
            fact_str = f"{total_fact:,}".replace(",", " ")
            self.ui.lblStats.setText(
                f"Отобрано проектов: {cnt} | План: {plan_str} руб. | Факт: {fact_str} руб."
            )
        elif self.current_table == "competitions":
            cnt = self.model_competitions.rowCount()
            flt = self.model_competitions.filter()
            conn = get_sqlite_connection(self.db_path)
            cur = conn.cursor()
            sql = "SELECT COALESCE(SUM(plan_fin), 0), COALESCE(SUM(fact_fin), 0) FROM gr_konk"
            if flt:
                sql += f" WHERE {flt}"
            cur.execute(sql)
            total_plan, total_fact = cur.fetchone()
            conn.close()
            plan_str = f"{total_plan:,}".replace(",", " ")
            fact_str = f"{total_fact:,}".replace(",", " ")
            self.ui.lblStats.setText(
                f"Отобрано конкурсов: {cnt} | План: {plan_str} руб. | Факт: {fact_str} руб."
            )
        elif self.current_table == "universities":
            cnt = self.model_universities.rowCount()
            self.ui.lblStats.setText(f"Всего вузов в справочнике: {cnt}")

    def add_record(self) -> None:
        if self.current_table != "projects":
            return

        dialog = ProjectEditDialog(self.db_path, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            data = dialog.get_data()
            try:
                conn = get_sqlite_connection(self.db_path)
                cur = conn.cursor()

                # Правило Полотнова: номер нового проекта = MAX + 1 внутри выбранного конкурса
                cur.execute("SELECT COALESCE(MAX(codproj), 0) FROM gr_proj WHERE codkon = ?;", (data["codkon"],))
                max_codproj = cur.fetchone()[0]
                new_codproj = max_codproj + 1

                cur.execute("""
                INSERT INTO gr_proj (
                    codproj, codkon, codvuz, vuz_short_name, grnti_code, plan_fin,
                    fact_fin, fin_q1, fin_q2, fin_q3, fin_q4, leader_fio, leader_post,
                    leader_rank, leader_degree, proj_name
                ) VALUES (?, ?, ?, ?, ?, ?, 0, 0, 0, 0, 0, ?, ?, ?, ?, ?);
                """, (
                    new_codproj,
                    data["codkon"],
                    data["codvuz"],
                    data["vuz_short_name"],
                    data["grnti_code"],
                    data["plan_fin"],
                    data["leader_fio"],
                    data["leader_post"],
                    data["leader_rank"],
                    data["leader_degree"],
                    data["proj_name"],
                ))
                conn.commit()
                conn.close()

                # Автоматический пересчет таблицы конкурсов
                recalculate_gr_konk(self.db_path)
                self.model_projects.select()
                self.model_competitions.select()
                self._update_stats_label()

                self.ui.statusbar.showMessage(
                    f"Добавлен проект №{new_codproj} в конкурс №{data['codkon']}", 5000
                )
            except Exception as e:
                QMessageBox.critical(self, "Ошибка добавления", f"Не удалось добавить проект: {e}")

    def edit_record(self) -> None:
        if self.current_table != "projects":
            return

        idx = self.ui.tableView.currentIndex()
        if not idx.isValid():
            QMessageBox.information(self, "Выбор записи", "Выберите строку проекта для редактирования.")
            return

        row = idx.row()
        project_id = self.model_projects.data(self.model_projects.index(row, 0))
        if project_id is None:
            return

        dialog = ProjectEditDialog(self.db_path, project_id=project_id, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            data = dialog.get_data()
            try:
                conn = get_sqlite_connection(self.db_path)
                cur = conn.cursor()
                cur.execute("SELECT codkon, codproj FROM gr_proj WHERE id = ?;", (project_id,))
                orig_row = cur.fetchone()
                old_codkon = orig_row[0]
                codproj = orig_row[1]

                msg_extra = ""
                # Если конкурс был изменен, переназначаем codproj = MAX + 1 для целевого конкурса (Полотнов)
                if data["codkon"] != old_codkon:
                    cur.execute("SELECT COALESCE(MAX(codproj), 0) FROM gr_proj WHERE codkon = ?;", (data["codkon"],))
                    codproj = cur.fetchone()[0] + 1
                    msg_extra = f" (перемещен из конкурса {old_codkon} в конкурс {data['codkon']} с кодом №{codproj})"

                cur.execute("""
                UPDATE gr_proj
                SET codproj = ?, codkon = ?, codvuz = ?, vuz_short_name = ?, grnti_code = ?,
                    plan_fin = ?, leader_fio = ?, leader_post = ?, leader_rank = ?,
                    leader_degree = ?, proj_name = ?
                WHERE id = ?;
                """, (
                    codproj,
                    data["codkon"],
                    data["codvuz"],
                    data["vuz_short_name"],
                    data["grnti_code"],
                    data["plan_fin"],
                    data["leader_fio"],
                    data["leader_post"],
                    data["leader_rank"],
                    data["leader_degree"],
                    data["proj_name"],
                    project_id,
                ))
                conn.commit()
                conn.close()

                recalculate_gr_konk(self.db_path)
                self.model_projects.select()
                self.model_competitions.select()
                self._update_stats_label()
                self.ui.statusbar.showMessage(f"Данные проекта успешно обновлены{msg_extra}", 4000)
            except Exception as e:
                QMessageBox.critical(self, "Ошибка обновления", f"Не удалось обновить проект: {e}")

    def delete_record(self) -> None:
        if self.current_table != "projects":
            return

        idx = self.ui.tableView.currentIndex()
        if not idx.isValid():
            QMessageBox.information(self, "Выбор записи", "Выберите строку проекта для удаления.")
            return

        row = idx.row()
        project_id = self.model_projects.data(self.model_projects.index(row, 0))
        proj_code = self.model_projects.data(self.model_projects.index(row, 1))
        konk_code = self.model_projects.data(self.model_projects.index(row, 2))

        ans = QMessageBox.question(
            self,
            "Подтверждение удаления",
            f"Вы действительно хотите удалить проект №{proj_code} из конкурса №{konk_code}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if ans == QMessageBox.StandardButton.Yes:
            try:
                conn = get_sqlite_connection(self.db_path)
                cur = conn.cursor()
                cur.execute("DELETE FROM gr_proj WHERE id = ?;", (project_id,))
                conn.commit()
                conn.close()

                recalculate_gr_konk(self.db_path)
                self.model_projects.select()
                self.model_competitions.select()
                self._update_stats_label()
                self.ui.statusbar.showMessage("Проект удален, сводные данные пересчитаны", 4000)
            except Exception as e:
                QMessageBox.critical(self, "Ошибка удаления", f"Не удалось удалить проект: {e}")

    def recalculate_data(self) -> None:
        recalculate_gr_konk(self.db_path)
        self.model_competitions.select()
        self.model_projects.select()
        self._update_stats_label()
        self.ui.statusbar.showMessage("Агрегированные данные конкурсов успешно пересчитаны", 4000)

    def execute_funding_order(self) -> None:
        percent, ok = QInputDialog.getInt(
            self,
            "Распоряжение о финансировании",
            "Укажите процент финансирования от плана (1–100%):",
            100, 1, 100, 5
        )
        if not ok:
            return

        try:
            res = apply_funding_order(percent=float(percent), db_path=self.db_path)
            self.model_projects.select()
            self.model_competitions.select()
            self._update_stats_label()

            allocated_str = f"{res['total_allocated']:,}".replace(",", " ")
            QMessageBox.information(
                self,
                "Распоряжение о финансировании",
                f"Выпущено распоряжение о {percent}% финансировании грантов.\n\n"
                f"Обновлено проектов: {res['projects_updated']}\n"
                f"Распределено средств: {allocated_str} руб.\n\n"
                f"Таблица конкурсов автоматически пересчитана.",
            )
        except Exception as e:
            QMessageBox.critical(self, "Ошибка финансирования", f"Ошибка выпуска распоряжения: {e}")

    def reset_all_funding(self) -> None:
        ans = QMessageBox.question(
            self,
            "Сброс финансирования",
            "Обнулить фактическое и поквартальное финансирование всех НИР?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if ans == QMessageBox.StandardButton.Yes:
            reset_funding(self.db_path)
            self.model_projects.select()
            self.model_competitions.select()
            self._update_stats_label()
            self.ui.statusbar.showMessage("Финансирование сброшено в ноль", 4000)

    def show_vuz_analysis(self) -> None:
        model = get_vuz_distribution_model(self.db, parent=self)
        dlg = ReportViewerDialog("Анализ: Распределение НИР по вузам", model, parent=self)
        dlg.exec()

    def show_konk_analysis(self) -> None:
        model = get_konk_distribution_model(self.db, parent=self)
        dlg = ReportViewerDialog("Анализ: Распределение НИР по конкурсам", model, parent=self)
        dlg.exec()

    def show_region_analysis(self) -> None:
        model = get_region_distribution_model(self.db, parent=self)
        dlg = ReportViewerDialog("Анализ: Распределение НИР по регионам РФ", model, parent=self)
        dlg.exec()

    def show_funding_statement(self) -> None:
        model = get_vuz_funding_statement_model(self.db, parent=self)
        dlg = ReportViewerDialog("Ведомость финансирования по вузам (с поквартальной разбивкой)", model, parent=self)
        dlg.exec()

    def show_about_dialog(self) -> None:
        text = (
            "<h3>Информационная система сопровождения конкурсов грантов НИР</h3>"
            "<p><b>Учебный курс:</b> Базы данных (СУБД)<br>"
            "<b>Кафедра:</b> Управления и интеллектуальных технологий (УИТ НИУ «МЭИ»)<br>"
            "<b>Вариант:</b> №7 «Сопровождение конкурсов на соискание грантов»<br>"
            "<b>Преподаватель:</b> доцент Полотнов М. М.<br>"
            "<b>Студент:</b> Егор Грудинин</p>"
            "<hr>"
            "<p><b>Стек технологий:</b> Python 3, PyQt6, SQLite</p>"
        )
        QMessageBox.about(self, "О программе", text)


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("GrantsManagementSystem")

    db_path = get_db_path()
    if not db_path.exists():
        from scripts.etl_import_excel import import_data
        import_data(db_path)

    window = MainWindow(db_path)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
