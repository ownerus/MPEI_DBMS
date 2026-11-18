use eframe::egui::{self, Color32, FontData, FontDefinitions, FontFamily, RichText};
use rusqlite::Connection;
use std::path::PathBuf;

use crate::filter::{self, FilterCriteria};
use crate::finance::{self, FinanceSummary, TrancheDistribution};
use crate::models::{self, Contest, Project, University};
use crate::reports::{self, ReportData};

#[derive(PartialEq, Clone, Copy)]
pub enum ActiveTab {
    Projects,
    Contests,
    Universities,
    Reports,
    Finance,
    Help,
}

pub struct AppState {
    pub db_path: PathBuf,
    pub active_tab: ActiveTab,
    pub status_message: String,

    // Data cache
    pub projects: Vec<Project>,
    pub contests: Vec<Contest>,
    pub universities: Vec<University>,
    pub selected_project_idx: Option<usize>,
    pub sort_by_key: bool,

    // Filter
    pub current_filter: FilterCriteria,
    pub filter_dialog_open: bool,
    pub filter_draft: FilterCriteria,

    // Project Dialog
    pub project_dialog_open: bool,
    pub project_dialog_is_edit: bool,
    pub project_draft: Project,
    pub project_dialog_error: String,

    // Delete confirmation
    pub delete_confirm_open: bool,
    pub delete_target_id: Option<i64>,

    // Reports
    pub selected_report_form: usize,
    pub current_report: Option<ReportData>,
    pub export_dialog_open: bool,
    pub export_path: String,

    // Finance
    pub finance_summary: Option<FinanceSummary>,
    pub finance_quarter: u8,
    pub finance_percent: f64,
    pub finance_sum: i64,
    pub calculated_tranche: Option<TrancheDistribution>,
    pub approve_confirm_open: bool,
    pub reset_confirm_open: bool,
}

impl AppState {
    pub fn new(db_path: PathBuf) -> Self {
        let mut state = Self {
            db_path,
            active_tab: ActiveTab::Projects,
            status_message: "Готово к работе".to_string(),

            projects: Vec::new(),
            contests: Vec::new(),
            universities: Vec::new(),
            selected_project_idx: None,
            sort_by_key: false,

            current_filter: FilterCriteria::default(),
            filter_dialog_open: false,
            filter_draft: FilterCriteria::default(),

            project_dialog_open: false,
            project_dialog_is_edit: false,
            project_draft: Project {
                id: 0,
                codkon: 1,
                codproj: 1,
                codvuz: 1,
                vuz_short_name: String::new(),
                grnti_code: "55.03.35".to_string(),
                plan_fin: 1000000,
                fact_fin: 0,
                fin_q1: 0,
                fin_q2: 0,
                fin_q3: 0,
                fin_q4: 0,
                leader_fio: String::new(),
                leader_post: "Доцент".to_string(),
                leader_rank: "Доцент".to_string(),
                leader_degree: "к.т.н.".to_string(),
                proj_name: String::new(),
            },
            project_dialog_error: String::new(),

            delete_confirm_open: false,
            delete_target_id: None,

            selected_report_form: 0,
            current_report: None,
            export_dialog_open: false,
            export_path: "otchet.xlsx".to_string(),

            finance_summary: None,
            finance_quarter: 1,
            finance_percent: 25.0,
            finance_sum: 50317500,
            calculated_tranche: None,
            approve_confirm_open: false,
            reset_confirm_open: false,
        };
        state.reload_all();
        state
    }

    pub fn open_conn(&self) -> rusqlite::Result<Connection> {
        crate::database::connect_db(&self.db_path)
    }

    pub fn reload_all(&mut self) {
        if let Ok(conn) = self.open_conn() {
            let _ = crate::database::sync_contest_aggregates(&conn, None);
            self.reload_projects(&conn);
            self.contests = models::get_contests(&conn).unwrap_or_default();
            self.universities = models::get_universities(&conn).unwrap_or_default();
            self.finance_summary = finance::get_finance_summary(&conn).ok();
            self.refresh_report_data(&conn);
        }
    }

    pub fn reload_projects(&mut self, conn: &Connection) {
        let fw = self.current_filter.build_where_clause();
        self.projects = models::get_projects(
            conn,
            if fw.is_empty() { None } else { Some(&fw) },
            self.sort_by_key,
        )
        .unwrap_or_default();
        let summary = self.current_filter.build_summary(conn);
        if summary.is_empty() {
            self.status_message = format!("Всего проектов: {}", self.projects.len());
        } else {
            self.status_message = format!("Проектов: {} (фильтр: {})", self.projects.len(), summary);
        }
    }

    pub fn refresh_report_data(&mut self, conn: &Connection) {
        let fw = self.current_filter.build_where_clause();
        let rep = match self.selected_report_form {
            0 => reports::build_contest_report(conn, &fw),
            1 => reports::build_vuz_report(conn, &fw),
            2 => reports::build_region_report(conn, &fw),
            _ => reports::build_contest_report(conn, &fw),
        };
        self.current_report = rep.ok();
    }
}

