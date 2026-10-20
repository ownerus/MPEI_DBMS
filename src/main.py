import sys
import sqlite3
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QColor, QFont, QKeySequence
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
    QStatusBar,
    QTableView,
    QTableWidget,
    QTableWidgetItem,
    QStackedWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

# Добавляем корень проекта и папку src в sys.path
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
        # При клике на заголовок сбрасываем составной ORDER BY
        self._custom_order = ""
        super().sort(column, order)


class MainWindow(QMainWindow):
    """
    Главное окно приложения для сопровождения конкурсов грантов (Вариант 7).
    Построено по эталонному шаблону настольных приложений Windows:
    - Главное меню (Файл, Правка, Вид, Анализ, Фильтр, Справка)
    - Панель инструментов (Toolbar) со стандартными действиями и горячими клавишами
    - Вкладки разделов (Tabs) без лишних повторяющихся окон и выпадающих списков
    - Строка состояния (Status Bar) внизу окна
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle("СУБД: Сопровождение конкурсов на соискание грантов (Вариант 7)")
        self.resize(1200, 720)

        # Состояние фильтрации и отчетов
        self.current_filters = {}
        self.current_filter_where = ""
        self.current_filter_summary = ""
        self.current_report_data = None

        self._init_models()
        self._init_actions()
        self._init_menu()
        self._init_toolbar()
        self._init_statusbar()
        self._init_ui()

        # Первоначальная загрузка первого раздела
        self._switch_section(0)

    def _init_models(self):
        """Инициализация моделей таблиц БД."""
        # 1. Проекты НИР
        self.model_proj = GrantsTableModel(self)
        self.model_proj.setTable("gr_proj")
        headers_proj = {
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
        for col, text in headers_proj.items():
            self.model_proj.setHeaderData(col, Qt.Orientation.Horizontal, text)
        self.model_proj.select()

        # 2. Конкурсы грантов
        self.model_konk = GrantsTableModel(self)
        self.model_konk.setTable("gr_konk")
        headers_konk = {
            0: "Код конкурса",
            1: "Наименование конкурса",
            2: "План",
            3: "Факт",
            4: "Квартал 1",
            5: "Квартал 2",
            6: "Квартал 3",
            7: "Квартал 4",
            8: "Число проектов",
        }
        for col, text in headers_konk.items():
            self.model_konk.setHeaderData(col, Qt.Orientation.Horizontal, text)
        self.model_konk.select()

        # 3. Справочник вузов
        self.model_vuz = GrantsTableModel(self)
        self.model_vuz.setTable("vuz")
        headers_vuz = {
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
        for col, text in headers_vuz.items():
            self.model_vuz.setHeaderData(col, Qt.Orientation.Horizontal, text)
        self.model_vuz.select()

    def _init_actions(self):
        """Создание стандартных действий (Actions) для меню и панели инструментов."""
        # Файл
        self.act_save_as = QAction("Сохранить как...", self)
        self.act_save_as.setShortcut(QKeySequence.StandardKey.Save)
        self.act_save_as.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
        self.act_save_as.setStatusTip("Экспорт открытой таблицы или аналитического отчета в файл (Excel, HTML, CSV, TXT)")
        self.act_save_as.triggered.connect(self._on_save_as)

        self.act_exit = QAction("Выход", self)
        self.act_exit.setShortcut("Ctrl+Q")
        self.act_exit.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
        self.act_exit.setStatusTip("Завершение работы с программой")
        self.act_exit.triggered.connect(self.close)

        # Действия над данными (CRUD)
        self.act_add = QAction("Добавить", self)
        self.act_add.setShortcut(QKeySequence("Insert"))
        self.act_add.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
        self.act_add.setStatusTip("Добавить новый проект НИР (Insert)")
        self.act_add.triggered.connect(self._on_add_record)

        self.act_edit = QAction("Изменить", self)
        self.act_edit.setShortcut(QKeySequence("F4"))
        self.act_edit.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
        self.act_edit.setStatusTip("Редактировать выделенный проект НИР (F4)")
        self.act_edit.triggered.connect(self._on_edit_record)

        self.act_delete = QAction("Удалить", self)
        self.act_delete.setShortcut(QKeySequence.StandardKey.Delete)
        self.act_delete.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
        self.act_delete.setStatusTip("Удалить выделенный проект НИР (Delete)")
        self.act_delete.triggered.connect(self._on_delete_record)

        self.act_key_sort = QAction("Сортировка по ключу", self)
        self.act_key_sort.setShortcut(QKeySequence("Ctrl+K"))
        self.act_key_sort.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
        self.act_key_sort.setStatusTip("Упорядочить по первичному составному ключу (Конкурс + Код НИР)")
        self.act_key_sort.triggered.connect(self._sort_by_key)

        # Фильтр
        self.act_filter = QAction("Фильтр", self)
        self.act_filter.setShortcut(QKeySequence.StandardKey.Find)
        self.act_filter.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
        self.act_filter.setStatusTip("Открыть окно расширенной фильтрации (Ctrl+F)")
        self.act_filter.triggered.connect(self._on_filter)

        self.act_clear_filter = QAction("Снять фильтр", self)
        self.act_clear_filter.setShortcut(QKeySequence("Ctrl+Shift+F"))
        self.act_clear_filter.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
        self.act_clear_filter.setStatusTip("Сбросить активный фильтр и показать все записи")
        self.act_clear_filter.setVisible(False)
        self.act_clear_filter.setEnabled(False)
        self.act_clear_filter.triggered.connect(self._on_clear_filter)

        # Обновить
        self.act_refresh = QAction("Обновить", self)
        self.act_refresh.setShortcut(QKeySequence.StandardKey.Refresh)
        self.act_refresh.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
        self.act_refresh.setStatusTip("Обновить данные активного экрана (F5)")
        self.act_refresh.triggered.connect(self._on_refresh)

        # О программе
        self.act_about = QAction("О программе", self)
        self.act_about.setShortcut(QKeySequence.StandardKey.HelpContents)
        self.act_about.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
        self.act_about.setStatusTip("Сведения о программе, дисциплине и авторах (F1)")
        self.act_about.triggered.connect(self._show_about)

        # Регистрируем все действия на уровне главного окна для надежной работы горячих клавиш
        self.addActions([
            self.act_save_as,
            self.act_exit,
            self.act_add,
            self.act_edit,
            self.act_delete,
            self.act_key_sort,
            self.act_filter,
            self.act_clear_filter,
            self.act_refresh,
            self.act_about,
        ])

    def _init_menu(self):
        """Создание главного меню."""
        menubar = self.menuBar()

        # 1. Меню "Файл"
        menu_file = menubar.addMenu("Файл")
        menu_file.addAction(self.act_save_as)
        menu_file.addSeparator()
        menu_file.addAction(self.act_exit)

        # 2. Меню "Данные" (выбор таблицы БД)
        menu_data = menubar.addMenu("Данные")
        act_proj = menu_data.addAction("Проекты НИР")
        act_proj.setShortcut("Ctrl+1")
        act_proj.triggered.connect(lambda: self._switch_section(0))

        act_konk = menu_data.addAction("Конкурсы грантов")
        act_konk.setShortcut("Ctrl+2")
        act_konk.triggered.connect(lambda: self._switch_section(1))

        act_vuz = menu_data.addAction("Справочник вузов")
        act_vuz.setShortcut("Ctrl+3")
        act_vuz.triggered.connect(lambda: self._switch_section(2))

        # 3. Меню "Анализ" (прямой переход к аналитическим отчетам ЛР №3)
        menu_analysis = menubar.addMenu("Анализ")
        act_rep1 = menu_analysis.addAction("Форма 1: Распределение по конкурсам")
        act_rep1.triggered.connect(lambda: self._switch_to_report(0))

        act_rep2 = menu_analysis.addAction("Форма 2: Распределение по вузам")
        act_rep2.triggered.connect(lambda: self._switch_to_report(1))

        act_rep3 = menu_analysis.addAction("Форма 3: Распределение по субъектам РФ")
        act_rep3.triggered.connect(lambda: self._switch_to_report(2))

        # 4. Меню "Финансирование"
        menu_fin = menubar.addMenu("Финансирование")
        act_fin_ord = menu_fin.addAction("Выпуск распоряжения о финансировании")
        act_fin_ord.triggered.connect(lambda: self._switch_section(4))
        act_fin_ved = menu_fin.addAction("Ведомость выплат по вузам")
        act_fin_ved.triggered.connect(lambda: self._switch_section(4))

        # 5. Меню "Справка"
        menu_help = menubar.addMenu("Справка")
        menu_help.addAction(self.act_about)

    def _init_toolbar(self):
        """Создание компактной панели инструментов с красивыми, строго отцентрированными кнопками."""
        self.toolbar = QToolBar("Панель инструментов", self)
        self.toolbar.setMovable(False)
        self.toolbar.setFloatable(False)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self.toolbar)

        # Компактное окошко-индикатор текущего раздела
        self.lbl_current_section = QLabel("Проекты НИР")
        self.lbl_current_section.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.toolbar.addWidget(self.lbl_current_section)
        self.toolbar.addSeparator()

        # Кнопки панели управления (QPushButton со строгим центрированием текста)
        self.btn_add = QPushButton("Добавить")
        self.btn_add.setToolTip("Добавить новый проект НИР (Insert)")
        self.btn_add.clicked.connect(self._on_add_record)
        self.toolbar.addWidget(self.btn_add)

        self.btn_edit = QPushButton("Изменить")
        self.btn_edit.setToolTip("Редактировать выделенный проект НИР (F4)")
        self.btn_edit.clicked.connect(self._on_edit_record)
        self.toolbar.addWidget(self.btn_edit)

        self.btn_delete = QPushButton("Удалить")
        self.btn_delete.setToolTip("Удалить выделенный проект НИР (Delete)")
        self.btn_delete.clicked.connect(self._on_delete_record)
        self.toolbar.addWidget(self.btn_delete)

        self.toolbar.addSeparator()

        self.btn_key_sort = QPushButton("Сортировка по ключу")
        self.btn_key_sort.setToolTip("Упорядочить по первичному составному ключу (Ctrl+K)")
        self.btn_key_sort.clicked.connect(self._sort_by_key)
        self.toolbar.addWidget(self.btn_key_sort)

        self.toolbar.addSeparator()

        self.btn_filter = QPushButton("Фильтр")
        self.btn_filter.setToolTip("Открыть окно фильтрации (Ctrl+F)")
        self.btn_filter.clicked.connect(self._on_filter)
        self.toolbar.addWidget(self.btn_filter)

        self.btn_clear_filter = QPushButton("Снять фильтр")
        self.btn_clear_filter.setToolTip("Сбросить активный фильтр (Ctrl+Shift+F)")
        self.btn_clear_filter.setVisible(False)
        self.btn_clear_filter.clicked.connect(self._on_clear_filter)
        self.toolbar.addWidget(self.btn_clear_filter)

        self.toolbar.addSeparator()

        self.btn_save_as = QPushButton("Сохранить как...")
        self.btn_save_as.setToolTip("Экспорт документа в Excel, HTML, CSV, TXT (Ctrl+S)")
        self.btn_save_as.clicked.connect(self._on_save_as)
        self.toolbar.addWidget(self.btn_save_as)

        self.btn_refresh = QPushButton("Обновить")
        self.btn_refresh.setToolTip("Обновить данные активного экрана (F5)")
        self.btn_refresh.clicked.connect(self._on_refresh)
        self.toolbar.addWidget(self.btn_refresh)

        # Аккуратный, компактный стиль для всех кнопок и индикатора
        self.toolbar.setStyleSheet("""
            QToolBar {
                spacing: 6px;
                padding: 3px 6px;
                border-bottom: 1px solid rgba(128, 128, 128, 0.25);
            }
            QLabel {
                font-family: Segoe UI, sans-serif;
                font-size: 12px;
                font-weight: 600;
                padding: 3px 12px;
                height: 22px;
                border: 1px solid rgba(128, 128, 128, 0.45);
                border-radius: 4px;
                background-color: rgba(128, 128, 128, 0.15);
            }
            QPushButton {
                font-family: Segoe UI, sans-serif;
                font-size: 12px;
                padding: 3px 12px;
                height: 22px;
                border: 1px solid rgba(128, 128, 128, 0.35);
                border-radius: 4px;
                background-color: rgba(128, 128, 128, 0.08);
            }
            QPushButton:hover {
                background-color: rgba(128, 128, 128, 0.22);
                border-color: rgba(128, 128, 128, 0.6);
            }
            QPushButton:pressed {
                background-color: rgba(128, 128, 128, 0.35);
            }
            QPushButton:disabled {
                color: rgba(128, 128, 128, 0.4);
                border-color: rgba(128, 128, 128, 0.15);
                background-color: transparent;
            }
        """)

    def _init_ui(self):
        """Построение центральной рабочей области с переключением разделов."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(6, 4, 6, 4)
        main_layout.setSpacing(4)

        # Центральная рабочая область с переключением разделов (без отдельной строки вкладок)
        self.stack = QStackedWidget()

        # Раздел 0: Проекты НИР по грантам
        tab_proj = QWidget()
        layout_proj = QVBoxLayout(tab_proj)
        layout_proj.setContentsMargins(0, 0, 0, 0)
        self.table_proj = QTableView()
        self.table_proj.setModel(self.model_proj)
        self.table_proj.setSortingEnabled(True)
        self.table_proj.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table_proj.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.table_proj.hideColumn(0)  # Скрываем суррогатный id
        self.table_proj.doubleClicked.connect(lambda _: self._on_edit_record())
        layout_proj.addWidget(self.table_proj)
        self.stack.addWidget(tab_proj)

        # Раздел 1: Конкурсы грантов
        tab_konk = QWidget()
        layout_konk = QVBoxLayout(tab_konk)
        layout_konk.setContentsMargins(0, 0, 0, 0)
        self.table_konk = QTableView()
        self.table_konk.setModel(self.model_konk)
        self.table_konk.setSortingEnabled(True)
        self.table_konk.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table_konk.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        layout_konk.addWidget(self.table_konk)
        self.stack.addWidget(tab_konk)

        # Раздел 2: Справочник вузов
        tab_vuz = QWidget()
        layout_vuz = QVBoxLayout(tab_vuz)
        layout_vuz.setContentsMargins(0, 0, 0, 0)
        self.table_vuz = QTableView()
        self.table_vuz.setModel(self.model_vuz)
        self.table_vuz.setSortingEnabled(True)
        self.table_vuz.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table_vuz.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        layout_vuz.addWidget(self.table_vuz)
        self.stack.addWidget(tab_vuz)

        # Раздел 3: Аналитические отчеты (ЛР №3)
        tab_reports = QWidget()
        layout_reports = QVBoxLayout(tab_reports)
        layout_reports.setContentsMargins(0, 4, 0, 0)
        layout_reports.setSpacing(6)

        rep_toolbar = QHBoxLayout()
        lbl_rep = QLabel("Форма аналитического отчета:")
        lbl_rep.setStyleSheet("font-weight: 500;")

        self.combo_report = QComboBox()
        self.combo_report.addItems([
            "Форма 1: Распределение проектов НИР по конкурсам грантов",
            "Форма 2: Распределение проектов НИР по вузам-исполнителям",
            "Форма 3: Распределение проектов НИР по субъектам РФ",
        ])
        self.combo_report.setMinimumWidth(420)
        self.combo_report.currentIndexChanged.connect(lambda _: self.refresh_current_report())

        rep_toolbar.addWidget(lbl_rep)
        rep_toolbar.addWidget(self.combo_report)
        rep_toolbar.addStretch()
        layout_reports.addLayout(rep_toolbar)

        self.report_table = QTableWidget()
        self.report_table.setAlternatingRowColors(True)
        self.report_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.report_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.report_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout_reports.addWidget(self.report_table)

        self.stack.addWidget(tab_reports)

        # Раздел 4: Финансирование
        tab_fin = QWidget()
        layout_fin = QVBoxLayout(tab_fin)
        layout_fin.setContentsMargins(0, 0, 0, 0)
        self.lbl_finance_stub = QLabel(
            "Раздел «Финансирование»\n\n"
            "Функции раздела:\n"
            "• Выпуск распоряжения по финансированию НИР\n"
            "• Формирование сводной ведомости выплат по вузам\n\n"
            "Раздел находится в разработке."
        )
        self.lbl_finance_stub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_finance_stub.setStyleSheet("font-size: 14px; color: #555; background: #fafafa; border: 1px dashed #ccc;")
        layout_fin.addWidget(self.lbl_finance_stub)
        self.stack.addWidget(tab_fin)

        main_layout.addWidget(self.stack)

        # Первичная настройка размеров столбцов
        self._adjust_table_columns(self.table_proj, self.model_proj, "gr_proj")
        self._adjust_table_columns(self.table_konk, self.model_konk, "gr_konk")
        self._adjust_table_columns(self.table_vuz, self.model_vuz, "vuz")

    def _init_statusbar(self):
        """Создание стандартной строки состояния Windows (Status Bar)."""
        self.status_bar = QStatusBar(self)
        self.setStatusBar(self.status_bar)

        self.lbl_db_info = QLabel("БД: grants.db (SQLite)")
        self.lbl_db_info.setStyleSheet("color: #666; padding-right: 10px;")
        self.status_bar.addPermanentWidget(self.lbl_db_info)

    def _adjust_table_columns(self, table_view: QTableView, model: QSqlTableModel, table_name: str):
        """Оптимальная подгонка ширины столбцов под заголовки и контент."""
        while model.canFetchMore():
            model.fetchMore()

        header = table_view.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(False)
        table_view.resizeColumnsToContents()

        fm = table_view.fontMetrics()
        for col in range(model.columnCount()):
            h_text = model.headerData(col, Qt.Orientation.Horizontal)
            h_width = fm.horizontalAdvance(str(h_text or "")) + 28
            c_width = table_view.columnWidth(col)
            target_width = max(h_width, c_width)

            if table_name == "gr_proj" and col == 16:  # Тема НИР
                target_width = max(target_width, 380)
            elif table_name == "vuz" and col in (9, 10):  # Наименования вузов
                target_width = max(target_width, 320)

            table_view.setColumnWidth(col, target_width)

    def _switch_section(self, index: int):
        """Переключение активного раздела системы."""
        self.stack.setCurrentIndex(index)

        section_names = {
            0: "Проекты НИР",
            1: "Конкурсы грантов",
            2: "Справочник вузов",
            3: "Аналитические отчеты",
            4: "Финансирование",
        }
        self.lbl_current_section.setText(section_names.get(index, "Раздел"))

        is_proj = (index == 0)
        is_reports = (index == 3)
        has_filter = bool(self.current_filter_where)

        # Контекстная доступность действий на панели инструментов
        if hasattr(self, "btn_add"):
            self.btn_add.setEnabled(is_proj)
            self.btn_edit.setEnabled(is_proj)
            self.btn_delete.setEnabled(is_proj)
            self.btn_key_sort.setEnabled(is_proj)
            self.btn_filter.setEnabled(is_proj or is_reports)
            self.btn_clear_filter.setVisible(has_filter)
            self.btn_clear_filter.setEnabled(has_filter)

        self.act_add.setEnabled(is_proj)
        self.act_edit.setEnabled(is_proj)
        self.act_delete.setEnabled(is_proj)
        self.act_key_sort.setEnabled(is_proj)
        self.act_filter.setEnabled(is_proj or is_reports)
        self.act_clear_filter.setVisible(has_filter)
        self.act_clear_filter.setEnabled(has_filter)

        if index == 0:
            self._update_status()
        elif index == 1:
            cnt = self.model_konk.rowCount()
            self.status_bar.showMessage(f"Конкурсы грантов: {cnt} записей")
        elif index == 2:
            cnt = self.model_vuz.rowCount()
            self.status_bar.showMessage(f"Справочник вузов: {cnt} записей")
        elif index == 3:
            self.refresh_current_report()
        elif index == 4:
            self.status_bar.showMessage("Раздел финансирования")

    def _switch_to_report(self, form_idx: int):
        """Прямой переход к нужной форме аналитического отчета из меню."""
        self._switch_section(3)
        self.combo_report.setCurrentIndex(form_idx)
        self.refresh_current_report()

    def _update_status(self):
        """Обновление строки состояния для таблицы проектов НИР."""
        if not hasattr(self, "status_bar"):
            return
        if self.stack.currentIndex() != 0:
            return
        count = self.model_proj.rowCount()
        if self.current_filter_where:
            self.status_bar.showMessage(f"Проекты НИР: {count} записей (фильтр: {self.current_filter_summary})")
        else:
            self.status_bar.showMessage(f"Проекты НИР: всего {count} записей (полная база)")

    def _sort_by_key(self):
        """Сортировка проектов по первичному составному ключу (Конкурс + Код НИР)."""
        if self.stack.currentIndex() != 0:
            return
        self.table_proj.horizontalHeader().setSortIndicator(-1, Qt.SortOrder.AscendingOrder)
        self.model_proj.setCustomOrder("codkon ASC, codproj ASC")
        while self.model_proj.canFetchMore():
            self.model_proj.fetchMore()
        self._update_status()

    def _on_add_record(self):
        """Добавление нового проекта НИР."""
        if self.stack.currentIndex() != 0:
            return

        default_codkon = 1
        sel = self.table_proj.selectionModel().selectedRows()
        if sel:
            rec = self.model_proj.record(sel[0].row())
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

            # Пересчет агрегатов конкурса
            cur.execute("""
                UPDATE gr_konk
                SET projects_count = projects_count + 1,
                    plan_fin = plan_fin + ?
                WHERE codkon = ?
            """, (d["plan_fin"], d["codkon"]))

            conn.commit()
            conn.close()

            # Обновление представлений
            self.model_proj.select()
            while self.model_proj.canFetchMore():
                self.model_proj.fetchMore()

            self.model_konk.select()

            # Автофокус на добавленную запись
            for r in range(self.model_proj.rowCount()):
                rec = self.model_proj.record(r)
                if rec.value("codkon") == d["codkon"] and rec.value("codproj") == d["codproj"]:
                    self.table_proj.selectRow(r)
                    self.table_proj.scrollTo(self.model_proj.index(r, 1))
                    break

            self._update_status()

    def _on_edit_record(self):
        """Редактирование выделенного проекта НИР."""
        if self.stack.currentIndex() != 0:
            return

        selection = self.table_proj.selectionModel().selectedRows()
        if not selection:
            QMessageBox.warning(self, "Внимание", "Пожалуйста, выделите строку проекта для редактирования.")
            return

        row_idx = selection[0].row()
        rec = self.model_proj.record(row_idx)

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

            # Синхронизация сумм и счетчиков конкурсов
            if old_codkon != new_codkon:
                cur.execute("""
                    UPDATE gr_konk
                    SET projects_count = projects_count - 1,
                        plan_fin = plan_fin - ?
                    WHERE codkon = ?
                """, (old_plan, old_codkon))
                cur.execute("""
                    UPDATE gr_konk
                    SET projects_count = projects_count + 1,
                        plan_fin = plan_fin + ?
                    WHERE codkon = ?
                """, (new_plan, new_codkon))
            else:
                plan_diff = new_plan - old_plan
                if plan_diff != 0:
                    cur.execute("""
                        UPDATE gr_konk
                        SET plan_fin = plan_fin + ?
                        WHERE codkon = ?
                    """, (plan_diff, new_codkon))

            conn.commit()
            conn.close()

            self.model_proj.select()
            while self.model_proj.canFetchMore():
                self.model_proj.fetchMore()

            self.model_konk.select()

            for r in range(self.model_proj.rowCount()):
                rec_r = self.model_proj.record(r)
                if rec_r.value("id") == record_data["id"]:
                    self.table_proj.selectRow(r)
                    self.table_proj.scrollTo(self.model_proj.index(r, 1))
                    break

            self._update_status()

    def _on_delete_record(self):
        """Удаление строго одной выделенной записи с подтверждением."""
        if self.stack.currentIndex() != 0:
            return

        selection = self.table_proj.selectionModel().selectedRows()
        if not selection:
            QMessageBox.warning(self, "Внимание", "Пожалуйста, выделите строку проекта для удаления.")
            return

        row_idx = selection[0].row()
        rec = self.model_proj.record(row_idx)
        proj_id = rec.value("id")
        codkon = rec.value("codkon")
        codproj = rec.value("codproj")
        leader_fio = rec.value("leader_fio")
        plan_fin = int(rec.value("plan_fin") or 0)

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

            self.model_proj.select()
            while self.model_proj.canFetchMore():
                self.model_proj.fetchMore()

            self.model_konk.select()
            self._update_status()

    def _on_filter(self):
        """Открытие диалогового окна сложной фильтрации."""
        dlg = FilterDialog(self, current_filters=self.current_filters, db_path=DB_PATH)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.current_filters = dlg.saved_filter_state
            self.current_filter_where = dlg.filter_where
            self.current_filter_summary = dlg.filter_summary

            # Применяем фильтр к проектам НИР
            self.model_proj.setFilter(self.current_filter_where)
            self.model_proj.select()
            while self.model_proj.canFetchMore():
                self.model_proj.fetchMore()

            has_flt = bool(self.current_filter_where)
            if hasattr(self, "btn_clear_filter"):
                self.btn_clear_filter.setVisible(has_flt)
                self.btn_clear_filter.setEnabled(has_flt)
            self.act_clear_filter.setVisible(has_flt)
            self.act_clear_filter.setEnabled(has_flt)

            if self.stack.currentIndex() == 3:
                self.refresh_current_report()
            else:
                self._update_status()

    def _on_clear_filter(self):
        """Сброс активного фильтра."""
        self.current_filters = {}
        self.current_filter_where = ""
        self.current_filter_summary = ""

        self.model_proj.setFilter("")
        self.model_proj.select()
        while self.model_proj.canFetchMore():
            self.model_proj.fetchMore()

        if hasattr(self, "btn_clear_filter"):
            self.btn_clear_filter.setVisible(False)
            self.btn_clear_filter.setEnabled(False)
        self.act_clear_filter.setVisible(False)
        self.act_clear_filter.setEnabled(False)

        if self.stack.currentIndex() == 3:
            self.refresh_current_report()
        else:
            self._update_status()

    def _on_refresh(self):
        """Обновление данных активной вкладки (F5)."""
        idx = self.stack.currentIndex()
        if idx == 0:
            self.model_proj.select()
            while self.model_proj.canFetchMore():
                self.model_proj.fetchMore()
            self._update_status()
        elif idx == 1:
            self.model_konk.select()
            while self.model_konk.canFetchMore():
                self.model_konk.fetchMore()
            self.status_bar.showMessage(f"Конкурсы грантов: {self.model_konk.rowCount()} записей")
        elif idx == 2:
            self.model_vuz.select()
            while self.model_vuz.canFetchMore():
                self.model_vuz.fetchMore()
            self.status_bar.showMessage(f"Справочник вузов: {self.model_vuz.rowCount()} записей")
        elif idx == 3:
            self.refresh_current_report()

    def refresh_current_report(self):
        """Формирование и отрисовка текущего аналитического отчета (ЛР №3)."""
        form_idx = self.combo_report.currentIndex()
        if form_idx == 0:
            report_data = build_contest_report(DB_PATH, self.current_filter_where)
        elif form_idx == 1:
            report_data = build_vuz_report(DB_PATH, self.current_filter_where)
        else:
            report_data = build_region_report(DB_PATH, self.current_filter_where)

        self.current_report_data = report_data
        self.render_report(report_data)

        if hasattr(self, "lbl_current_section") and self.stack.currentIndex() == 3:
            report_titles = {
                0: "Отчет: по конкурсам",
                1: "Отчет: по вузам",
                2: "Отчет: по регионам",
            }
            self.lbl_current_section.setText(report_titles.get(form_idx, "Аналитические отчеты"))

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

        # Данные отчета
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

        # Строка «ИТОГО»
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

        # Обновление строки состояния
        filter_str = f"фильтр: {self.current_filter_summary}" if self.current_filter_where else "полная база данных"
        self.status_bar.showMessage(f"Аналитический отчет сформирован: {len(rows)} строк ({filter_str})")

    def _on_save_as(self):
        """Универсальный экспорт активного документа (Ctrl+S)."""
        tab_idx = self.stack.currentIndex()

        if tab_idx == 3:  # Аналитические отчеты
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
                QMessageBox.information(self, "Экспорт завершен", f"Аналитический отчет успешно сохранен в файл:\n{file_path}")
            except Exception as e:
                QMessageBox.critical(self, "Ошибка сохранения", f"Не удалось сохранить отчет:\n{e}")

        elif tab_idx in (0, 1, 2):  # Таблицы БД
            info = {
                0: (self.model_proj, self.table_proj, "gr_proj", "Проекты НИР по грантам"),
                1: (self.model_konk, self.table_konk, "gr_konk", "Конкурсы грантов"),
                2: (self.model_vuz, self.table_vuz, "vuz", "Справочник вузов"),
            }[tab_idx]
            model, table_view, tbl_name, title = info
            default_name = f"{tbl_name}_export.xlsx"

            file_path, _ = QFileDialog.getSaveFileName(
                self,
                f"Сохранить таблицу «{title}» как...",
                default_name,
                "Таблица Excel (*.xlsx);;Веб-страница HTML (*.html);;Текстовый документ (*.txt);;Файл CSV (*.csv)"
            )
            if not file_path:
                return

            try:
                while model.canFetchMore():
                    model.fetchMore()
                visible_cols = [c for c in range(model.columnCount()) if not table_view.isColumnHidden(c)]
                headers = [str(model.headerData(c, Qt.Orientation.Horizontal) or f"Колонка {c}") for c in visible_cols]

                rows = []
                for r in range(model.rowCount()):
                    rec = model.record(r)
                    row_vals = [rec.value(c) if rec.value(c) is not None else "" for c in visible_cols]
                    rows.append(row_vals)

                money_cols = []
                numeric_cols = []
                if tbl_name == "gr_proj":
                    for idx, c in enumerate(visible_cols):
                        if c in (6, 7, 8, 9, 10, 11):
                            money_cols.append(idx)
                        elif c in (1, 2, 3):
                            numeric_cols.append(idx)
                elif tbl_name == "gr_konk":
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

                export_report_to_file(file_path, table_report_data, self.current_filter_summary if tbl_name == "gr_proj" else "")
                QMessageBox.information(self, "Экспорт завершен", f"Данные таблицы «{title}» успешно сохранены:\n{file_path}")
            except Exception as e:
                QMessageBox.critical(self, "Ошибка сохранения", f"Не удалось сохранить таблицу:\n{e}")
        else:
            QMessageBox.information(self, "Сохранить как...", "В данном разделе нет открытых документов для сохранения.")

    def _show_about(self):
        """Диалоговое окно «О программе»."""
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
