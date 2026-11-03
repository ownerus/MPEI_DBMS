"""
Модуль «Финансирование» (Лабораторная работа №4).
Реализация алгоритма выпуска распоряжения о финансировании,
пропорционального распределения средств по проектам НИР,
формирования сводной ведомости выплат по вузам и проведения транша в БД.
"""

import sqlite3
from pathlib import Path
from datetime import datetime

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QDoubleSpinBox,
    QComboBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QFileDialog,
    QMessageBox,
    QFrame,
)

from src.database import DB_PATH, sync_contest_aggregates
from src.reports import export_report_to_file


def get_finance_summary(db_path: Path = None) -> dict:
    """Получение агрегированных показателей системы для справочного блока."""
    target_path = str(db_path or DB_PATH)
    conn = sqlite3.connect(target_path)
    cur = conn.cursor()

    row = cur.execute("""
        SELECT 
            COUNT(DISTINCT codvuz),
            COUNT(*),
            COALESCE(SUM(plan_fin), 0),
            COALESCE(SUM(fact_fin), 0),
            COALESCE(SUM(fin_q1), 0),
            COALESCE(SUM(fin_q2), 0),
            COALESCE(SUM(fin_q3), 0),
            COALESCE(SUM(fin_q4), 0)
        FROM gr_proj
    """).fetchone()

    conn.close()

    total_vuz = row[0] or 0
    total_proj = row[1] or 0
    total_plan = row[2] or 0
    total_fact = row[3] or 0
    q1 = row[4] or 0
    q2 = row[5] or 0
    q3 = row[6] or 0
    q4 = row[7] or 0

    fact_pct = (total_fact / total_plan * 100.0) if total_plan > 0 else 0.0

    return {
        "total_vuz": total_vuz,
        "total_proj": total_proj,
        "total_plan": total_plan,
        "total_fact": total_fact,
        "fact_pct": fact_pct,
        "q1": q1,
        "q2": q2,
        "q3": q3,
        "q4": q4,
    }


def calculate_tranche_distribution(percent: float, db_path: Path = None) -> dict:
    """
    Расчет пропорционального распределения транша по проектам НИР
    и формирование проекта ведомости выплат по вузам.
    """
    target_path = str(db_path or DB_PATH)
    conn = sqlite3.connect(target_path)
    cur = conn.cursor()

    # Загружаем проекты и справочные данные вузов
    sql = """
        SELECT 
            p.id,
            p.codkon,
            p.codproj,
            p.codvuz,
            p.plan_fin,
            v.vuz_short_name,
            v.city
        FROM gr_proj p
        LEFT JOIN vuz v ON p.codvuz = v.codvuz
        ORDER BY p.codvuz, p.codkon, p.codproj
    """
    projects = cur.execute(sql).fetchall()
    conn.close()

    total_plan = sum(p[4] for p in projects)
    pct_fraction = percent / 100.0

    project_tranches = []
    vuz_map = {}

    for p in projects:
        p_id, codkon, codproj, codvuz, plan_fin, vuz_short, city = p
        # Округление до целого рубля по каждому проекту
        p_tranche = int(round(plan_fin * pct_fraction))
        project_tranches.append((p_id, p_tranche))

        vuz_key = codvuz
        if vuz_key not in vuz_map:
            vuz_map[vuz_key] = {
                "codvuz": codvuz,
                "vuz_short_name": vuz_short or f"Вуз #{codvuz}",
                "city": city or "",
                "proj_count": 0,
                "plan_sum": 0,
                "tranche_sum": 0,
            }
        vuz_map[vuz_key]["proj_count"] += 1
        vuz_map[vuz_key]["plan_sum"] += plan_fin
        vuz_map[vuz_key]["tranche_sum"] += p_tranche

    vuz_rows = sorted(vuz_map.values(), key=lambda x: x["codvuz"])
    total_distributed = sum(p[1] for p in project_tranches)
    total_proj_count = len(project_tranches)

    return {
        "percent": percent,
        "total_plan": total_plan,
        "total_distributed": total_distributed,
        "total_proj_count": total_proj_count,
        "project_tranches": project_tranches,
        "vuz_rows": vuz_rows,
    }