pub fn setup_custom_fonts(ctx: &egui::Context) {
    let mut fonts = FontDefinitions::default();

    // Загрузка Segoe UI или Arial из Windows Fonts для идеальной кириллицы
    let font_candidates = [
        "C:\\Windows\\Fonts\\segoeui.ttf",
        "C:\\Windows\\Fonts\\arial.ttf",
        "C:\\Windows\\Fonts\\tahoma.ttf",
    ];

    for path in font_candidates {
        if let Ok(bytes) = std::fs::read(path) {
            fonts
                .font_data
                .insert("windows_font".to_owned(), FontData::from_owned(bytes).into());
            fonts
                .families
                .get_mut(&FontFamily::Proportional)
                .unwrap()
                .insert(0, "windows_font".to_owned());
            fonts
                .families
                .get_mut(&FontFamily::Monospace)
                .unwrap()
                .insert(0, "windows_font".to_owned());
            break;
        }
    }

    ctx.set_fonts(fonts);
}

pub struct MainWindow {
    pub state: AppState,
}

impl eframe::App for MainWindow {
    fn ui(&mut self, ui: &mut egui::Ui, _frame: &mut eframe::Frame) {
        let ctx = ui.ctx().clone();

        // Верхняя панель навигации
        ui.horizontal(|ui| {
            ui.heading("АРМ «Гранты» (Вариант № 7)");
            ui.separator();

            if ui
                .selectable_label(self.state.active_tab == ActiveTab::Projects, "Проекты НИР (Ctrl+1)")
                .clicked()
            {
                self.state.active_tab = ActiveTab::Projects;
            }
            if ui
                .selectable_label(self.state.active_tab == ActiveTab::Contests, "Конкурсы грантов (Ctrl+2)")
                .clicked()
            {
                self.state.active_tab = ActiveTab::Contests;
            }
            if ui
                .selectable_label(self.state.active_tab == ActiveTab::Universities, "Справочник вузов (Ctrl+3)")
                .clicked()
            {
                self.state.active_tab = ActiveTab::Universities;
            }
            if ui
                .selectable_label(self.state.active_tab == ActiveTab::Reports, "Аналитические отчеты (Ctrl+4)")
                .clicked()
            {
                self.state.active_tab = ActiveTab::Reports;
                if let Ok(conn) = self.state.open_conn() {
                    self.state.refresh_report_data(&conn);
                }
            }
            if ui
                .selectable_label(self.state.active_tab == ActiveTab::Finance, "Финансирование (Ctrl+5)")
                .clicked()
            {
                self.state.active_tab = ActiveTab::Finance;
                if let Ok(conn) = self.state.open_conn() {
                    self.state.finance_summary = finance::get_finance_summary(&conn).ok();
                }
            }
            if ui
                .selectable_label(self.state.active_tab == ActiveTab::Help, "Справка (F1)")
                .clicked()
            {
                self.state.active_tab = ActiveTab::Help;
            }
        });
        ui.separator();

        // Центральная часть вкладки
        match self.state.active_tab {
            ActiveTab::Projects => self.render_projects_tab(ui),
            ActiveTab::Contests => self.render_contests_tab(ui),
            ActiveTab::Universities => self.render_universities_tab(ui),
            ActiveTab::Reports => self.render_reports_tab(ui),
            ActiveTab::Finance => self.render_finance_tab(ui),
            ActiveTab::Help => self.render_help_tab(ui),
        }

        ui.separator();
        ui.horizontal(|ui| {
            ui.label(RichText::new(&self.state.status_message).size(12.0).color(Color32::DARK_GRAY));
            ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                ui.label(RichText::new(format!("БД: {}", self.state.db_path.display())).size(11.0));
            });
        });

        // Модальные окна
        self.render_filter_dialog(&ctx);
        self.render_project_dialog(&ctx);
        self.render_delete_dialog(&ctx);
        self.render_export_dialog(&ctx);
        self.render_approve_dialog(&ctx);
        self.render_reset_dialog(&ctx);
    }
}

impl MainWindow {
    fn render_projects_tab(&mut self, ui: &mut egui::Ui) {
        ui.horizontal(|ui| {
            if ui.button("Добавить (Insert)").clicked() {
                self.open_add_project_dialog();
            }

            let has_selection = self.state.selected_project_idx.is_some();
            if ui.add_enabled(has_selection, egui::Button::new("Изменить (F4)")).clicked() {
                self.open_edit_project_dialog();
            }
            if ui.add_enabled(has_selection, egui::Button::new("Удалить (Delete)")).clicked() {
                if let Some(idx) = self.state.selected_project_idx {
                    if let Some(p) = self.state.projects.get(idx) {
                        self.state.delete_target_id = Some(p.id);
                        self.state.delete_confirm_open = true;
                    }
                }
            }

            ui.separator();
            if ui.button("Фильтр (Ctrl+F)").clicked() {
                self.state.filter_draft = self.state.current_filter.clone();
                self.state.filter_dialog_open = true;
            }

            if !self.state.current_filter.is_empty() {
                if ui.button("Снять фильтр").clicked() {
                    self.state.current_filter.clear();
                    if let Ok(conn) = self.state.open_conn() {
                        self.state.reload_projects(&conn);
                    }
                }
            }

            ui.separator();
            if ui
                .checkbox(&mut self.state.sort_by_key, "Сортировка по ключу (Ctrl+K)")
                .changed()
            {
                if let Ok(conn) = self.state.open_conn() {
                    self.state.reload_projects(&conn);
                }
            }
        });

        ui.separator();

        // Таблица проектов
        egui::ScrollArea::both().show(ui, |ui| {
            egui::Grid::new("projects_grid")
                .striped(true)
                .min_col_width(50.0)
                .show(ui, |ui| {
                    ui.label(RichText::new("№").strong());
                    ui.label(RichText::new("Конкурс").strong());
                    ui.label(RichText::new("Код НИР").strong());
                    ui.label(RichText::new("Код вуза").strong());
                    ui.label(RichText::new("Вуз").strong());
                    ui.label(RichText::new("ГРНТИ").strong());
                    ui.label(RichText::new("План (руб.)").strong());
                    ui.label(RichText::new("Факт (руб.)").strong());
                    ui.label(RichText::new("Руководитель").strong());
                    ui.label(RichText::new("Тема НИР").strong());
                    ui.end_row();

                    for (idx, p) in self.state.projects.iter().enumerate() {
                        let is_selected = self.state.selected_project_idx == Some(idx);
                        let num_label = ui.selectable_label(is_selected, (idx + 1).to_string());
                        if num_label.clicked() {
                            self.state.selected_project_idx = Some(idx);
                        }
                        ui.label(p.codkon.to_string());
                        ui.label(p.codproj.to_string());
                        ui.label(p.codvuz.to_string());
                        ui.label(&p.vuz_short_name);
                        ui.label(&p.grnti_code);
                        ui.label(crate::database::format_money(p.plan_fin));
                        ui.label(crate::database::format_money(p.fact_fin));
                        ui.label(&p.leader_fio);
                        ui.label(&p.proj_name);
                        ui.end_row();
                    }
                });
        });
    }

