import re
import sqlite3
from pathlib import Path
from PyQt6.QtCore import Qt, QRegularExpression
from PyQt6.QtGui import QIntValidator, QRegularExpressionValidator
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QLabel,
    QLineEdit,
    QComboBox,
    QTextEdit,
    QPushButton,
    QMessageBox,
    QGroupBox,
)


class GrntiLineEdit(QLineEdit):
    """Поле ввода ГРНТИ с автоматической расстановкой точек и запятых."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setPlaceholderText("Например: 55.22.01")
        self.textEdited.connect(self._on_text_edited)

    def _on_text_edited(self, text: str):
        # Оставляем только цифры (до 12 цифр для двух кодов ГРНТИ)
        digits = "".join(c for c in text if c.isdigit())[:12]
        formatted = ""
        for i, d in enumerate(digits):
            if i in (2, 4, 8, 10):
                formatted += "."
            elif i == 6:
                formatted += ", "
            formatted += d

        if formatted != text:
            cursor_pos = self.cursorPosition()
            diff = len(formatted) - len(text)
            self.setText(formatted)
            self.setCursorPosition(max(0, cursor_pos + diff))


class ProjectDialog(QDialog):
    """Модальное окно добавления / редактирования проекта НИР."""

    def __init__(self, parent=None, mode="add", record_data=None, default_codkon=1, db_path=None):
        super().__init__(parent)
        self.mode = mode
        self.record_data = record_data or {}
        self.default_codkon = default_codkon
        self.suggested_codproj = None
        self.db_path = db_path or Path(__file__).resolve().parent.parent / "databases" / "grants.db"

        title = "Добавление проекта НИР" if mode == "add" else "Редактирование проекта НИР"
        self.setWindowTitle(title)
        self.resize(650, 560)

        self._init_ui()
        self._load_reference_data()

        if self.mode == "edit":
            self._fill_existing_data()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)

        # 1. Группа "Конкурс и шифр НИР"
        grp_key = QGroupBox("Конкурс и шифр проекта")
        layout_key = QFormLayout(grp_key)

        self.combo_konk = QComboBox()
        self.combo_konk.currentIndexChanged.connect(self._on_contest_changed)

        self.txt_codproj = QLineEdit()
        self.txt_codproj.setValidator(QIntValidator(1, 999999, self))

        layout_key.addRow("Конкурс:", self.combo_konk)
        layout_key.addRow("Код НИР в конкурсе:", self.txt_codproj)
        main_layout.addWidget(grp_key)

        # 2. Группа "Исполнитель (Вуз)"
        grp_vuz = QGroupBox("Организация-исполнитель")
        layout_vuz = QFormLayout(grp_vuz)

        self.combo_vuz = QComboBox()
        layout_vuz.addRow("Вуз:", self.combo_vuz)
        main_layout.addWidget(grp_vuz)

        # 3. Группа "Руководитель НИР"
        grp_leader = QGroupBox("Руководитель НИР")
        layout_leader = QFormLayout(grp_leader)

        self.txt_leader_fio = QLineEdit()
        self.txt_leader_fio.setPlaceholderText("Иванов И.И.")

        self.txt_leader_post = QLineEdit()
        self.txt_leader_post.setPlaceholderText("Например: профессор")

        self.txt_leader_rank = QLineEdit()
        self.txt_leader_rank.setPlaceholderText("Например: доцент")

        self.txt_leader_degree = QLineEdit()
        self.txt_leader_degree.setPlaceholderText("Например: д.т.н.")

        layout_leader.addRow("Ф.И.О. руководителя:", self.txt_leader_fio)
        layout_leader.addRow("Должность:", self.txt_leader_post)
        layout_leader.addRow("Ученое звание:", self.txt_leader_rank)
        layout_leader.addRow("Ученая степень:", self.txt_leader_degree)
        main_layout.addWidget(grp_leader)

        # 4. Группа "Тематика и финансирование"
        grp_details = QGroupBox("Сведения о проекте")
        layout_details = QFormLayout(grp_details)

        self.txt_proj_name = QTextEdit()
        self.txt_proj_name.setMaximumHeight(70)
        self.txt_proj_name.setPlaceholderText("Наименование темы исследования")

        self.txt_grnti = GrntiLineEdit()

        self.txt_plan_fin = QLineEdit()
        self.txt_plan_fin.setValidator(QIntValidator(0, 1000000000, self))
        self.txt_plan_fin.setPlaceholderText("Целое число")

        layout_details.addRow("Тема НИР:", self.txt_proj_name)
        layout_details.addRow("Рубрикатор ГРНТИ:", self.txt_grnti)
        layout_details.addRow("План финансирования:", self.txt_plan_fin)
        main_layout.addWidget(grp_details)

        # Кнопки диалога
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.btn_save = QPushButton("Сохранить")
        self.btn_save.setStyleSheet("font-weight: bold; padding: 6px 16px;")
        self.btn_save.clicked.connect(self._on_save)

        self.btn_cancel = QPushButton("Отмена")
        self.btn_cancel.clicked.connect(self.reject)

        btn_layout.addWidget(self.btn_save)
        btn_layout.addWidget(self.btn_cancel)
        main_layout.addLayout(btn_layout)

    def _load_reference_data(self):
        """Загрузка справочников конкурсов и вузов."""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        # 1. Конкурсы
        self.combo_konk.blockSignals(True)
        self.combo_konk.clear()

        cur.execute("SELECT codkon, konk_name FROM gr_konk ORDER BY codkon")
        selected_idx = 0
        for i, (codkon, name) in enumerate(cur.fetchall()):
            self.combo_konk.addItem(f"{codkon}: {name}", userData=codkon)
            if codkon == self.default_codkon:
                selected_idx = i

        self.combo_konk.setCurrentIndex(selected_idx)
        self.combo_konk.blockSignals(False)

        # Рассчитываем рекомендуемый номер для выбранного конкурса в качестве подсказки
        if self.mode == "add":
            active_codkon = self.combo_konk.currentData() or 1
            cur.execute("SELECT COALESCE(MAX(codproj), 0) FROM gr_proj WHERE codkon = ?", (active_codkon,))
            max_cod = cur.fetchone()[0]
            self.suggested_codproj = max_cod + 1
            self.txt_codproj.clear()
            self.txt_codproj.setPlaceholderText(str(self.suggested_codproj))

        # 2. Вузы (по дефолту пустой выбор)
        self.combo_vuz.clear()
        self.combo_vuz.addItem("", userData=(None, ""))

        cur.execute("SELECT codvuz, vuz_short_name, vuz_name FROM vuz ORDER BY vuz_short_name")
        for codvuz, short_name, full_name in cur.fetchall():
            label = f"{short_name} — {full_name}" if full_name else short_name
            self.combo_vuz.addItem(label, userData=(codvuz, short_name))
        self.combo_vuz.setCurrentIndex(0)
        conn.close()

    def _on_contest_changed(self, index: int):
        """При выборе конкурса предлагаем следующий порядковый номер (MAX + 1)."""
        if self.mode != "add":
            return

        codkon = self.combo_konk.currentData()
        if not codkon:
            self.suggested_codproj = None
            self.txt_codproj.clear()
            self.txt_codproj.setPlaceholderText("")
            return

        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT COALESCE(MAX(codproj), 0) FROM gr_proj WHERE codkon = ?", (codkon,))
        max_cod = cur.fetchone()[0]
        conn.close()

        self.suggested_codproj = max_cod + 1
        self.txt_codproj.clear()
        self.txt_codproj.setPlaceholderText(str(self.suggested_codproj))

    def _fill_existing_data(self):
        """Предзаполнение полей при редактировании записи."""
        data = self.record_data

        # Конкурс
        codkon = data.get("codkon")
        for i in range(self.combo_konk.count()):
            if self.combo_konk.itemData(i) == codkon:
                self.combo_konk.setCurrentIndex(i)
                break
        self.combo_konk.setEnabled(False)  # Код конкурса в существующем проекте не меняем

        # Код НИР
        self.txt_codproj.setText(str(data.get("codproj", "")))
        self.txt_codproj.setEnabled(False)

        # Вуз
        codvuz = data.get("codvuz")
        for i in range(self.combo_vuz.count()):
            vdata = self.combo_vuz.itemData(i)
            if vdata and vdata[0] == codvuz:
                self.combo_vuz.setCurrentIndex(i)
                break

        # Руководитель
        self.txt_leader_fio.setText(str(data.get("leader_fio", "")))
        self.txt_leader_post.setText(str(data.get("leader_post", "")))
        self.txt_leader_rank.setText(str(data.get("leader_rank", "")))
        self.txt_leader_degree.setText(str(data.get("leader_degree", "")))

        # Тема, ГРНТИ, План
        self.txt_proj_name.setPlainText(str(data.get("proj_name", "")))
        self.txt_grnti.setText(str(data.get("grnti_code", "")))
        self.txt_plan_fin.setText(str(data.get("plan_fin", 0)))

    def _on_save(self):
        """Проверка введенных данных и сохранение."""
        codkon = self.combo_konk.currentData()
        if not codkon:
            QMessageBox.warning(self, "Ошибка ввода", "Пожалуйста, выберите конкурс из списка.")
            self.combo_konk.setFocus()
            return

        codproj_text = self.txt_codproj.text().strip()
        if not codproj_text:
            if self.suggested_codproj:
                codproj = self.suggested_codproj
            else:
                QMessageBox.warning(self, "Ошибка ввода", "Укажите номер проекта в конкурсе.")
                self.txt_codproj.setFocus()
                return
        else:
            if not codproj_text.isdigit() or int(codproj_text) <= 0:
                QMessageBox.warning(self, "Ошибка ввода", "Укажите корректный положительный номер проекта.")
                self.txt_codproj.setFocus()
                return
            codproj = int(codproj_text)

        # Проверка уникальности составного ключа (codkon, codproj) при добавлении
        if self.mode == "add":
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM gr_proj WHERE codkon = ? AND codproj = ?", (codkon, codproj))
            exists = cur.fetchone()[0] > 0
            conn.close()

            if exists:
                QMessageBox.warning(
                    self,
                    "Дубликат ключа",
                    f"Проект с кодом {codproj} в конкурсе №{codkon} уже существует!\n"
                    "Укажите другой номер проекта."
                )
                self.txt_codproj.setFocus()
                return

        vuz_info = self.combo_vuz.currentData()
        if not vuz_info or not vuz_info[0]:
            QMessageBox.warning(self, "Ошибка ввода", "Пожалуйста, выберите вуз-исполнитель из списка.")
            self.combo_vuz.setFocus()
            return
        codvuz, vuz_short_name = vuz_info

        leader_fio = self.txt_leader_fio.text().strip()
        if not leader_fio:
            QMessageBox.warning(self, "Ошибка ввода", "Пожалуйста, укажите Ф.И.О. руководителя НИР.")
            self.txt_leader_fio.setFocus()
            return

        proj_name = self.txt_proj_name.toPlainText().strip()
        if not proj_name:
            QMessageBox.warning(self, "Ошибка ввода", "Пожалуйста, укажите наименование темы НИР.")
            self.txt_proj_name.setFocus()
            return

        grnti = self.txt_grnti.text().strip()
        if not re.fullmatch(r"^\d{2}\.\d{2}\.\d{2}(?:,\s*\d{2}\.\d{2}\.\d{2})?$", grnti):
            QMessageBox.warning(
                self,
                "Ошибка формата ГРНТИ",
                "Код ГРНТИ должен иметь формат XX.YY.ZZ\n(или два кода через запятую: XX.YY.ZZ, AA.BB.CC)."
            )
            self.txt_grnti.setFocus()
            return

        plan_fin_text = self.txt_plan_fin.text().strip()
        plan_fin = int(plan_fin_text) if plan_fin_text.isdigit() else 0

        # Собираем итоговые проверенные данные
        self.result_data = {
            "codkon": codkon,
            "codproj": codproj,
            "codvuz": codvuz,
            "vuz_short_name": vuz_short_name,
            "leader_fio": leader_fio,
            "leader_post": self.txt_leader_post.text().strip(),
            "leader_rank": self.txt_leader_rank.text().strip(),
            "leader_degree": self.txt_leader_degree.text().strip(),
            "proj_name": proj_name,
            "grnti_code": grnti,
            "plan_fin": plan_fin,
        }

        self.accept()


class FilterDialog(QDialog):
    """Модальное окно сложной фильтрации: Географический фильтр + Фильтр по конкурсу."""

    def __init__(self, parent=None, current_filters=None, db_path=None):
        super().__init__(parent)
        self.db_path = db_path or Path(__file__).resolve().parent.parent / "databases" / "grants.db"
        self.current_filters = current_filters or {}
        self.filter_where = ""
        self.filter_summary = ""

        self.setWindowTitle("Фильтрация проектов НИР")
        self.resize(550, 420)

        self._init_ui()
        self._load_data()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)

        # 1. Фильтр по конкурсу
        grp_konk = QGroupBox("Фильтр по конкурсу грантов")
        layout_konk = QFormLayout(grp_konk)
        self.combo_konk = QComboBox()
        layout_konk.addRow("Конкурс:", self.combo_konk)
        main_layout.addWidget(grp_konk)

        # 2. Географический фильтр (иерархический: Округ -> Субъект -> Город -> Вуз)
        grp_geo = QGroupBox("Географический фильтр (по вузам)")
        layout_geo = QFormLayout(grp_geo)

        self.combo_region = QComboBox()
        self.combo_obl = QComboBox()
        self.combo_city = QComboBox()
        self.combo_vuz = QComboBox()

        self.combo_region.currentIndexChanged.connect(self._on_region_changed)
        self.combo_obl.currentIndexChanged.connect(self._on_obl_changed)
        self.combo_city.currentIndexChanged.connect(self._on_city_changed)
        self.combo_vuz.currentIndexChanged.connect(self._on_vuz_changed)

        layout_geo.addRow("Федеральный округ:", self.combo_region)
        layout_geo.addRow("Субъект РФ:", self.combo_obl)
        layout_geo.addRow("Город:", self.combo_city)
        layout_geo.addRow("Вуз:", self.combo_vuz)
        main_layout.addWidget(grp_geo)

        # Кнопки
        btn_layout = QHBoxLayout()

        self.btn_reset = QPushButton("Снять фильтр")
        self.btn_reset.clicked.connect(self._on_reset)

        self.btn_apply = QPushButton("Применить")
        self.btn_apply.setStyleSheet("font-weight: bold; padding: 6px 14px;")
        self.btn_apply.clicked.connect(self._on_apply)

        self.btn_cancel = QPushButton("Отмена")
        self.btn_cancel.clicked.connect(self.reject)

        btn_layout.addWidget(self.btn_reset)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_apply)
        btn_layout.addWidget(self.btn_cancel)
        main_layout.addLayout(btn_layout)

    def _load_data(self):
        """Первоначальная загрузка всех справочных данных."""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        # Конкурсы (первый элемент - пустой выбор)
        self.combo_konk.clear()
        self.combo_konk.addItem("", userData=None)
        cur.execute("SELECT codkon, konk_name FROM gr_konk ORDER BY codkon")
        for ck, name in cur.fetchall():
            self.combo_konk.addItem(f"{ck}: {name}", userData=ck)

        # Загрузка базы вузов для каскадной фильтрации
        cur.execute("SELECT codvuz, vuz_short_name, region, obl_name, city FROM vuz ORDER BY vuz_short_name")
        self.all_vuz = cur.fetchall()
        conn.close()

        self._populate_geo_combos()

        # Восстановление текущих выбранных фильтров, если они переданы
        if self.current_filters:
            self._restore_current_filters()

    def _populate_geo_combos(self):
        """Заполнение географических комбобоксов с пустым дефолтным выбором."""
        self._block_geo_signals(True)

        # 1. Округа
        regions = sorted(list(set(r[2] for r in self.all_vuz if r[2])))
        self.combo_region.clear()
        self.combo_region.addItem("")
        for reg in regions:
            self.combo_region.addItem(reg)

        # 2. Субъекты
        obls = sorted(list(set(r[3] for r in self.all_vuz if r[3])))
        self.combo_obl.clear()
        self.combo_obl.addItem("")
        for obl in obls:
            self.combo_obl.addItem(obl)

        # 3. Города
        cities = sorted(list(set(r[4] for r in self.all_vuz if r[4])))
        self.combo_city.clear()
        self.combo_city.addItem("")
        for c in cities:
            self.combo_city.addItem(c)

        # 4. Вузы
        self.combo_vuz.clear()
        self.combo_vuz.addItem("", userData=None)
        for codvuz, short_name, _, _, _ in sorted(self.all_vuz, key=lambda x: x[1].lower()):
            self.combo_vuz.addItem(short_name, userData=codvuz)

        self._block_geo_signals(False)

    def _block_geo_signals(self, block: bool):
        self.combo_region.blockSignals(block)
        self.combo_obl.blockSignals(block)
        self.combo_city.blockSignals(block)
        self.combo_vuz.blockSignals(block)

    def _on_region_changed(self):
        """При выборе округа фильтруем нижележащие списки."""
        region = self.combo_region.currentText().strip()
        self._block_geo_signals(True)

        filtered = [r for r in self.all_vuz if (not region or r[2] == region)]

        # Обновляем субъекты
        current_obl = self.combo_obl.currentText()
        obls = sorted(list(set(r[3] for r in filtered if r[3])))
        self.combo_obl.clear()
        self.combo_obl.addItem("")
        for obl in obls:
            self.combo_obl.addItem(obl)
        if current_obl in obls:
            self.combo_obl.setCurrentText(current_obl)

        # Обновляем города
        current_city = self.combo_city.currentText()
        cities = sorted(list(set(r[4] for r in filtered if r[4])))
        self.combo_city.clear()
        self.combo_city.addItem("")
        for c in cities:
            self.combo_city.addItem(c)
        if current_city in cities:
            self.combo_city.setCurrentText(current_city)

        # Обновляем вузы
        current_vuz_id = self.combo_vuz.currentData()
        self.combo_vuz.clear()
        self.combo_vuz.addItem("", userData=None)
        for codvuz, short_name, _, _, _ in sorted(filtered, key=lambda x: x[1].lower()):
            self.combo_vuz.addItem(short_name, userData=codvuz)
            if codvuz == current_vuz_id:
                self.combo_vuz.setCurrentIndex(self.combo_vuz.count() - 1)

        self._block_geo_signals(False)

    def _on_obl_changed(self):
        """При выборе субъекта подставляем округ и фильтруем города/вузы."""
        obl = self.combo_obl.currentText().strip()
        self._block_geo_signals(True)

        if obl:
            # Находим округ для выбранного субъекта
            for r in self.all_vuz:
                if r[3] == obl and r[2]:
                    self.combo_region.setCurrentText(r[2])
                    break
            filtered = [r for r in self.all_vuz if r[3] == obl]
        else:
            region = self.combo_region.currentText().strip()
            filtered = [r for r in self.all_vuz if (not region or r[2] == region)]

        # Обновляем города
        current_city = self.combo_city.currentText()
        cities = sorted(list(set(r[4] for r in filtered if r[4])))
        self.combo_city.clear()
        self.combo_city.addItem("")
        for c in cities:
            self.combo_city.addItem(c)
        if current_city in cities:
            self.combo_city.setCurrentText(current_city)

        # Обновляем вузы
        current_vuz_id = self.combo_vuz.currentData()
        self.combo_vuz.clear()
        self.combo_vuz.addItem("", userData=None)
        for codvuz, short_name, _, _, _ in sorted(filtered, key=lambda x: x[1].lower()):
            self.combo_vuz.addItem(short_name, userData=codvuz)
            if codvuz == current_vuz_id:
                self.combo_vuz.setCurrentIndex(self.combo_vuz.count() - 1)

        self._block_geo_signals(False)

    def _on_city_changed(self):
        """При выборе города подставляем субъект и округ."""
        city = self.combo_city.currentText().strip()
        self._block_geo_signals(True)

        if city:
            for r in self.all_vuz:
                if r[4] == city:
                    if r[3]:
                        self.combo_obl.setCurrentText(r[3])
                    if r[2]:
                        self.combo_region.setCurrentText(r[2])
                    break
            filtered = [r for r in self.all_vuz if r[4] == city]
        else:
            obl = self.combo_obl.currentText().strip()
            region = self.combo_region.currentText().strip()
            filtered = [r for r in self.all_vuz if ((not obl or r[3] == obl) and (not region or r[2] == region))]

        # Обновляем вузы
        current_vuz_id = self.combo_vuz.currentData()
        self.combo_vuz.clear()
        self.combo_vuz.addItem("", userData=None)
        for codvuz, short_name, _, _, _ in sorted(filtered, key=lambda x: x[1].lower()):
            self.combo_vuz.addItem(short_name, userData=codvuz)
            if codvuz == current_vuz_id:
                self.combo_vuz.setCurrentIndex(self.combo_vuz.count() - 1)

        self._block_geo_signals(False)

    def _on_vuz_changed(self):
        """При выборе вуза автоматически выставляем его город, субъект и округ."""
        codvuz = self.combo_vuz.currentData()
        if not codvuz:
            return

        self._block_geo_signals(True)
        for r in self.all_vuz:
            if r[0] == codvuz:
                if r[2]:
                    self.combo_region.setCurrentText(r[2])
                if r[3]:
                    self.combo_obl.setCurrentText(r[3])
                if r[4]:
                    self.combo_city.setCurrentText(r[4])
                break
        self._block_geo_signals(False)

    def _restore_current_filters(self):
        """Восстановление ранее выбранных фильтров."""
        cf = self.current_filters
        if cf.get("codkon"):
            for i in range(self.combo_konk.count()):
                if self.combo_konk.itemData(i) == cf["codkon"]:
                    self.combo_konk.setCurrentIndex(i)
                    break

        if cf.get("codvuz"):
            self.combo_vuz.setCurrentIndex(0)
            for i in range(self.combo_vuz.count()):
                if self.combo_vuz.itemData(i) == cf["codvuz"]:
                    self.combo_vuz.setCurrentIndex(i)
                    self._on_vuz_changed()
                    break
        elif cf.get("city"):
            self.combo_city.setCurrentText(cf["city"])
            self._on_city_changed()
        elif cf.get("obl_name"):
            self.combo_obl.setCurrentText(cf["obl_name"])
            self._on_obl_changed()
        elif cf.get("region"):
            self.combo_region.setCurrentText(cf["region"])
            self._on_region_changed()

    def _on_reset(self):
        """Сброс всех фильтров."""
        self.filter_where = ""
        self.filter_summary = ""
        self.saved_filter_state = {}
        self.accept()

    def _on_apply(self):
        """Формирование SQL-условия фильтрации."""
        clauses = []
        labels = []

        # 1. Конкурс
        codkon = self.combo_konk.currentData()
        if codkon:
            clauses.append(f"codkon = {codkon}")
            labels.append(f"Конкурс №{codkon}")

        # 2. География
        codvuz = self.combo_vuz.currentData()
        city = self.combo_city.currentText().strip()
        obl = self.combo_obl.currentText().strip()
        region = self.combo_region.currentText().strip()

        if codvuz:
            clauses.append(f"codvuz = {codvuz}")
            labels.append(f"Вуз: {self.combo_vuz.currentText()}")
        elif city:
            safe_city = city.replace("'", "''")
            clauses.append(f"codvuz IN (SELECT codvuz FROM vuz WHERE city = '{safe_city}')")
            labels.append(f"Город: {city}")
        elif obl:
            safe_obl = obl.replace("'", "''")
            clauses.append(f"codvuz IN (SELECT codvuz FROM vuz WHERE obl_name = '{safe_obl}')")
            labels.append(f"Субъект: {obl}")
        elif region:
            safe_reg = region.replace("'", "''")
            clauses.append(f"codvuz IN (SELECT codvuz FROM vuz WHERE region = '{safe_reg}')")
            labels.append(f"Округ: {region}")

        self.filter_where = " AND ".join(clauses) if clauses else ""
        self.filter_summary = ", ".join(labels) if labels else ""
        self.saved_filter_state = {
            "codkon": codkon,
            "codvuz": codvuz,
            "city": city,
            "obl_name": obl,
            "region": region,
        }

        self.accept()
