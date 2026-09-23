import sys
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtSql import QSqlTableModel
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTableView,
    QVBoxLayout,
    QWidget,
)

# Добавляем корень проекта и папку src в sys.path для любого способа запуска
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

try:
    from src.database import connect_db
except ModuleNotFoundError:
    from database import connect_db


class MainWindow(QMainWindow):
    """Главное окно приложения по Варианту 7."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("СУБД: Сопровождение конкурсов на соискание грантов (Вариант 7)")
        self.resize(1100, 650)

        # Модели данных
        self.current_model = None

        self._init_menu()
        self._init_ui()

        # По умолчанию открываем таблицу проектов НИР
        self.show_table("gr_proj")

    def _init_menu(self):
        """Создание главного меню приложения."""
        menubar = self.menuBar()

        # Меню "Данные"
        menu_data = menubar.addMenu("Данные")
        act_proj = menu_data.addAction("НИР по грантам")
        act_proj.triggered.connect(lambda: self.combo_view.setCurrentIndex(0))

        act_konk = menu_data.addAction("Конкурсы грантов")
        act_konk.triggered.connect(lambda: self.combo_view.setCurrentIndex(1))

        act_vuz = menu_data.addAction("Справочник вузов")
        act_vuz.triggered.connect(lambda: self.combo_view.setCurrentIndex(2))

        # Меню "Анализ"
        menu_analysis = menubar.addMenu("Анализ")
        act_an_vuz = menu_analysis.addAction("Распределение НИР по вузам")
        act_an_vuz.triggered.connect(lambda: self.combo_view.setCurrentIndex(3))

        act_an_konk = menu_analysis.addAction("Распределение НИР по конкурсам")
        act_an_konk.triggered.connect(lambda: self.combo_view.setCurrentIndex(3))

        act_an_reg = menu_analysis.addAction("Распределение НИР по регионам РФ")
        act_an_reg.triggered.connect(lambda: self.combo_view.setCurrentIndex(3))

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

        # 1. Верхняя панель: выбор текущего экрана/таблицы
        top_layout = QHBoxLayout()
        lbl_section = QLabel("Раздел системы:")
        lbl_section.setStyleSheet("font-weight: bold;")

        self.combo_view = QComboBox()
        self.combo_view.addItems([
            "Проекты НИР по грантам",
            "Конкурсы грантов",
            "Справочник вузов",
            "Анализ данных",
            "Финансирование",
        ])
        self.combo_view.currentIndexChanged.connect(self._on_section_changed)

        top_layout.addWidget(lbl_section)
        top_layout.addWidget(self.combo_view, stretch=1)
        main_layout.addLayout(top_layout)

        # 2. Центральная область (стек: таблицы данных или отчеты)
        self.stack = QStackedWidget()

        # Страница 0: Просмотр таблиц
        table_page = QWidget()
        table_layout = QVBoxLayout(table_page)
        table_layout.setContentsMargins(0, 5, 0, 5)

        self.table_view = QTableView()
        self.table_view.setSortingEnabled(True)  # Сортировка по клику на заголовок (из видео Мохова)
        self.table_view.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        table_layout.addWidget(self.table_view)

        # Кнопки CRUD
        buttons_layout = QHBoxLayout()
        btn_add = QPushButton("Добавить")
        btn_edit = QPushButton("Изменить")
        btn_delete = QPushButton("Удалить")
        btn_filter = QPushButton("Фильтр")

        btn_add.clicked.connect(lambda: self._show_stub("Добавление записи"))
        btn_edit.clicked.connect(lambda: self._show_stub("Редактирование записи"))
        btn_delete.clicked.connect(lambda: self._show_stub("Удаление записи"))
        btn_filter.clicked.connect(lambda: self._show_stub("Фильтрация данных"))

        buttons_layout.addWidget(btn_add)
        buttons_layout.addWidget(btn_edit)
        buttons_layout.addWidget(btn_delete)
        buttons_layout.addWidget(btn_filter)
        buttons_layout.addStretch()

        self.lbl_status = QLabel("Записей: 0")
        buttons_layout.addWidget(self.lbl_status)

        table_layout.addLayout(buttons_layout)
        self.stack.addWidget(table_page)

        # Страница 1: Раздел Анализ
        self.lbl_analysis_stub = QLabel(
            "Раздел «Анализ данных»\n\n"
            "Сводные отчетные формы:\n"
            "• Распределение НИР по вузам\n"
            "• Распределение НИР по конкурсам грантов\n"
            "• Распределение НИР по субъектам РФ\n\n"
            "Функция пока не реализована."
        )
        self.lbl_analysis_stub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_analysis_stub.setStyleSheet("font-size: 14px; color: #555; background: #f9f9f9; border: 1px dashed #ccc;")
        self.stack.addWidget(self.lbl_analysis_stub)

        # Страница 2: Раздел Финансирование
        self.lbl_finance_stub = QLabel(
            "Раздел «Финансирование»\n\n"
            "Функции раздела:\n"
            "• Выпуск распоряжения по финансированию НИР\n"
            "• Формирование сводной ведомости выплат по вузам\n\n"
            "Функция пока не реализована."
        )
        self.lbl_finance_stub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_finance_stub.setStyleSheet("font-size: 14px; color: #555; background: #f9f9f9; border: 1px dashed #ccc;")
        self.stack.addWidget(self.lbl_finance_stub)

        main_layout.addWidget(self.stack)

    def _on_section_changed(self, index: int):
        """Обработка переключения разделов."""
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
        elif index == 4:
            self.stack.setCurrentIndex(2)

    def show_table(self, table_name: str):
        """Отображение таблицы БД через стандартный QSqlTableModel."""
        self.current_model = QSqlTableModel(self)
        self.current_model.setTable(table_name)
        self.current_model.select()

        # Настраиваем читаемые русские заголовки
        if table_name == "gr_proj":
            headers = {
                1: "Код НИР",
                2: "Конкурс",
                3: "Код вуза",
                4: "Вуз",
                5: "ГРНТИ",
                6: "План (руб.)",
                7: "Факт (руб.)",
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
            for col, text in headers.items():
                self.current_model.setHeaderData(col, Qt.Orientation.Horizontal, text)

        elif table_name == "gr_konk":
            headers = {
                0: "Код конкурса",
                1: "Направление конкурса",
                2: "План финансирования (руб.)",
                3: "Факт финансирования (руб.)",
                4: "Квартал 1",
                5: "Квартал 2",
                6: "Квартал 3",
                7: "Квартал 4",
                8: "Число проектов",
            }
            for col, text in headers.items():
                self.current_model.setHeaderData(col, Qt.Orientation.Horizontal, text)

        elif table_name == "vuz":
            headers = {
                0: "Код вуза",
                1: "Наименование вуза",
                2: "Полное юридическое наименование",
                3: "Аббревиатура",
                4: "Статус",
                5: "Город",
                6: "Федеральный округ",
                7: "Код региона",
                8: "Субъект РФ",
                9: "Ведомство",
                10: "Профиль",
            }
            for col, text in headers.items():
                self.current_model.setHeaderData(col, Qt.Orientation.Horizontal, text)

        self.table_view.setModel(self.current_model)

        # Скрываем суррогатный id в таблице проектов
        if table_name == "gr_proj":
            self.table_view.hideColumn(0)

        # Подгружаем все строки для корректного счетчика записей
        while self.current_model.canFetchMore():
            self.current_model.fetchMore()

        self.lbl_status.setText(f"Всего записей: {self.current_model.rowCount()}")

    def _show_stub(self, action_name: str):
        """Информационное сообщение для еще не реализованных функций."""
        QMessageBox.information(
            self,
            "Информация",
            f"Функция «{action_name}» пока не реализована."
        )

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
            "Студенты: Грудинин Е., Степанищев В., Криштул А.\n"
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