    fn render_contests_tab(&mut self, ui: &mut egui::Ui) {
        ui.heading("Справочник конкурсов грантов");
        ui.separator();
        egui::ScrollArea::both().show(ui, |ui| {
            egui::Grid::new("contests_grid")
                .striped(true)
                .show(ui, |ui| {
                    ui.label(RichText::new("Код").strong());
                    ui.label(RichText::new("Наименование конкурса").strong());
                    ui.label(RichText::new("Проектов").strong());
                    ui.label(RichText::new("План (руб.)").strong());
                    ui.label(RichText::new("Факт (руб.)").strong());
                    ui.label(RichText::new("1 кв (руб.)").strong());
                    ui.label(RichText::new("2 кв (руб.)").strong());
                    ui.label(RichText::new("3 кв (руб.)").strong());
                    ui.label(RichText::new("4 кв (руб.)").strong());
                    ui.end_row();

                    for c in &self.state.contests {
                        ui.label(c.codkon.to_string());
                        ui.label(&c.konk_name);
                        ui.label(c.projects_count.to_string());
                        ui.label(crate::database::format_money(c.plan_fin));
                        ui.label(crate::database::format_money(c.fact_fin));
                        ui.label(crate::database::format_money(c.fin_q1));
                        ui.label(crate::database::format_money(c.fin_q2));
                        ui.label(crate::database::format_money(c.fin_q3));
                        ui.label(crate::database::format_money(c.fin_q4));
                        ui.end_row();
                    }
                });
        });
    }

    fn render_universities_tab(&mut self, ui: &mut egui::Ui) {
        ui.heading("Справочник вузов-исполнителей");
        ui.separator();
        egui::ScrollArea::both().show(ui, |ui| {
            egui::Grid::new("vuz_grid")
                .striped(true)
                .show(ui, |ui| {
                    ui.label(RichText::new("Код").strong());
                    ui.label(RichText::new("Краткое название").strong());
                    ui.label(RichText::new("Город").strong());
                    ui.label(RichText::new("Субъект РФ").strong());
                    ui.label(RichText::new("Фед. округ").strong());
                    ui.label(RichText::new("Ведомство").strong());
                    ui.end_row();

                    for v in &self.state.universities {
                        ui.label(v.codvuz.to_string());
                        ui.label(&v.vuz_short_name);
                        ui.label(&v.city);
                        ui.label(&v.obl_name);
                        ui.label(&v.region);
                        ui.label(&v.department);
                        ui.end_row();
                    }
                });
        });
    }

    fn render_reports_tab(&mut self, ui: &mut egui::Ui) {
        ui.horizontal(|ui| {
            ui.label("Аналитическая форма:");
            let prev = self.state.selected_report_form;
            egui::ComboBox::from_id_salt("combo_rep")
                .selected_text(match self.state.selected_report_form {
                    0 => "Форма 1: по конкурсам грантов",
                    1 => "Форма 2: по вузам-исполнителям",
                    2 => "Форма 3: по субъектам РФ",
                    _ => "",
                })
                .show_ui(ui, |ui| {
                    ui.selectable_value(&mut self.state.selected_report_form, 0, "Форма 1: по конкурсам");
                    ui.selectable_value(&mut self.state.selected_report_form, 1, "Форма 2: по вузам");
                    ui.selectable_value(&mut self.state.selected_report_form, 2, "Форма 3: по субъектам РФ");
                });

            if prev != self.state.selected_report_form {
                if let Ok(conn) = self.state.open_conn() {
                    self.state.refresh_report_data(&conn);
                }
            }

            if ui.button("Обновить").clicked() {
                if let Ok(conn) = self.state.open_conn() {
                    self.state.refresh_report_data(&conn);
                }
            }

            if ui.button("Экспорт... (Ctrl+S)").clicked() {
                self.state.export_path = match self.state.selected_report_form {
                    0 => "otchet_forma_1.xlsx".to_string(),
                    1 => "otchet_forma_2.xlsx".to_string(),
                    _ => "otchet_forma_3.xlsx".to_string(),
                };
                self.state.export_dialog_open = true;
            }
        });

        ui.separator();

        if let Some(ref report) = self.state.current_report {
            ui.heading(&report.title);
            let summary = self
                .state
                .open_conn()
                .map(|c| self.state.current_filter.build_summary(&c))
                .unwrap_or_default();
            if !summary.is_empty() {
                ui.label(format!("Условия отбора: {}", summary));
            }

            egui::ScrollArea::both().show(ui, |ui| {
                egui::Grid::new("rep_grid")
                    .striped(true)
                    .show(ui, |ui| {
                        for h in &report.headers {
                            ui.label(RichText::new(h).strong());
                        }
                        ui.end_row();

                        for row in &report.rows {
                            for cell in row {
                                ui.label(cell);
                            }
                            ui.end_row();
                        }

                        if !report.totals.is_empty() {
                            for cell in &report.totals {
                                ui.label(RichText::new(cell).strong().color(Color32::from_rgb(20, 60, 120)));
                            }
                            ui.end_row();
                        }
                    });
            });
        }
    }

