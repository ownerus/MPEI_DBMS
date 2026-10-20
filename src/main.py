import sys
import sqlite3
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtSql import QSqlDatabase, QSqlTableModel
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTableView,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

# Добавляем корень проекта и папку src в sys.path для любого способа запуска
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

try:
    from src.database import DB_PATH, connect_db
    from src.dialogs import ProjectDialog, FilterDialog
    from src.reports import (
        build_contest_report,
        build_vuz_report,
        build_region_report,
        export_report_to_file,
        _format_money,
    )
except ModuleNotFoundError:
    from database import DB_PATH, connect_db
    from dialogs import ProjectDialog, FilterDialog
    from reports import (
        build_contest_report,
        build_vuz_report,
        build_region_report,
        export_report_to_file,
        _format_money,
    )


class GrantsTableModel(QSqlTableModel):
    """Модель таблицы с поддержкой составной сортировки по первичному ключу."""

    def __init__(self, parent=None, db=QSqlDatabase()):
        super().__init__(parent, db)
        self._custom_order = ""

    def setCustomOrder(self, order_str: str):
        self._custom_order = order_str
        self.select()

    def orderByClause(self) -> str:
        if self._custom_order:
            return f"ORDER BY {self._custom_order}"
        return super().orderByClause()

    def sort(self, column: int, order: Qt.SortOrder):
        # При клике на заголовок столбца сбрасываем пользовательский составной ORDER BY
        self._custom_order = ""
        super().sort(column, order)