def execute_tranche_in_db(quarter: int, project_tranches: list, db_path: Path = None):
    """
    Фиксация утвержденного распоряжения в базе данных:
    поквартальное обновление fin_qX и fact_fin в gr_proj + синхронизация gr_konk.
    """
    target_path = str(db_path or DB_PATH)
    conn = sqlite3.connect(target_path)
    cur = conn.cursor()

    col_q = f"fin_q{quarter}"
    cur.execute("BEGIN TRANSACTION")
    for p_id, tranche_val in project_tranches:
        cur.execute(f"""
            UPDATE gr_proj
            SET {col_q} = {col_q} + ?,
                fact_fin = fact_fin + ?
            WHERE id = ?
        """, (tranche_val, tranche_val, p_id))

    conn.commit()
    conn.close()

    # Синхронизация агрегатов таблицы конкурсов
    sync_contest_aggregates(target_path)


def reset_quarter_funding(quarter: int, db_path: Path = None):
    """
    Очистка фактического финансирования выбранного квартала (сброс в 0).
    Уменьшает fact_fin на сумму выплат этого квартала и синхронизирует таблицу gr_konk.
    """
    target_path = str(db_path or DB_PATH)
    conn = sqlite3.connect(target_path)
    cur = conn.cursor()

    col_q = f"fin_q{quarter}"
    cur.execute("BEGIN TRANSACTION")
    cur.execute(f"""
        UPDATE gr_proj
        SET fact_fin = MAX(0, fact_fin - {col_q}),
            {col_q} = 0
    """)
    conn.commit()
    conn.close()

    sync_contest_aggregates(target_path)