    fn render_finance_tab(&mut self, ui: &mut egui::Ui) {
        ui.heading("Раздел «Финансирование проектов НИР»");
        ui.separator();

        if let Some(ref sum) = self.state.finance_summary {
            ui.group(|ui| {
                ui.horizontal(|ui| {
                    ui.vertical(|ui| {
                        ui.label(format!("Вузов-исполнителей: {}", sum.vuz_count));
                        ui.label(format!("Проектов НИР: {}", sum.proj_count));
                    });
                    ui.separator();
                    ui.vertical(|ui| {
                        ui.label(format!("Суммарный план: {} руб.", crate::database::format_money(sum.total_plan)));
                        ui.label(format!(
                            "Фактически профинансировано: {} руб. ({:.2}%)",
                            crate::database::format_money(sum.total_fact),
                            sum.fact_pct
                        ));
                    });
                    ui.separator();
                    ui.vertical(|ui| {
                        ui.label(format!(
                            "Поквартально: Q1: {} | Q2: {} | Q3: {} | Q4: {}",
                            crate::database::format_money(sum.q1),
                            crate::database::format_money(sum.q2),
                            crate::database::format_money(sum.q3),
                            crate::database::format_money(sum.q4)
                        ));
                    });
                });
            });
        }

        ui.add_space(8.0);
        ui.group(|ui| {
            ui.horizontal(|ui| {
                ui.label("Квартал:");
                egui::ComboBox::from_id_salt("fin_q_combo")
                    .selected_text(format!("{}-й квартал", self.state.finance_quarter))
                    .show_ui(ui, |ui| {
                        for q in 1..=4 {
                            ui.selectable_value(&mut self.state.finance_quarter, q, format!("{}-й квартал", q));
                        }
                    });

                ui.separator();
                ui.label("Процент от плана (%):");
                let p_changed = ui
                    .add(egui::DragValue::new(&mut self.state.finance_percent).speed(0.1).range(0.01..=100.0))
                    .changed();
                if p_changed {
                    if let Some(ref s) = self.state.finance_summary {
                        self.state.finance_sum = ((s.total_plan as f64) * (self.state.finance_percent / 100.0)).round() as i64;
                    }
                }

                ui.label("Сумма (руб.):");
                let s_changed = ui.add(egui::DragValue::new(&mut self.state.finance_sum).speed(1000.0)).changed();
                if s_changed {
                    if let Some(ref s) = self.state.finance_summary {
                        if s.total_plan > 0 {
                            self.state.finance_percent = (self.state.finance_sum as f64 / s.total_plan as f64) * 100.0;
                        }
                    }
                }

                if ui.button("Рассчитать").clicked() {
                    if let Ok(conn) = self.state.open_conn() {
                        self.state.calculated_tranche = finance::calculate_tranche_distribution(
                            self.state.finance_percent,
                            &conn,
                        )
                        .ok();
                    }
                }

                if self.state.calculated_tranche.is_some() {
                    if ui.button("Отмена").clicked() {
                        self.state.calculated_tranche = None;
                    }
                    if ui.button("Сохранить документ...").clicked() {
                        self.state.export_path = format!("rasporyazhenie_q{}.xlsx", self.state.finance_quarter);
                        self.state.export_dialog_open = true;
                    }
                    if ui.button(RichText::new("Утвердить").strong().color(Color32::from_rgb(0, 120, 0))).clicked() {
                        self.state.approve_confirm_open = true;
                    }
                }

                ui.separator();
                if ui.button("Сброс квартала...").clicked() {
                    self.state.reset_confirm_open = true;
                }
            });
        });

        ui.add_space(8.0);
        if let Some(ref calc) = self.state.calculated_tranche {
            ui.heading(format!(
                "Сводная ведомость выплат по вузам ({}-й квартал, {:.2}%, транш: {} руб.)",
                self.state.finance_quarter,
                calc.percent,
                crate::database::format_money(calc.total_distributed)
            ));

            egui::ScrollArea::both().show(ui, |ui| {
                egui::Grid::new("fin_grid")
                    .striped(true)
                    .show(ui, |ui| {
                        ui.label(RichText::new("№").strong());
                        ui.label(RichText::new("Код").strong());
                        ui.label(RichText::new("Вуз-исполнитель").strong());
                        ui.label(RichText::new("Город").strong());
                        ui.label(RichText::new("Проектов").strong());
                        ui.label(RichText::new("Сумма выплат (руб.)").strong());
                        ui.end_row();

                        for (i, v) in calc.vuz_rows.iter().enumerate() {
                            ui.label((i + 1).to_string());
                            ui.label(v.codvuz.to_string());
                            ui.label(&v.vuz_short_name);
                            ui.label(&v.city);
                            ui.label(v.proj_count.to_string());
                            ui.label(crate::database::format_money(v.tranche_sum));
                            ui.end_row();
                        }

                        ui.label(RichText::new("ИТОГО").strong());
                        ui.label("");
                        ui.label("");
                        ui.label("");
                        ui.label(RichText::new(calc.total_proj_count.to_string()).strong());
                        ui.label(RichText::new(crate::database::format_money(calc.total_distributed)).strong());
                        ui.end_row();
                    });
            });
        }
    }