class MainWindow(QMainWindow):
    """Главное окно приложения для сопровождения конкурсов грантов (Вариант 7)."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("СУБД: Сопровождение конкурсов на соискание грантов (Вариант 7)")
        self.resize(1200, 680)

        # Текущее состояние
        self.current_model = None
        self.current_table_name = "gr_proj"
        self.current_filters = {}
        self.current_filter_where = ""
        self.current_filter_summary = ""
        self.current_report_data = None

        self._init_menu()
        self._init_ui()

        # По умолчанию открываем таблицу проектов НИР
        self.show_table("gr_proj")

    def _init_menu(self):
        """Создание главного меню приложения."""
        menubar = self.menuBar()

        # Меню "Файл"
        menu_file = menubar.addMenu("Файл")
        act_save_as = menu_file.addAction("Сохранить как...")
        act_save_as.setShortcut("Ctrl+S")
        act_save_as.triggered.connect(self._on_save_as)

        menu_file.addSeparator()

        act_exit = menu_file.addAction("Выход")
        act_exit.setShortcut("Ctrl+Q")
        act_exit.triggered.connect(self.close)

        # Меню "Данные"
        menu_data = menubar.addMenu("Данные")
        act_proj = menu_data.addAction("НИР по грантам")
        act_proj.triggered.connect(lambda: self.combo_view.setCurrentIndex(0))

        act_konk = menu_data.addAction("Конкурсы грантов")
        act_konk.triggered.connect(lambda: self.combo_view.setCurrentIndex(1))

        act_vuz = menu_data.addAction("Справочник вузов")
        act_vuz.triggered.connect(lambda: self.combo_view.setCurrentIndex(2))

        # Меню "Анализ" (Лабораторная работа №3)
        menu_analysis = menubar.addMenu("Анализ")
        act_an_konk = menu_analysis.addAction("Распределение НИР по конкурсам")
        act_an_konk.triggered.connect(lambda: self._switch_to_report(0))

        act_an_vuz = menu_analysis.addAction("Распределение НИР по вузам")
        act_an_vuz.triggered.connect(lambda: self._switch_to_report(1))

        act_an_reg = menu_analysis.addAction("Распределение НИР по регионам РФ")
        act_an_reg.triggered.connect(lambda: self._switch_to_report(2))

        # Меню "Финансирование"
        menu_finance = menubar.addMenu("Финансирование")
        act_fin_order = menu_finance.addAction("Выпуск распоряжения о финансировании")
        act_fin_order.triggered.connect(lambda: self.combo_view.setCurrentIndex(4))

        act_fin_ved = menu_finance.addAction("Ведомость выплат по вузам")
        act_fin_ved.triggered.connect(lambda: self.combo_view.setCurrentIndex(4))

        # Меню "Справка"
        menu_help = menubar.addMenu("Справка")
        act_about = menu_help.addAction("О программе")
        act_about.triggered.connect(self._show_about)

    def _init_ui(self):
        """Построение элементов графического интерфейса."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 8, 10, 10)
        main_layout.setSpacing(6)

        # 1. Единая компактная панель инструментов (toolbar) над таблицей:
        # Селектор разделов (без подписи "Раздел системы:"), кнопки действий с иконками и счетчик
        toolbar_layout = QHBoxLayout()
        toolbar_layout.setContentsMargins(0, 0, 0, 2)
        toolbar_layout.setSpacing(6)

        self.combo_view = QComboBox()
        self.combo_view.addItems([
            "Проекты НИР по грантам",
            "Конкурсы грантов",
            "Справочник вузов",
            "Анализ данных",
            "Финансирование",
        ])
        self.combo_view.setMinimumWidth(215)
        self.combo_view.currentIndexChanged.connect(self._on_section_changed)

        self.btn_add = QPushButton("Добавить")
        self.btn_add.clicked.connect(self._on_add_record)

        self.btn_edit = QPushButton("Изменить")
        self.btn_edit.clicked.connect(self._on_edit_record)

        self.btn_delete = QPushButton("Удалить")
        self.btn_delete.clicked.connect(self._on_delete_record)

        self.btn_key_sort = QPushButton("Сортировка по ключу")
        self.btn_key_sort.setToolTip("Упорядочить по первичному составному ключу (Конкурс + Код НИР)")
        self.btn_key_sort.clicked.connect(self._sort_by_key)

        self.btn_filter = QPushButton("Фильтр")
        self.btn_filter.clicked.connect(self._on_filter)

        self.btn_clear_filter = QPushButton("Снять фильтр")
        self.btn_clear_filter.setVisible(False)
        self.btn_clear_filter.clicked.connect(self._on_clear_filter)

        self.btn_save_as = QPushButton("Сохранить как...")
        self.btn_save_as.setToolTip("Сохранить открытый документ или таблицу в файл Excel, HTML, CSV или TXT (Ctrl+S)")
        self.btn_save_as.clicked.connect(self._on_save_as)

        self.lbl_status = QLabel("Всего записей: 0")
        self.lbl_status.setStyleSheet("font-weight: 500;")

        toolbar_layout.addWidget(self.combo_view)
        toolbar_layout.addWidget(self.btn_add)
        toolbar_layout.addWidget(self.btn_edit)
        toolbar_layout.addWidget(self.btn_delete)
        toolbar_layout.addWidget(self.btn_key_sort)
        toolbar_layout.addWidget(self.btn_filter)
        toolbar_layout.addWidget(self.btn_clear_filter)
        toolbar_layout.addWidget(self.btn_save_as)
        toolbar_layout.addStretch()
        toolbar_layout.addWidget(self.lbl_status)

        main_layout.addLayout(toolbar_layout)

        # 2. Центральная область (стек экранов)
        self.stack = QStackedWidget()

        # Страница 0: Просмотр таблиц (вся высота отдана таблице данных)
        table_page = QWidget()
        table_layout = QVBoxLayout(table_page)
        table_layout.setContentsMargins(0, 4, 0, 0)
        table_layout.setSpacing(0)

        self.table_view = QTableView()
        self.table_view.setSortingEnabled(True)
        self.table_view.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table_view.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        table_layout.addWidget(self.table_view)

        self.stack.addWidget(table_page)

        # Страница 1: Раздел «Анализ данных» (ЛР3 — сводные аналитические отчеты)
        analysis_page = QWidget()
        analysis_layout = QVBoxLayout(analysis_page)
        analysis_layout.setContentsMargins(0, 4, 0, 0)
        analysis_layout.setSpacing(6)

        analysis_toolbar = QHBoxLayout()
        lbl_rep = QLabel("Аналитический отчет:")
        lbl_rep.setStyleSheet("font-weight: bold;")

        self.combo_report = QComboBox()
        self.combo_report.addItems([
            "Форма 1: Распределение проектов НИР по конкурсам грантов",
            "Форма 2: Распределение проектов НИР по вузам-исполнителям",
            "Форма 3: Распределение проектов НИР по субъектам РФ",
        ])
        self.combo_report.setMinimumWidth(390)
        self.combo_report.currentIndexChanged.connect(self._on_report_changed)

        self.btn_report_refresh = QPushButton("Обновить")
        self.btn_report_refresh.clicked.connect(self.refresh_current_report)

        self.lbl_report_info = QLabel("")

        analysis_toolbar.addWidget(lbl_rep)
        analysis_toolbar.addWidget(self.combo_report)
        analysis_toolbar.addWidget(self.btn_report_refresh)
        analysis_toolbar.addStretch()
        analysis_toolbar.addWidget(self.lbl_report_info)
        analysis_layout.addLayout(analysis_toolbar)

        self.report_table = QTableWidget()
        self.report_table.setAlternatingRowColors(True)
        self.report_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.report_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.report_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        analysis_layout.addWidget(self.report_table)

        self.stack.addWidget(analysis_page)

        # Страница 2: Раздел «Финансирование»
        finance_page = QWidget()
        finance_layout = QVBoxLayout(finance_page)
        finance_layout.setContentsMargins(0, 4, 0, 0)

        self.lbl_finance_stub = QLabel(
            "Раздел «Финансирование»\n\n"
            "Функции раздела:\n"
            "• Выпуск распоряжения по финансированию НИР\n"
            "• Формирование сводной ведомости выплат по вузам\n\n"
            "Функция пока не реализована."
        )
        self.lbl_finance_stub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_finance_stub.setStyleSheet("font-size: 14px; color: #555; background: #f9f9f9; border: 1px dashed #ccc;")
        finance_layout.addWidget(self.lbl_finance_stub)

        self.stack.addWidget(finance_page)

        main_layout.addWidget(self.stack)

    def _switch_to_report(self, form_idx: int):
        """Переключение на указанную аналитическую форму из меню."""
        self.combo_view.setCurrentIndex(3)
        self.combo_report.setCurrentIndex(form_idx)
        self.refresh_current_report()

    def _on_report_changed(self, index: int):
        """Смена аналитической формы в комбобоксе отчетов."""
        self.refresh_current_report()

    def _on_section_changed(self, index: int):
        """Обработка переключения разделов."""
        is_proj = (index == 0)
        is_table = (index in (0, 1, 2))
        is_analysis = (index == 3)

        # Управление доступностью кнопок на главной панели
        self.btn_add.setEnabled(is_proj)
        self.btn_edit.setEnabled(is_proj)
        self.btn_delete.setEnabled(is_proj)
        self.btn_key_sort.setEnabled(is_proj)
        self.btn_filter.setEnabled(is_proj or is_analysis)
        self.btn_clear_filter.setEnabled(bool(self.current_filter_where))
        self.btn_clear_filter.setVisible(bool(self.current_filter_where))
        self.btn_save_as.setEnabled(is_table or is_analysis)

        if index == 0:
            self.stack.setCurrentIndex(0)
            self.show_table("gr_proj")
        elif index == 1:
            self.stack.setCurrentIndex(0)
            self.show_table("gr_konk")
        elif index == 2:
            self.stack.setCurrentIndex(0)
            self.show_table("vuz")
        elif index == 3:
            self.stack.setCurrentIndex(1)
            self.refresh_current_report()
        elif index == 4:
            self.stack.setCurrentIndex(2)
            self.lbl_status.setText("Раздел финансирования")

    def show_table(self, table_name: str):
        """Отображение таблицы БД с индивидуальной фиксированной шапкой и автошириной."""
        self.current_table_name = table_name
        self.current_model = GrantsTableModel(self)
        self.current_model.setTable(table_name)

        # Настраиваем читаемые русские заголовки
        if table_name == "gr_proj":
            headers = {
                1: "Конкурс",
                2: "Код НИР",
                3: "Код вуза",
                4: "Вуз",
                5: "ГРНТИ",
                6: "План",
                7: "Факт",
                8: "Квартал 1",
                9: "Квартал 2",
                10: "Квартал 3",
                11: "Квартал 4",
                12: "Руководитель",
                13: "Должность",
                14: "Звание",
                15: "Степень",
                16: "Тема НИР",
            }
            if self.current_filter_where:
                self.current_model.setFilter(self.current_filter_where)

        elif table_name == "gr_konk":
            headers = {
                0: "Код конкурса",
                1: "Название конкурса",
                2: "План",
                3: "Факт",
                4: "Квартал 1",
                5: "Квартал 2",
                6: "Квартал 3",
                7: "Квартал 4",
                8: "Число проектов",
            }

        elif table_name == "vuz":
            headers = {
                0: "Код вуза",
                1: "Аббревиатура",
                2: "Статус",
                3: "Город",
                4: "Федеральный округ",
                5: "Субъект РФ",
                6: "Профиль",
                7: "Ведомство",
                8: "Код региона",
                9: "Наименование вуза",
                10: "Полное наименование",
            }

        for col, text in headers.items():
            self.current_model.setHeaderData(col, Qt.Orientation.Horizontal, text)

        self.current_model.select()
        self.table_view.setModel(self.current_model)

        # Скрываем суррогатный id в таблице проектов
        if table_name == "gr_proj":
            self.table_view.hideColumn(0)

        # Подгружаем все строки для корректного счетчика записей
        while self.current_model.canFetchMore():
            self.current_model.fetchMore()

        # Настройка фиксированной шапки и адаптивной ширины столбцов
        header = self.table_view.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(False)

        self.table_view.resizeColumnsToContents()

        # Гарантируем, что заголовки полностью читаемы и не обрезаются
        fm = self.table_view.fontMetrics()
        for col in range(self.current_model.columnCount()):
            h_text = self.current_model.headerData(col, Qt.Orientation.Horizontal)
            h_width = fm.horizontalAdvance(str(h_text or "")) + 28
            c_width = self.table_view.columnWidth(col)
            target_width = max(h_width, c_width)

            if table_name == "gr_proj" and col == 16:  # Длинная тема НИР
                target_width = max(target_width, 380)
            elif table_name == "vuz" and col in (9, 10):  # Длинные наименования вузов справа
                target_width = max(target_width, 320)

            self.table_view.setColumnWidth(col, target_width)

        # Управление доступностью кнопок
        is_proj = (table_name == "gr_proj")
        self.btn_key_sort.setEnabled(is_proj)
        self.btn_add.setEnabled(is_proj)
        self.btn_edit.setEnabled(is_proj)
        self.btn_delete.setEnabled(is_proj)
        self.btn_filter.setEnabled(is_proj)
        self.btn_save_as.setEnabled(True)

        has_filter = is_proj and bool(self.current_filter_where)
        self.btn_clear_filter.setVisible(has_filter)
        self.btn_clear_filter.setEnabled(has_filter)

        self._update_status()

    def _update_status(self):
        """Обновление строки состояния."""
        if self.combo_view.currentIndex() == 3:
            return
        count = self.current_model.rowCount() if self.current_model else 0
        if self.current_filter_where and self.current_table_name == "gr_proj":
            self.lbl_status.setText(f"Записей: {count} (фильтр: {self.current_filter_summary})")
        else:
            self.lbl_status.setText(f"Всего записей: {count}")

    def refresh_current_report(self):
        """Формирование и отрисовка текущего аналитического отчета (ЛР3)."""
        idx = self.combo_report.currentIndex()
        if idx == 0:
            report_data = build_contest_report(DB_PATH, self.current_filter_where)
        elif idx == 1:
            report_data = build_vuz_report(DB_PATH, self.current_filter_where)
        else:
            report_data = build_region_report(DB_PATH, self.current_filter_where)

        self.current_report_data = report_data
        self.render_report(report_data)

    def render_report(self, report_data: dict):
        """Отрисовка отчета в self.report_table."""
        headers = report_data.get("headers", [])
        rows = report_data.get("rows", [])
        totals = report_data.get("totals", [])
        money_cols = set(report_data.get("money_cols", []))
        numeric_cols = set(report_data.get("numeric_cols", []))

        total_row_count = len(rows) + (1 if totals else 0)
        self.report_table.setRowCount(total_row_count)
        self.report_table.setColumnCount(len(headers))
        self.report_table.setHorizontalHeaderLabels(headers)

        # Заполнение строк данных
        for row_idx, r in enumerate(rows):
            for col_idx, val in enumerate(r):
                if col_idx in money_cols:
                    val_str = _format_money(val)
                    align = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                elif col_idx in numeric_cols:
                    val_str = str(val)
                    align = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                elif col_idx == 0:
                    val_str = str(val)
                    align = Qt.AlignmentFlag.AlignCenter
                else:
                    val_str = str(val)
                    align = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter

                item = QTableWidgetItem(val_str)
                item.setTextAlignment(align)
                item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                self.report_table.setItem(row_idx, col_idx, item)

        # Заполнение строки ИТОГО
        if totals:
            tot_row_idx = len(rows)
            for col_idx, val in enumerate(totals):
                if col_idx in money_cols:
                    val_str = _format_money(val) if val != "" else ""
                    align = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                elif col_idx in numeric_cols:
                    val_str = str(val) if val != "" else ""
                    align = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                elif col_idx == 0:
                    val_str = str(val)
                    align = Qt.AlignmentFlag.AlignCenter
                else:
                    val_str = str(val)
                    align = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter

                item = QTableWidgetItem(val_str)
                item.setTextAlignment(align)
                item.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
                item.setBackground(QColor(255, 242, 204))
                item.setForeground(QColor(0, 0, 0))
                item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                self.report_table.setItem(tot_row_idx, col_idx, item)

        # Автоподбор ширины столбцов
        header = self.report_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        self.report_table.resizeColumnsToContents()

        fm = self.report_table.fontMetrics()
        for col in range(len(headers)):
            h_text = headers[col]
            h_width = fm.horizontalAdvance(h_text) + 24
            c_width = self.report_table.columnWidth(col)
            self.report_table.setColumnWidth(col, max(h_width, c_width, 90))

        # Обновление текста состояния
        status_txt = f"Строк: {len(rows)}"
        if self.current_filter_where:
            status_txt += f" (фильтр: {self.current_filter_summary})"
            self.lbl_status.setText(f"Отчет: {len(rows)} строк (фильтр: {self.current_filter_summary})")
        else:
            self.lbl_status.setText(f"Отчет: {len(rows)} строк (полная база)")
        self.lbl_report_info.setText(status_txt)

    def _sort_by_key(self):
        """Сортировка по составному первичному ключу (Конкурс + Код НИР)."""
        if self.current_table_name != "gr_proj" or not self.current_model:
            return
        self.current_model.setCustomOrder("codkon ASC, codproj ASC")
        while self.current_model.canFetchMore():
            self.current_model.fetchMore()
        self._update_status()

    def _on_add_record(self):
        """Добавление нового проекта НИР."""
        if self.current_table_name != "gr_proj":
            return

        default_codkon = 1
        sel = self.table_view.selectionModel().selectedRows()
        if sel:
            rec = self.current_model.record(sel[0].row())
            default_codkon = rec.value("codkon") or 1

        dlg = ProjectDialog(self, mode="add", default_codkon=default_codkon, db_path=DB_PATH)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            d = dlg.result_data

            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO gr_proj (
                    codkon, codproj, codvuz, vuz_short_name, grnti_code, plan_fin,
                    fact_fin, fin_q1, fin_q2, fin_q3, fin_q4,
                    leader_fio, leader_post, leader_rank, leader_degree, proj_name
                ) VALUES (?, ?, ?, ?, ?, ?, 0, 0, 0, 0, 0, ?, ?, ?, ?, ?)
            """, (
                d["codkon"], d["codproj"], d["codvuz"], d["vuz_short_name"],
                d["grnti_code"], d["plan_fin"],
                d["leader_fio"], d["leader_post"], d["leader_rank"], d["leader_degree"],
                d["proj_name"]
            ))

            # Автоматически обновляем агрегаты конкурса
            cur.execute("""
                UPDATE gr_konk
                SET projects_count = projects_count + 1,
                    plan_fin = plan_fin + ?
                WHERE codkon = ?
            """, (d["plan_fin"], d["codkon"]))

            conn.commit()
            conn.close()

            # Обновляем представление
            self.current_model.select()
            while self.current_model.canFetchMore():
                self.current_model.fetchMore()

            # Перемещаем курсор и выделение на добавленную запись
            for r in range(self.current_model.rowCount()):
                rec = self.current_model.record(r)
                if rec.value("codkon") == d["codkon"] and rec.value("codproj") == d["codproj"]:
                    self.table_view.selectRow(r)
                    self.table_view.scrollTo(self.current_model.index(r, 1))
                    break

            self._update_status()

    def _on_edit_record(self):
        """Редактирование выбранного проекта НИР."""
        if self.current_table_name != "gr_proj":
            return

        selection = self.table_view.selectionModel().selectedRows()
        if not selection:
            QMessageBox.warning(self, "Внимание", "Пожалуйста, выделите строку проекта для редактирования.")
            return

        row_idx = selection[0].row()
        rec = self.current_model.record(row_idx)

        record_data = {
            "id": rec.value("id"),
            "codkon": rec.value("codkon"),
            "codproj": rec.value("codproj"),
            "codvuz": rec.value("codvuz"),
            "vuz_short_name": rec.value("vuz_short_name"),
            "grnti_code": rec.value("grnti_code"),
            "plan_fin": rec.value("plan_fin"),
            "leader_fio": rec.value("leader_fio"),
            "leader_post": rec.value("leader_post"),
            "leader_rank": rec.value("leader_rank"),
            "leader_degree": rec.value("leader_degree"),
            "proj_name": rec.value("proj_name"),
        }

        dlg = ProjectDialog(self, mode="edit", record_data=record_data, db_path=DB_PATH)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            d = dlg.result_data
            old_plan = int(record_data.get("plan_fin") or 0)
            new_plan = int(d["plan_fin"] or 0)
            old_codkon = int(record_data.get("codkon"))
            new_codkon = int(d["codkon"])

            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            cur.execute("""
                UPDATE gr_proj
                SET codkon = ?, codproj = ?, codvuz = ?, vuz_short_name = ?, grnti_code = ?, plan_fin = ?,
                    leader_fio = ?, leader_post = ?, leader_rank = ?, leader_degree = ?,
                    proj_name = ?
                WHERE id = ?
            """, (
                d["codkon"], d["codproj"], d["codvuz"], d["vuz_short_name"], d["grnti_code"], d["plan_fin"],
                d["leader_fio"], d["leader_post"], d["leader_rank"], d["leader_degree"],
                d["proj_name"], record_data["id"]
            ))

            # Синхронизация сумм и счетчиков в таблице конкурсов
            if old_codkon != new_codkon:
                # 1. Уменьшаем счетчик и сумму в старом конкурсе
                cur.execute("""
                    UPDATE gr_konk
                    SET projects_count = projects_count - 1,
                        plan_fin = plan_fin - ?
                    WHERE codkon = ?
                """, (old_plan, old_codkon))
                # 2. Увеличиваем счетчик и сумму в новом конкурсе
                cur.execute("""
                    UPDATE gr_konk
                    SET projects_count = projects_count + 1,
                        plan_fin = plan_fin + ?
                    WHERE codkon = ?
                """, (new_plan, new_codkon))
            else:
                # Конкурс не менялся, только сумма
                plan_diff = new_plan - old_plan
                if plan_diff != 0:
                    cur.execute("""
                        UPDATE gr_konk
                        SET plan_fin = plan_fin + ?
                        WHERE codkon = ?
                    """, (plan_diff, new_codkon))

            conn.commit()
            conn.close()

            self.current_model.select()
            while self.current_model.canFetchMore():
                self.current_model.fetchMore()

            # Восстанавливаем выделение
            for r in range(self.current_model.rowCount()):
                rec_r = self.current_model.record(r)
                if rec_r.value("id") == record_data["id"]:
                    self.table_view.selectRow(r)
                    self.table_view.scrollTo(self.current_model.index(r, 1))
                    break

            self._update_status()

    def _on_delete_record(self):
        """Удаление строго одной выделенной записи с запросом подтверждения."""
        if self.current_table_name != "gr_proj":
            return

        selection = self.table_view.selectionModel().selectedRows()
        if not selection:
            QMessageBox.warning(self, "Внимание", "Пожалуйста, выделите строку проекта для удаления.")
            return

        row_idx = selection[0].row()
        rec = self.current_model.record(row_idx)
        proj_id = rec.value("id")
        codkon = rec.value("codkon")
        codproj = rec.value("codproj")
        leader_fio = rec.value("leader_fio")
        plan_fin = int(rec.value("plan_fin") or 0)

        # Диалог подтверждения с русскими кнопками "Да" и "Нет"
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Подтверждение удаления")
        msg_box.setText(
            f"Вы действительно хотите удалить проект №{codproj} конкурса №{codkon}?\n\n"
            f"Руководитель: {leader_fio}\n"
            f"План финансирования: {_format_money(plan_fin)}"
        )
        msg_box.setIcon(QMessageBox.Icon.Question)
        btn_yes = msg_box.addButton("Да", QMessageBox.ButtonRole.YesRole)
        btn_no = msg_box.addButton("Нет", QMessageBox.ButtonRole.NoRole)
        msg_box.setDefaultButton(btn_no)
        msg_box.exec()

        if msg_box.clickedButton() == btn_yes:
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            cur.execute("DELETE FROM gr_proj WHERE id = ?", (proj_id,))
            cur.execute("""
                UPDATE gr_konk
                SET projects_count = projects_count - 1,
                    plan_fin = plan_fin - ?
                WHERE codkon = ?
            """, (plan_fin, codkon))
            conn.commit()
            conn.close()

            self.current_model.select()
            while self.current_model.canFetchMore():
                self.current_model.fetchMore()

            self._update_status()

    def _on_filter(self):
        """Открытие диалогового окна сложной фильтрации."""
        dlg = FilterDialog(self, current_filters=self.current_filters, db_path=DB_PATH)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.current_filters = dlg.saved_filter_state
            self.current_filter_where = dlg.filter_where
            self.current_filter_summary = dlg.filter_summary

            if self.current_table_name == "gr_proj" and self.current_model:
                self.current_model.setFilter(self.current_filter_where)
                self.current_model.select()
                while self.current_model.canFetchMore():
                    self.current_model.fetchMore()

            has_flt = bool(self.current_filter_where)
            self.btn_clear_filter.setVisible(has_flt)
            self.btn_clear_filter.setEnabled(has_flt)

            if self.combo_view.currentIndex() == 3:
                self.refresh_current_report()
            else:
                self._update_status()

    def _on_clear_filter(self):
        """Сброс активного фильтра."""
        self.current_filters = {}
        self.current_filter_where = ""
        self.current_filter_summary = ""

        if self.current_table_name == "gr_proj" and self.current_model:
            self.current_model.setFilter("")
            self.current_model.select()
            while self.current_model.canFetchMore():
                self.current_model.fetchMore()

        self.btn_clear_filter.setVisible(False)
        self.btn_clear_filter.setEnabled(False)

        if self.combo_view.currentIndex() == 3:
            self.refresh_current_report()
        else:
            self._update_status()

    def _on_save_as(self):
        """Универсальный экспорт открытого в данный момент документа или таблицы."""
        curr_idx = self.combo_view.currentIndex()

        if curr_idx == 3:  # Раздел «Анализ данных»
            if not self.current_report_data:
                self.refresh_current_report()

            rep_num = self.combo_report.currentIndex() + 1
            default_name = f"otchet_forma_{rep_num}.xlsx"

            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "Сохранить отчет как...",
                default_name,
                "Таблица Excel (*.xlsx);;Веб-страница HTML (*.html);;Текстовый документ (*.txt);;Файл CSV (*.csv)"
            )
            if not file_path:
                return

            try:
                export_report_to_file(file_path, self.current_report_data, self.current_filter_summary)
                QMessageBox.information(
                    self,
                    "Экспорт завершен",
                    f"Аналитический отчет успешно сохранен в файл:\n{file_path}"
                )
            except Exception as e:
                QMessageBox.critical(self, "Ошибка сохранения", f"Не удалось сохранить отчет:\n{e}")

        elif curr_idx in (0, 1, 2):  # Таблицы базы данных
            table_name = self.current_table_name
            table_titles = {
                "gr_proj": "Проекты НИР по грантам",
                "gr_konk": "Конкурсы грантов",
                "vuz": "Справочник вузов",
            }
            title = table_titles.get(table_name, table_name)
            default_name = f"{table_name}_export.xlsx"

            file_path, _ = QFileDialog.getSaveFileName(
                self,
                f"Сохранить таблицу «{title}» как...",
                default_name,
                "Таблица Excel (*.xlsx);;Веб-страница HTML (*.html);;Текстовый документ (*.txt);;Файл CSV (*.csv)"
            )
            if not file_path:
                return

            try:
                visible_cols = []
                headers = []
                for c in range(self.current_model.columnCount()):
                    if not self.table_view.isColumnHidden(c):
                        visible_cols.append(c)
                        headers.append(str(self.current_model.headerData(c, Qt.Orientation.Horizontal) or f"Колонка {c}"))

                rows = []
                for r in range(self.current_model.rowCount()):
                    rec = self.current_model.record(r)
                    row_vals = []
                    for c in visible_cols:
                        val = rec.value(c)
                        row_vals.append(val if val is not None else "")
                    rows.append(row_vals)

                money_cols = []
                numeric_cols = []
                if table_name == "gr_proj":
                    for idx, c in enumerate(visible_cols):
                        if c in (6, 7, 8, 9, 10, 11):
                            money_cols.append(idx)
                        elif c in (1, 2, 3):
                            numeric_cols.append(idx)
                elif table_name == "gr_konk":
                    for idx, c in enumerate(visible_cols):
                        if c in (2, 3, 4, 5, 6, 7):
                            money_cols.append(idx)
                        elif c in (0, 8):
                            numeric_cols.append(idx)

                table_report_data = {
                    "title": f"СУБД: {title}",
                    "headers": headers,
                    "rows": rows,
                    "totals": [],
                    "money_cols": money_cols,
                    "numeric_cols": numeric_cols,
                }

                export_report_to_file(file_path, table_report_data, self.current_filter_summary if table_name == "gr_proj" else "")
                QMessageBox.information(
                    self,
                    "Экспорт завершен",
                    f"Данные таблицы «{title}» успешно сохранены:\n{file_path}"
                )
            except Exception as e:
                QMessageBox.critical(self, "Ошибка сохранения", f"Не удалось сохранить таблицу:\n{e}")
        else:
            QMessageBox.information(self, "Сохранить как...", "В данном разделе нет открытых документов для сохранения.")

    def _show_about(self):
        """Сведения о программе."""
        QMessageBox.information(
            self,
            "О программе",
            "Дисциплина: Системы управления базами данных (СУБД)\n"
            "НИУ «МЭИ», Кафедра УИТ\n"
            "Вариант:  №7 Сопровождение конкурсов на соискание грантов\n\n"
            "Группа: А-03-23\n"
            "Бригада: 4\n"
            "Студенты: Грудинин Е.К., Степанищев В.Р., Криштул А.Н.\n"
            "Преподаватель: доц. Полотнов М.М."
        )


def main():
    app = QApplication(sys.argv)

    if not connect_db():
        sys.exit(1)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