class FinanceWidget(QWidget):
    """Экранная форма раздела «Финансирование» (ЛР №4)."""

    data_updated = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.calculated_data = None
        self._init_ui()
        self.refresh_summary()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 6, 8, 6)
        main_layout.setSpacing(6)

        # 1. Справочный блок исходного состояния базы данных
        group_summary = QGroupBox("Текущее состояние финансирования (исходные данные БД)")
        group_summary.setStyleSheet("""
            QGroupBox {
                font-weight: 600;
                font-size: 12px;
                border: 1px solid rgba(128, 128, 128, 0.35);
                border-radius: 4px;
                margin-top: 6px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
            }
        """)
        layout_sum = QGridLayout(group_summary)
        layout_sum.setContentsMargins(10, 8, 10, 8)
        layout_sum.setHorizontalSpacing(20)
        layout_sum.setVerticalSpacing(4)

        self.lbl_val_vuz = QLabel("0")
        self.lbl_val_proj = QLabel("0")
        self.lbl_val_plan = QLabel("0 руб.")
        self.lbl_val_fact = QLabel("0 руб. (0.0%)")
        self.lbl_val_quarters = QLabel("1 кв: 0 | 2 кв: 0 | 3 кв: 0 | 4 кв: 0")

        lbl_title_vuz = QLabel("Вузов-исполнителей:")
        lbl_title_proj = QLabel("Проектов НИР:")
        lbl_title_plan = QLabel("Суммарный план:")
        lbl_title_fact = QLabel("Фактически профинансировано:")
        lbl_title_q = QLabel("Поквартальный факт:")

        for lbl in (lbl_title_vuz, lbl_title_proj, lbl_title_plan, lbl_title_fact, lbl_title_q):
            lbl.setStyleSheet("color: #888;")

        for val_lbl in (self.lbl_val_vuz, self.lbl_val_proj, self.lbl_val_plan, self.lbl_val_fact):
            val_lbl.setStyleSheet("font-weight: 600;")

        layout_sum.addWidget(lbl_title_vuz, 0, 0)
        layout_sum.addWidget(self.lbl_val_vuz, 0, 1)
        layout_sum.addWidget(lbl_title_proj, 0, 2)
        layout_sum.addWidget(self.lbl_val_proj, 0, 3)

        layout_sum.addWidget(lbl_title_plan, 1, 0)
        layout_sum.addWidget(self.lbl_val_plan, 1, 1)
        layout_sum.addWidget(lbl_title_fact, 1, 2)
        layout_sum.addWidget(self.lbl_val_fact, 1, 3)

        layout_sum.addWidget(lbl_title_q, 2, 0)
        layout_sum.addWidget(self.lbl_val_quarters, 2, 1, 1, 3)

        main_layout.addWidget(group_summary)

        # 2. Блок параметров транша финансирования
        group_params = QGroupBox("Параметры выпуска распоряжения о финансировании")
        group_params.setStyleSheet(group_summary.styleSheet())
        layout_params = QHBoxLayout(group_params)
        layout_params.setContentsMargins(10, 8, 10, 8)
        layout_params.setSpacing(10)

        layout_params.addWidget(QLabel("Сумма к распределению (руб.):"))
        self.edit_sum = QLineEdit()
        self.edit_sum.setPlaceholderText("Например: 50317500")
        self.edit_sum.setMaximumWidth(160)
        layout_params.addWidget(self.edit_sum)

        layout_params.addWidget(QLabel("ИЛИ Процент от плана (%):"))
        self.spin_pct = QDoubleSpinBox()
        self.spin_pct.setRange(0.01, 100.0)
        self.spin_pct.setDecimals(2)
        self.spin_pct.setSingleStep(5.0)
        self.spin_pct.setValue(25.0)
        self.spin_pct.setSuffix(" %")
        self.spin_pct.setMaximumWidth(110)
        layout_params.addWidget(self.spin_pct)

        layout_params.addWidget(QLabel("Квартал:"))
        self.combo_quarter = QComboBox()
        self.combo_quarter.addItems(["1-й квартал", "2-й квартал", "3-й квартал", "4-й квартал"])
        self.combo_quarter.setMaximumWidth(130)
        layout_params.addWidget(self.combo_quarter)

        self.btn_calculate = QPushButton("Рассчитать")
        self.btn_calculate.setStyleSheet("font-weight: 600; padding: 4px 14px;")
        layout_params.addWidget(self.btn_calculate)

        self.btn_cancel = QPushButton("Отмена")
        self.btn_cancel.setStyleSheet("padding: 4px 12px;")
        self.btn_cancel.setToolTip("Сбросить текущий предварительный расчет и очистить форму")
        layout_params.addWidget(self.btn_cancel)

        self.btn_reset_quarter = QPushButton("Очистить квартал...")
        self.btn_reset_quarter.setStyleSheet("padding: 4px 12px; color: #d97768;")
        self.btn_reset_quarter.setToolTip("Обнулить проведённые выплаты выбранного квартала в базе данных")
        self.btn_reset_quarter.clicked.connect(self._on_reset_quarter)
        layout_params.addWidget(self.btn_reset_quarter)

        layout_params.addStretch()
        main_layout.addWidget(group_params)

        # Двусторонняя связь полей «Сумма» <-> «Процент»
        self.edit_sum.textEdited.connect(self._on_sum_edited)
        self.spin_pct.valueChanged.connect(self._on_percent_changed)
        self.btn_calculate.clicked.connect(self._on_calculate)
        self.btn_cancel.clicked.connect(self._on_cancel)

        # 3. Таблица сводной ведомости выплат по вузам
        self.table_ved = QTableWidget()
        self.table_ved.setColumnCount(6)
        self.table_ved.setHorizontalHeaderLabels([
            "№ п/п",
            "Код вуза",
            "Вуз-исполнитель",
            "Город",
            "Количество НИР",
            "Сумма выплат (руб.)",
        ])
        self.table_ved.setAlternatingRowColors(True)
        self.table_ved.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_ved.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table_ved.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table_ved.horizontalHeader().setStretchLastSection(True)
        self.table_ved.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table_ved.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table_ved.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table_ved.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table_ved.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.table_ved.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        main_layout.addWidget(self.table_ved)

        # 4. Нижняя панель действий документа
        layout_bottom = QHBoxLayout()
        layout_bottom.setContentsMargins(4, 4, 4, 4)

        self.lbl_calc_status = QLabel("Задайте параметры распоряжения и нажмите «Рассчитать» для формирования ведомости выплат.")
        self.lbl_calc_status.setStyleSheet("color: #888; font-size: 12px;")
        layout_bottom.addWidget(self.lbl_calc_status)

        layout_bottom.addStretch()

        self.btn_save_doc = QPushButton("Сохранить документ...")
        self.btn_save_doc.setEnabled(False)
        self.btn_save_doc.setToolTip("Экспортировать проект распоряжения / ведомость выплат (Excel, HTML, CSV, TXT)")
        self.btn_save_doc.clicked.connect(self._on_save_document)
        layout_bottom.addWidget(self.btn_save_doc)

        self.btn_approve = QPushButton("Утвердить")
        self.btn_approve.setEnabled(False)
        self.btn_approve.setToolTip("Утвердить распоряжение и внести выплаты в базу данных")
        self.btn_approve.setStyleSheet("font-weight: 600; padding: 4px 16px;")
        self.btn_approve.clicked.connect(self._on_approve)
        layout_bottom.addWidget(self.btn_approve)

        main_layout.addLayout(layout_bottom)

        # Первичная синхронизация поля суммы по 25%
        self._sync_sum_from_percent(self.spin_pct.value())

    def refresh_summary(self):
        """Обновление информационного блока исходного состояния."""
        summary = get_finance_summary(DB_PATH)
        self.current_summary = summary

        self.lbl_val_vuz.setText(str(summary["total_vuz"]))
        self.lbl_val_proj.setText(str(summary["total_proj"]))
        self.lbl_val_plan.setText(f"{summary['total_plan']:,} руб.".replace(",", " "))
        self.lbl_val_fact.setText(
            f"{summary['total_fact']:,} руб. ({summary['fact_pct']:.2f}%)".replace(",", " ")
        )
        self.lbl_val_quarters.setText(
            f"1 кв: {summary['q1']:,} руб. | 2 кв: {summary['q2']:,} руб. | 3 кв: {summary['q3']:,} руб. | 4 кв: {summary['q4']:,} руб.".replace(",", " ")
        )

    def _sync_sum_from_percent(self, pct: float):
        """Расчет суммы по проценту."""
        total_plan = getattr(self, "current_summary", {}).get("total_plan", 201270000)
        target_sum = int(round(total_plan * (pct / 100.0)))
        self.edit_sum.blockSignals(True)
        self.edit_sum.setText(str(target_sum))
        self.edit_sum.blockSignals(False)

    def _on_percent_changed(self, val: float):
        """Пользователь изменил процент."""
        self._sync_sum_from_percent(val)

    def _on_sum_edited(self, text: str):
        """Пользователь ввел сумму вручную."""
        clean_text = "".join(ch for ch in text if ch.isdigit())
        if not clean_text:
            return
        total_plan = getattr(self, "current_summary", {}).get("total_plan", 201270000)
        if total_plan <= 0:
            return

        val = int(clean_text)
        pct = (val / total_plan) * 100.0
        pct = max(0.01, min(100.0, pct))

        self.spin_pct.blockSignals(True)
        self.spin_pct.setValue(pct)
        self.spin_pct.blockSignals(False)

    def _on_calculate(self):
        """Выполнение расчета распределения средств."""
        pct = self.spin_pct.value()
        quarter = self.combo_quarter.currentIndex() + 1

        calc = calculate_tranche_distribution(pct, DB_PATH)
        calc["quarter"] = quarter
        self.calculated_data = calc

        self._render_vedomost(calc)

        self.lbl_calc_status.setText(
            f"Проект распоряжения на {quarter}-й квартал: выделено {calc['total_distributed']:,} руб. ({pct:.2f}% от плана) по {calc['total_proj_count']} НИР.".replace(",", " ")
        )
        self.btn_save_doc.setEnabled(True)
        self.btn_approve.setEnabled(True)

    def _render_vedomost(self, calc: dict):
        """Отрисовка ведомости выплат по вузам в таблице."""
        vuz_rows = calc["vuz_rows"]
        total_rows = len(vuz_rows) + 1  # + строка ИТОГО

        self.table_ved.setRowCount(total_rows)

        total_projs = 0
        total_payments = 0

        for idx, row in enumerate(vuz_rows, start=1):
            total_projs += row["proj_count"]
            total_payments += row["tranche_sum"]

            item_num = QTableWidgetItem(str(idx))
            item_num.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            item_code = QTableWidgetItem(str(row["codvuz"]))
            item_code.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            item_name = QTableWidgetItem(row["vuz_short_name"])
            item_city = QTableWidgetItem(row["city"])

            item_cnt = QTableWidgetItem(str(row["proj_count"]))
            item_cnt.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            item_pay = QTableWidgetItem(f"{row['tranche_sum']:,}".replace(",", " "))
            item_pay.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            row_idx = idx - 1
            self.table_ved.setItem(row_idx, 0, item_num)
            self.table_ved.setItem(row_idx, 1, item_code)
            self.table_ved.setItem(row_idx, 2, item_name)
            self.table_ved.setItem(row_idx, 3, item_city)
            self.table_ved.setItem(row_idx, 4, item_cnt)
            self.table_ved.setItem(row_idx, 5, item_pay)

        # Строка «ИТОГО»
        bold_font = QFont()
        bold_font.setBold(True)

        tot_row = len(vuz_rows)
        item_tot_lbl = QTableWidgetItem("ИТОГО")
        item_tot_lbl.setFont(bold_font)
        item_tot_lbl.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

        item_tot_cnt = QTableWidgetItem(str(total_projs))
        item_tot_cnt.setFont(bold_font)
        item_tot_cnt.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        item_tot_pay = QTableWidgetItem(f"{total_payments:,}".replace(",", " "))
        item_tot_pay.setFont(bold_font)
        item_tot_pay.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self.table_ved.setItem(tot_row, 0, item_tot_lbl)
        self.table_ved.setItem(tot_row, 1, QTableWidgetItem(""))
        self.table_ved.setItem(tot_row, 2, QTableWidgetItem(""))
        self.table_ved.setItem(tot_row, 3, QTableWidgetItem(""))
        self.table_ved.setItem(tot_row, 4, item_tot_cnt)
        self.table_ved.setItem(tot_row, 5, item_tot_pay)

        for col in range(6):
            it = self.table_ved.item(tot_row, col)
            if it:
                it.setBackground(QColor(128, 128, 128, 40))

    def _on_cancel(self):
        """Сброс параметров и очистка ведомости."""
        self.calculated_data = None
        self.table_ved.setRowCount(0)
        self.spin_pct.setValue(25.0)
        self._sync_sum_from_percent(25.0)
        self.combo_quarter.setCurrentIndex(0)
        self.lbl_calc_status.setText("Расчет отменен. Задайте параметры и нажмите «Рассчитать».")
        self.btn_save_doc.setEnabled(False)
        self.btn_approve.setEnabled(False)

    def _build_document_report_data(self) -> dict:
        """Подготовка структуры данных отчета для экспорта."""
        if not self.calculated_data:
            return None

        calc = self.calculated_data
        quarter = calc["quarter"]
        pct = calc["percent"]

        headers = [
            "№ п/п",
            "Код вуза",
            "Вуз-исполнитель",
            "Город",
            "Количество НИР",
            "Сумма выплат (руб.)",
        ]

        rows = []
        for idx, row in enumerate(calc["vuz_rows"], start=1):
            rows.append([
                idx,
                row["codvuz"],
                row["vuz_short_name"],
                row["city"],
                row["proj_count"],
                row["tranche_sum"],
            ])

        totals = [
            "ИТОГО",
            "",
            "",
            "",
            calc["total_proj_count"],
            calc["total_distributed"],
        ]

        return {
            "title": f"Распоряжение о финансировании проектов НИР по грантам ({quarter}-й квартал, {pct:.2f}% от плана)",
            "headers": headers,
            "rows": rows,
            "totals": totals,
            "money_cols": [5],
            "numeric_cols": [0, 1, 4],
        }

    def _on_save_document(self):
        """Экспорт сформированной ведомости выплат в файл."""
        rep_data = self._build_document_report_data()
        if not rep_data:
            return

        filters = "Файлы Excel (*.xlsx);;HTML Документ (*.html);;Текстовый CSV (*.csv);;Текстовый документ (*.txt)"
        now = datetime.now()
        q = self.calculated_data["quarter"]
        default_name = f"Распоряжение_финансирование_Квартал_{q}_{now.strftime('%Y%m%d_%H%M')}.xlsx"

        file_path, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Сохранить документ распоряжения о финансировании",
            default_name,
            filters
        )

        if not file_path:
            return

        try:
            filter_desc = f"Параметры: Квартал {q}, выделенный объем {self.calculated_data['percent']:.2f}% ({self.calculated_data['total_distributed']:,} руб.)"
            export_report_to_file(file_path, rep_data, filter_desc)
            QMessageBox.information(
                self,
                "Экспорт завершен",
                f"Документ распоряжения о финансировании успешно сохранен:\n{file_path}"
            )
        except Exception as e:
            QMessageBox.critical(self, "Ошибка сохранения", f"Не удалось сохранить документ:\n{e}")

    def _on_approve(self):
        """Утверждение распоряжения и проведение выплат в базе данных."""
        if not self.calculated_data:
            return

        calc = self.calculated_data
        q = calc["quarter"]
        total_dist = calc["total_distributed"]
        pct = calc["percent"]

        # Запрос подтверждения у оператора
        reply = QMessageBox.question(
            self,
            "Подтверждение утверждения финансирования",
            f"Вы действительно хотите утвердить распоряжение о финансировании проектов НИР?\n\n"
            f"• Квартал: {q}-й квартал\n"
            f"• Процент от плана: {pct:.2f}%\n"
            f"• Сумма транша: {total_dist:,} руб.\n"
            f"• Число проектов: {calc['total_proj_count']}\n\n"
            f"Данные будут зафиксированы в базе данных SQLite.".replace(",", " "),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            execute_tranche_in_db(q, calc["project_tranches"], DB_PATH)
            self.refresh_summary()
            self.data_updated.emit()

            self.btn_approve.setEnabled(False)
            self.lbl_calc_status.setText(
                f"Распоряжение на {q}-й квартал ({total_dist:,} руб.) успешно УТВЕРЖДЕНО и проведено в БД!".replace(",", " ")
            )

            # Предложение сохранить официальный утвержденный документ
            exp_reply = QMessageBox.question(
                self,
                "Сохранение документа",
                "Финансирование успешно проведено в базу данных!\n\n"
                "Желаете сохранить утвержденную ведомость выплат в файл документа?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes
            )
            if exp_reply == QMessageBox.StandardButton.Yes:
                self._on_save_document()

        except Exception as e:
            QMessageBox.critical(self, "Ошибка проведения", f"Сбой при проведении транша в базе данных:\n{e}")

    def _on_reset_quarter(self):
        """Сброс и обнуление выплат по выбранному кварталу в базе данных."""
        q = self.combo_quarter.currentIndex() + 1
        summary = get_finance_summary(DB_PATH)
        current_q_val = summary.get(f"q{q}", 0)

        if current_q_val == 0:
            QMessageBox.information(
                self,
                "Очистка квартала",
                f"В {q}-м квартале пока нет проведённых выплат (сумма равна 0 руб.)."
            )
            return

        reply = QMessageBox.question(
            self,
            "Подтверждение очистки квартала",
            f"Вы действительно хотите обнулить выплаты за {q}-й квартал?\n\n"
            f"• Текущая сумма выплат: {current_q_val:,} руб.\n\n"
            f"Данные по {q}-му кварталу будут сброшены в 0, а общий факт финансирования уменьшен.".replace(",", " "),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            reset_quarter_funding(q, DB_PATH)
            self.refresh_summary()
            self._on_cancel()
            self.data_updated.emit()
            QMessageBox.information(
                self,
                "Квартал очищен",
                f"Финансирование за {q}-й квартал ({current_q_val:,} руб.) успешно сброшено в 0.".replace(",", " ")
            )
        except Exception as e:
            QMessageBox.critical(self, "Ошибка очистки", f"Не удалось обнулить квартал:\n{e}")