    fn render_help_tab(&mut self, ui: &mut egui::Ui) {
        ui.heading("Руководство пользователя — АРМ сопровождения конкурсов грантов");
        ui.separator();
        egui::ScrollArea::vertical().show(ui, |ui| {
            ui.label(RichText::new("1. Навигация по разделам").strong());
            ui.label("Переключение между разделами выполняется кнопками на верхней панели или сочетаниями клавиш Ctrl+1 .. Ctrl+5.");
            ui.add_space(6.0);
            ui.label(RichText::new("2. Реестр проектов НИР").strong());
            ui.label("• Добавить (Insert): открытие диалога создания проекта. Номер внутри конкурса предлагается автоматически (MAX + 1).");
            ui.label("• Изменить (F4): редактирование темы, ГРНТИ, руководителя или плановой суммы выбранного проекта.");
            ui.label("• Удалить (Delete): удаление проекта с обязательным подтверждением.");
            ui.label("• Сортировка по ключу (Ctrl+K): переключение сортировки по первичному составному ключу (codkon, codproj).");
            ui.add_space(6.0);
            ui.label(RichText::new("3. Фильтрация данных").strong());
            ui.label("Диалог фильтра (Ctrl+F) поддерживает отбор по конкурсу и каскадную географию вуза (округ → субъект → город → вуз).");
            ui.add_space(6.0);
            ui.label(RichText::new("4. Аналитические отчеты").strong());
            ui.label("Формируются три аналитических отчета (по конкурсам, вузам и регионам). Экспорт отчета в форматы XLSX, HTML, CSV, TXT выполняется по кнопке «Экспорт...» или Ctrl+S.");
            ui.add_space(6.0);
            ui.label(RichText::new("5. Финансирование проектов").strong());
            ui.label("Задайте квартал и сумму или процент от плана, затем нажмите «Рассчитать». Средства распределяются по всем проектам пропорционально с округлением до целых рублей. Кнопка «Утвердить» фиксирует транш в БД, «Сброс квартала» обнуляет выплаты выбранного периода.");
        });
    }

    // Вспомогательные модальные диалоги
    fn open_add_project_dialog(&mut self) {
        let codkon = 1;
        let next_code = if let Ok(conn) = self.state.open_conn() {
            models::suggest_next_codproj(&conn, codkon).unwrap_or(1)
        } else {
            1
        };
        self.state.project_draft = Project {
            id: 0,
            codkon,
            codproj: next_code,
            codvuz: 1,
            vuz_short_name: String::new(),
            grnti_code: "55.03.35".to_string(),
            plan_fin: 1000000,
            fact_fin: 0,
            fin_q1: 0,
            fin_q2: 0,
            fin_q3: 0,
            fin_q4: 0,
            leader_fio: "Иванов И.И.".to_string(),
            leader_post: "Доцент".to_string(),
            leader_rank: "Доцент".to_string(),
            leader_degree: "к.т.н.".to_string(),
            proj_name: "Новая НИР".to_string(),
        };
        self.state.project_dialog_is_edit = false;
        self.state.project_dialog_error.clear();
        self.state.project_dialog_open = true;
    }

    fn open_edit_project_dialog(&mut self) {
        if let Some(idx) = self.state.selected_project_idx {
            if let Some(p) = self.state.projects.get(idx) {
                self.state.project_draft = p.clone();
                self.state.project_dialog_is_edit = true;
                self.state.project_dialog_error.clear();
                self.state.project_dialog_open = true;
            }
        }
    }

