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

from src.database import connect_db


class MainWindow(QMainWindow):
    """Главное окно приложения-пустышки по Варианту 7."""

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

        # Меню "Анализ" (заглушка к ЛР 4)
        menu_analysis = menubar.addMenu("Анализ")
        act_an_vuz = menu_analysis.addAction("Распределение НИР по вузам")
        act_an_vuz.triggered.connect(lambda: self.combo_view.setCurrentIndex(3))

        act_an_konk = menu_analysis.addAction("Распределение НИР по конкурсам")
        act_an_konk.triggered.connect(lambda: self.combo_view.setCurrentIndex(3))

        act_an_reg = menu_analysis.addAction("Распределение НИР по регионам РФ")
        act_an_reg.triggered.connect(lambda: self.combo_view.setCurrentIndex(3))

        # Меню "Финансирование" (заглушка к ЛР 5)
        menu_finance = menubar.addMenu("Финансирование")
        act_fin_order = menu_finance.addAction("Выпуск распоряжения о финансировании")
        act_fin_order.triggered.connect(lambda: self.combo_view.setCurrentIndex(4))

        act_fin_ved = menu_finance.addAction("Ведомость выплат по вузам")
        act_fin_ved.triggered.connect(lambda: self.combo_view.setCurrentIndex(4))

        # Меню "Справка"
        menu_help = menubar.addMenu("Справка")
        act_about = menu_help.addAction("О программе")
        act_about.triggered.connect(self._show_about)

        # Меню "Выход"
        menu_exit = menubar.addMenu("Выход")
        act_exit = menu_exit.addAction("Закрыть приложение")
        act_exit.triggered.connect(self.close)

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
            "1. Данные: Проекты НИР по грантам",
            "1. Данные: Конкурсы грантов",
            "1. Данные: Справочник вузов РФ",
            "2. Анализ данных (Заглушка ЛР 4)",
            "3. Финансирование (Заглушка ЛР 5)",
        ])
        self.combo_view.currentIndexChanged.connect(self._on_section_changed)

        top_layout.addWidget(lbl_section)
        top_layout.addWidget(self.combo_view, stretch=1)
        main_layout.addLayout(top_layout)

        # 2. Центральная область (стек: таблицы данных или заглушки отчетов)
        self.stack = QStackedWidget()

        # Страница 0: Просмотр таблиц
        table_page = QWidget()
        table_layout = QVBoxLayout(table_page)
        table_layout.setContentsMargins(0, 5, 0, 5)

        self.table_view = QTableView()
        self.table_view.setSortingEnabled(True)  # Сортировка по клику на заголовок (из видео Мохова)
        self.table_view.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        table_layout.addWidget(self.table_view)

        # Кнопки CRUD (заглушки)
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

        # Страница 1: Заглушка раздела Анализ
        self.lbl_analysis_stub = QLabel(
            "Раздел «2. Анализ данных»\n\n"
            "Здесь будут реализованы сводные отчетные формы по ТЗ Варианта 7:\n"
            "• Распределение НИР по вузам\n"
            "• Распределение НИР по конкурсам грантов\n"
            "• Распределение НИР по субъектам РФ\n\n"
            "(Будет реализовано в ЛР №4)"
        )
        self.lbl_analysis_stub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_analysis_stub.setStyleSheet("font-size: 14px; color: #555; background: #f9f9f9; border: 1px dashed #ccc;")
        self.stack.addWidget(self.lbl_analysis_stub)

        # Страница 2: Заглушка раздела Финансирование
        self.lbl_finance_stub = QLabel(
            "Раздел «3. Финансирование»\n\n"
            "Здесь будут реализованы специальные функции Варианта 7:\n"
            "• Выпуск распоряжения по финансированию НИР\n"
            "• Формирование сводной ведомости выплат по вузам\n\n"
            "(Будет реализовано в ЛР №5)"
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
        """Информационное сообщение-заглушка."""
        QMessageBox.information(
            self,
            "Макет интерфейса",
            f"Функция «{action_name}» является элементом интерфейса-пустышки "
            "и будет реализована на этапе выполнения ЛР 2–3."
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