    fn render_project_dialog(&mut self, ctx: &egui::Context) {
        if !self.state.project_dialog_open {
            return;
        }

        let title = if self.state.project_dialog_is_edit {
            "Редактирование проекта НИР"
        } else {
            "Добавление проекта НИР"
        };

        egui::Window::new(title)
            .collapsible(false)
            .resizable(false)
            .anchor(egui::Align2::CENTER_CENTER, [0.0, 0.0])
            .show(ctx, |ui| {
                ui.set_min_width(450.0);
                egui::Grid::new("proj_dlg_grid").show(ui, |ui| {
                    ui.label("Код конкурса:");
                    let prev_konk = self.state.project_draft.codkon;
                    egui::ComboBox::from_id_salt("dlg_konk")
                        .selected_text(format!("Конкурс {}", self.state.project_draft.codkon))
                        .show_ui(ui, |ui| {
                            for c in &self.state.contests {
                                ui.selectable_value(
                                    &mut self.state.project_draft.codkon,
                                    c.codkon,
                                    format!("{}: {}", c.codkon, c.konk_name),
                                );
                            }
                        });
                    ui.end_row();

                    if prev_konk != self.state.project_draft.codkon && !self.state.project_dialog_is_edit {
                        if let Ok(conn) = self.state.open_conn() {
                            self.state.project_draft.codproj =
                                models::suggest_next_codproj(&conn, self.state.project_draft.codkon).unwrap_or(1);
                        }
                    }

                    ui.label("Номер проекта (codproj):");
                    ui.add(egui::DragValue::new(&mut self.state.project_draft.codproj).range(1..=999999));
                    ui.end_row();

                    ui.label("Код вуза:");
                    egui::ComboBox::from_id_salt("dlg_vuz")
                        .selected_text(format!("{}: {}", self.state.project_draft.codvuz, self.state.project_draft.vuz_short_name))
                        .show_ui(ui, |ui| {
                            for v in &self.state.universities {
                                if ui
                                    .selectable_label(
                                        self.state.project_draft.codvuz == v.codvuz,
                                        format!("{}: {}", v.codvuz, v.vuz_short_name),
                                    )
                                    .clicked()
                                {
                                    self.state.project_draft.codvuz = v.codvuz;
                                    self.state.project_draft.vuz_short_name = v.vuz_short_name.clone();
                                }
                            }
                        });
                    ui.end_row();

                    ui.label("ГРНТИ:");
                    ui.text_edit_singleline(&mut self.state.project_draft.grnti_code);
                    ui.end_row();

                    ui.label("План (руб.):");
                    ui.add(egui::DragValue::new(&mut self.state.project_draft.plan_fin).speed(10000.0).range(0..=1_000_000_000));
                    ui.end_row();

                    ui.label("Руководитель ФИО:");
                    ui.text_edit_singleline(&mut self.state.project_draft.leader_fio);
                    ui.end_row();

                    ui.label("Должность:");
                    ui.text_edit_singleline(&mut self.state.project_draft.leader_post);
                    ui.end_row();

                    ui.label("Тема НИР:");
                    ui.text_edit_multiline(&mut self.state.project_draft.proj_name);
                    ui.end_row();
                });

                if !self.state.project_dialog_error.is_empty() {
                    ui.label(RichText::new(&self.state.project_dialog_error).color(Color32::RED));
                }

                ui.add_space(8.0);
                ui.horizontal(|ui| {
                    if ui.button("Сохранить").clicked() {
                        if !models::validate_grnti(&self.state.project_draft.grnti_code) {
                            self.state.project_dialog_error = "Неверный формат ГРНТИ (ожидается XX.XX.XX)".to_string();
                            return;
                        }

                        if let Ok(conn) = self.state.open_conn() {
                            let exclude = if self.state.project_dialog_is_edit {
                                Some(self.state.project_draft.id)
                            } else {
                                None
                            };
                            let is_unique = models::check_unique_project_code(
                                &conn,
                                self.state.project_draft.codkon,
                                self.state.project_draft.codproj,
                                exclude,
                            )
                            .unwrap_or(false);

                            if !is_unique {
                                self.state.project_dialog_error = format!(
                                    "Шифр проекта {} уже существует в конкурсе {}",
                                    self.state.project_draft.codproj, self.state.project_draft.codkon
                                );
                                return;
                            }

                            if self.state.project_dialog_is_edit {
                                let _ = models::update_project(&conn, &self.state.project_draft);
                            } else {
                                let _ = models::insert_project(&conn, &self.state.project_draft);
                            }
                            self.state.reload_all();
                            self.state.project_dialog_open = false;
                        }
                    }
                    if ui.button("Отмена").clicked() {
                        self.state.project_dialog_open = false;
                    }
                });
            });
    }

    fn render_filter_dialog(&mut self, ctx: &egui::Context) {
        if !self.state.filter_dialog_open {
            return;
        }

        egui::Window::new("Фильтрация проектов НИР")
            .collapsible(false)
            .anchor(egui::Align2::CENTER_CENTER, [0.0, 0.0])
            .show(ctx, |ui| {
                ui.set_min_width(400.0);

                ui.heading("Фильтр по конкурсу:");
                ui.horizontal(|ui| {
                    ui.label("Конкурс:");
                    let current_text = match self.state.filter_draft.codkon {
                        Some(k) => format!("Конкурс {}", k),
                        None => "Все конкурсы".to_string(),
                    };
                    egui::ComboBox::from_id_salt("flt_konk_combo")
                        .selected_text(current_text)
                        .show_ui(ui, |ui| {
                            ui.selectable_value(&mut self.state.filter_draft.codkon, None, "Все конкурсы");
                            for c in &self.state.contests {
                                ui.selectable_value(&mut self.state.filter_draft.codkon, Some(c.codkon), format!("{}: {}", c.codkon, c.konk_name));
                            }
                        });
                });

                ui.separator();
                ui.heading("Географический фильтр по вузам:");

                if let Ok(conn) = self.state.open_conn() {
                    // Регионы
                    let regions = filter::get_distinct_regions(&conn).unwrap_or_default();
                    ui.horizontal(|ui| {
                        ui.label("Фед. округ:");
                        let text = self.state.filter_draft.region.clone().unwrap_or_else(|| "Все округа".to_string());
                        egui::ComboBox::from_id_salt("flt_reg_combo")
                            .selected_text(text)
                            .show_ui(ui, |ui| {
                                if ui.selectable_label(self.state.filter_draft.region.is_none(), "Все округа").clicked() {
                                    self.state.filter_draft.region = None;
                                    self.state.filter_draft.obl_name = None;
                                    self.state.filter_draft.city = None;
                                    self.state.filter_draft.codvuz = None;
                                }
                                for r in &regions {
                                    if ui.selectable_label(self.state.filter_draft.region.as_deref() == Some(r), r).clicked() {
                                        self.state.filter_draft.region = Some(r.clone());
                                        self.state.filter_draft.obl_name = None;
                                        self.state.filter_draft.city = None;
                                        self.state.filter_draft.codvuz = None;
                                    }
                                }
                            });
                    });

                    // Субъекты РФ
                    let obls = filter::get_distinct_obls(&conn, self.state.filter_draft.region.as_deref()).unwrap_or_default();
                    ui.horizontal(|ui| {
                        ui.label("Субъект РФ:");
                        let text = self.state.filter_draft.obl_name.clone().unwrap_or_else(|| "Все субъекты".to_string());
                        egui::ComboBox::from_id_salt("flt_obl_combo")
                            .selected_text(text)
                            .show_ui(ui, |ui| {
                                if ui.selectable_label(self.state.filter_draft.obl_name.is_none(), "Все субъекты").clicked() {
                                    self.state.filter_draft.obl_name = None;
                                    self.state.filter_draft.city = None;
                                    self.state.filter_draft.codvuz = None;
                                }
                                for o in &obls {
                                    if ui.selectable_label(self.state.filter_draft.obl_name.as_deref() == Some(o), o).clicked() {
                                        self.state.filter_draft.obl_name = Some(o.clone());
                                        self.state.filter_draft.city = None;
                                        self.state.filter_draft.codvuz = None;
                                    }
                                }
                            });
                    });

                    // Города
                    let cities = filter::get_distinct_cities(&conn, self.state.filter_draft.obl_name.as_deref()).unwrap_or_default();
                    ui.horizontal(|ui| {
                        ui.label("Город:");
                        let text = self.state.filter_draft.city.clone().unwrap_or_else(|| "Все города".to_string());
                        egui::ComboBox::from_id_salt("flt_city_combo")
                            .selected_text(text)
                            .show_ui(ui, |ui| {
                                if ui.selectable_label(self.state.filter_draft.city.is_none(), "Все города").clicked() {
                                    self.state.filter_draft.city = None;
                                    self.state.filter_draft.codvuz = None;
                                }
                                for c in &cities {
                                    if ui.selectable_label(self.state.filter_draft.city.as_deref() == Some(c), c).clicked() {
                                        self.state.filter_draft.city = Some(c.clone());
                                        self.state.filter_draft.codvuz = None;
                                    }
                                }
                            });
                    });

                    // Вузы
                    let vuz_list = filter::get_vuz_list_filtered(
                        &conn,
                        self.state.filter_draft.city.as_deref(),
                        self.state.filter_draft.obl_name.as_deref(),
                    )
                    .unwrap_or_default();
                    ui.horizontal(|ui| {
                        ui.label("Вуз:");
                        let text = match self.state.filter_draft.codvuz {
                            Some(v) => vuz_list
                                .iter()
                                .find(|(id, _)| *id == v)
                                .map(|(_, name)| name.clone())
                                .unwrap_or_else(|| format!("Вуз {}", v)),
                            None => "Все вузы".to_string(),
                        };
                        egui::ComboBox::from_id_salt("flt_vuz_combo")
                            .selected_text(text)
                            .show_ui(ui, |ui| {
                                ui.selectable_value(&mut self.state.filter_draft.codvuz, None, "Все вузы");
                                for (id, name) in &vuz_list {
                                    ui.selectable_value(&mut self.state.filter_draft.codvuz, Some(*id), name);
                                }
                            });
                    });
                }

                ui.add_space(8.0);
                ui.horizontal(|ui| {
                    if ui.button("Применить").clicked() {
                        self.state.current_filter = self.state.filter_draft.clone();
                        if let Ok(conn) = self.state.open_conn() {
                            self.state.reload_projects(&conn);
                            self.state.refresh_report_data(&conn);
                        }
                        self.state.filter_dialog_open = false;
                    }
                    if ui.button("Сбросить").clicked() {
                        self.state.filter_draft.clear();
                    }
                    if ui.button("Отмена").clicked() {
                        self.state.filter_dialog_open = false;
                    }
                });
            });
    }

    fn render_delete_dialog(&mut self, ctx: &egui::Context) {
        if !self.state.delete_confirm_open {
            return;
        }

        egui::Window::new("Подтверждение удаления")
            .collapsible(false)
            .anchor(egui::Align2::CENTER_CENTER, [0.0, 0.0])
            .show(ctx, |ui| {
                ui.label("Вы действительно хотите удалить выбранный проект НИР?");
                ui.add_space(8.0);
                ui.horizontal(|ui| {
                    if ui.button("Да, удалить").clicked() {
                        if let Some(id) = self.state.delete_target_id {
                            if let Ok(conn) = self.state.open_conn() {
                                let _ = models::delete_project(&conn, id);
                                self.state.selected_project_idx = None;
                                self.state.reload_all();
                            }
                        }
                        self.state.delete_confirm_open = false;
                    }
                    if ui.button("Отмена").clicked() {
                        self.state.delete_confirm_open = false;
                    }
                });
            });
    }

    fn render_approve_dialog(&mut self, ctx: &egui::Context) {
        if !self.state.approve_confirm_open {
            return;
        }

        egui::Window::new("Утверждение распоряжения")
            .collapsible(false)
            .anchor(egui::Align2::CENTER_CENTER, [0.0, 0.0])
            .show(ctx, |ui| {
                if let Some(ref dist) = self.state.calculated_tranche {
                    ui.label(format!(
                        "Утвердить проведение транша за {}-й квартал на сумму {} руб. ({:.2}% от плана)?",
                        self.state.finance_quarter,
                        crate::database::format_money(dist.total_distributed),
                        dist.percent
                    ));
                }
                ui.add_space(8.0);
                ui.horizontal(|ui| {
                    if ui.button("Да, утвердить").clicked() {
                        let to_exec = self.state.calculated_tranche.as_ref().map(|d| {
                            (
                                self.state.finance_quarter,
                                d.project_tranches.clone(),
                                d.total_distributed,
                            )
                        });
                        if let Some((q, tranches, total)) = to_exec {
                            if let Ok(mut conn) = self.state.open_conn() {
                                let _ = finance::execute_tranche_in_db(q, &tranches, &mut conn);
                                self.state.reload_all();
                                self.state.status_message = format!(
                                    "Транш за {}-й квартал на сумму {} руб. успешно зафиксирован в БД!",
                                    q,
                                    crate::database::format_money(total)
                                );
                            }
                        }
                        self.state.approve_confirm_open = false;
                    }
                    if ui.button("Отмена").clicked() {
                        self.state.approve_confirm_open = false;
                    }
                });
            });
    }

    fn render_reset_dialog(&mut self, ctx: &egui::Context) {
        if !self.state.reset_confirm_open {
            return;
        }

        egui::Window::new("Сброс финансирования квартала")
            .collapsible(false)
            .anchor(egui::Align2::CENTER_CENTER, [0.0, 0.0])
            .show(ctx, |ui| {
                ui.label(format!(
                    "Обнулить фактические выплаты за {}-й квартал (fin_q{} = 0)?",
                    self.state.finance_quarter, self.state.finance_quarter
                ));
                ui.add_space(8.0);
                ui.horizontal(|ui| {
                    if ui.button("Да, обнулить").clicked() {
                        if let Ok(mut conn) = self.state.open_conn() {
                            let _ = finance::reset_quarter_funding(self.state.finance_quarter, &mut conn);
                            self.state.reload_all();
                            self.state.status_message = format!(
                                "Финансирование {}-го квартала успешно сброшено в 0 руб.!",
                                self.state.finance_quarter
                            );
                        }
                        self.state.reset_confirm_open = false;
                    }
                    if ui.button("Отмена").clicked() {
                        self.state.reset_confirm_open = false;
                    }
                });
            });
    }

    fn render_export_dialog(&mut self, ctx: &egui::Context) {
        if !self.state.export_dialog_open {
            return;
        }

        egui::Window::new("Экспорт документа")
            .collapsible(false)
            .anchor(egui::Align2::CENTER_CENTER, [0.0, 0.0])
            .show(ctx, |ui| {
                ui.label("Укажите путь или имя файла (.xlsx, .html, .csv, .txt):");
                ui.text_edit_singleline(&mut self.state.export_path);
                ui.add_space(8.0);
                ui.horizontal(|ui| {
                    if ui.button("Сохранить").clicked() {
                        let path = std::path::Path::new(&self.state.export_path);
                        let rep_opt = if self.state.active_tab == ActiveTab::Finance {
                            self.state
                                .calculated_tranche
                                .as_ref()
                                .map(|d| finance::build_finance_document_report(d, self.state.finance_quarter))
                        } else {
                            self.state.current_report.clone()
                        };

                        if let Some(ref rep) = rep_opt {
                            let summary = self
                                .state
                                .open_conn()
                                .map(|c| self.state.current_filter.build_summary(&c))
                                .unwrap_or_default();
                            match crate::export::export_report_to_file(path, rep, &summary) {
                                Ok(()) => {
                                    self.state.status_message = format!("Файл успешно сохранен: {}", path.display());
                                    self.state.export_dialog_open = false;
                                }
                                Err(e) => {
                                    self.state.status_message = format!("Ошибка экспорта: {}", e);
                                }
                            }
                        }
                    }
                    if ui.button("Отмена").clicked() {
                        self.state.export_dialog_open = false;
                    }
                });
            });
    }
}

pub fn run_gui(db_path: PathBuf) -> eframe::Result {
    let options = eframe::NativeOptions {
        viewport: egui::ViewportBuilder::default()
            .with_inner_size([1200.0, 750.0])
            .with_title("АРМ сопровождения конкурсов на соискание грантов (Rust)"),
        ..Default::default()
    };

    eframe::run_native(
        "MPEI DBMS",
        options,
        Box::new(|cc| {
            setup_custom_fonts(&cc.egui_ctx);
            let state = AppState::new(db_path);
            Ok(Box::new(MainWindow { state }))
        }),
    )
}
