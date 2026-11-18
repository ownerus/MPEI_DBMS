use clap::{Args, Parser, Subcommand, ValueEnum};
use comfy_table::Table;
use std::path::PathBuf;

#[derive(Parser, Debug)]
#[command(
    name = "mpei-dbms",
    author = "Грудинин Е.К., Степанищев В.Р., Криштул А.Н.",
    version = "1.0.0",
    about = "АРМ сопровождения конкурсов на соискание грантов (Вариант № 7)",
    long_about = "Автоматизированное рабочее место сопровождения конкурсов на соискание грантов.\nПоддерживает графический интерфейс (GUI) и командную строку (CLI)."
)]
pub struct Cli {
    #[arg(short, long, help = "Путь к файлу базы данных SQLite")]
    pub db: Option<PathBuf>,

    #[arg(long, help = "Запустить графический интерфейс (по умолчанию при отсутствии команд)")]
    pub gui: bool,

    #[command(subcommand)]
    pub command: Option<Commands>,
}

#[derive(Subcommand, Debug)]
pub enum Commands {
    #[command(about = "Построение и экспорт аналитических отчетов")]
    Report(ReportArgs),

    #[command(about = "Управление финансированием проектов НИР")]
    Finance(FinanceArgs),

    #[command(about = "Просмотр и операции с проектами НИР")]
    Projects(ProjectsArgs),

    #[command(about = "Синхронизация агрегатов таблицы конкурсов gr_konk")]
    Sync,

    #[command(about = "Запуск графического интерфейса пользователя")]
    Gui,
}

#[derive(ValueEnum, Clone, Copy, Debug, PartialEq, Eq)]
pub enum ReportForm {
    #[value(name = "contest", alias = "1", help = "Форма 1: по конкурсам")]
    Contest,
    #[value(name = "vuz", alias = "2", help = "Форма 2: по вузам-исполнителям")]
    Vuz,
    #[value(name = "region", alias = "3", help = "Форма 3: по субъектам РФ")]
    Region,
}

#[derive(Args, Debug)]
pub struct ReportArgs {
    #[arg(short, long, value_enum, default_value = "contest", help = "Форма аналитического отчета")]
    pub form: ReportForm,

    #[arg(long, help = "Фильтр по коду конкурса (например, --contest 1)")]
    pub contest: Option<i64>,

    #[arg(short, long, help = "Путь для экспорта отчета (.xlsx, .html, .csv, .txt)")]
    pub export: Option<PathBuf>,
}

#[derive(Args, Debug)]
pub struct FinanceArgs {
    #[command(subcommand)]
    pub command: FinanceCommands,
}

#[derive(Subcommand, Debug)]
pub enum FinanceCommands {
    #[command(about = "Сводное состояние финансирования (план, факт, поквартальные итоги)")]
    Summary,

    #[command(about = "Расчет предварительного распределения транша")]
    Calc {
        #[arg(short, long, help = "Процент от общего плана финансирования (например, 25.0)")]
        percent: f64,

        #[arg(short, long, default_value = "1", help = "Номер квартала (1-4)")]
        quarter: u8,

        #[arg(short, long, help = "Экспорт ведомости в файл (.xlsx, .html, .csv, .txt)")]
        export: Option<PathBuf>,
    },

    #[command(about = "Утверждение транша и фиксация выплат в базе данных")]
    Approve {
        #[arg(short, long, help = "Процент от плана (например, 25.0)")]
        percent: f64,

        #[arg(short, long, help = "Номер квартала (1-4)")]
        quarter: u8,
    },

    #[command(about = "Очистка/сброс финансирования выбранного квартала (fin_qX = 0)")]
    Reset {
        #[arg(short, long, help = "Номер квартала для сброса (1-4)")]
        quarter: u8,
    },
}

#[derive(Args, Debug)]
pub struct ProjectsArgs {
    #[arg(long, help = "Фильтр по коду конкурса")]
    pub contest: Option<i64>,

    #[arg(long, help = "Сортировать по составному ключу (codkon, codproj)")]
    pub sort_key: bool,

    #[arg(long, help = "Ограничить количество выводимых записей")]
    pub limit: Option<usize>,
}

pub fn run_cli_command(cli: &Cli, db_path: &std::path::Path) -> Result<(), Box<dyn std::error::Error>> {
    let mut conn = crate::database::connect_db(db_path)?;
    crate::database::sync_contest_aggregates(&conn, None)?;

    match &cli.command {
        Some(Commands::Report(args)) => {
            let filter_where = if let Some(k) = args.contest {
                format!("codkon = {}", k)
            } else {
                String::new()
            };
            let filter_summary = if let Some(k) = args.contest {
                format!("Конкурс {}", k)
            } else {
                String::new()
            };

            let report = match args.form {
                ReportForm::Contest => crate::reports::build_contest_report(&conn, &filter_where)?,
                ReportForm::Vuz => crate::reports::build_vuz_report(&conn, &filter_where)?,
                ReportForm::Region => crate::reports::build_region_report(&conn, &filter_where)?,
            };

            if let Some(ref export_path) = args.export {
                crate::export::export_report_to_file(export_path, &report, &filter_summary)?;
                println!("Отчет успешно экспортирован в: {}", export_path.display());
            } else {
                let mut table = Table::new();
                table.set_header(&report.headers);
                for row in &report.rows {
                    table.add_row(row);
                }
                if !report.totals.is_empty() {
                    table.add_row(&report.totals);
                }
                println!("\n=== {} ===", report.title);
                if !filter_summary.is_empty() {
                    println!("Условия отбора: {}", filter_summary);
                }
                println!("{}\n", table);
            }
        }
        Some(Commands::Finance(args)) => match &args.command {
            FinanceCommands::Summary => {
                let sum = crate::finance::get_finance_summary(&conn)?;
                println!("\n=== Текущее состояние финансирования ===");
                println!("Вузов-исполнителей:          {}", sum.vuz_count);
                println!("Проектов НИР:                {}", sum.proj_count);
                println!("Суммарный план:              {} руб.", crate::database::format_money(sum.total_plan));
                println!("Фактически профинансировано: {} руб. ({:.2}% от плана)", crate::database::format_money(sum.total_fact), sum.fact_pct);
                println!("Поквартальный факт:");
                println!("  1-й квартал: {} руб.", crate::database::format_money(sum.q1));
                println!("  2-й квартал: {} руб.", crate::database::format_money(sum.q2));
                println!("  3-й квартал: {} руб.", crate::database::format_money(sum.q3));
                println!("  4-й квартал: {} руб.\n", crate::database::format_money(sum.q4));
            }
            FinanceCommands::Calc { percent, quarter, export } => {
                if *percent <= 0.0 {
                    return Err("Процент финансирования должен быть положительным числом".into());
                }
                let dist = crate::finance::calculate_tranche_distribution(*percent, &conn)?;
                let doc_report = crate::finance::build_finance_document_report(&dist, *quarter);

                if let Some(ref export_path) = export {
                    crate::export::export_report_to_file(export_path, &doc_report, "")?;
                    println!("Ведомость выплат успешно экспортирована в: {}", export_path.display());
                } else {
                    let mut table = Table::new();
                    table.set_header(&doc_report.headers);
                    for row in &doc_report.rows {
                        table.add_row(row);
                    }
                    table.add_row(&doc_report.totals);
                    println!("\n=== {} ===", doc_report.title);
                    println!("Расчетный транш: {} руб. по {} проектам ({} вузов)",
                        crate::database::format_money(dist.total_distributed),
                        dist.total_proj_count,
                        dist.vuz_rows.len()
                    );
                    println!("{}\n", table);
                }
            }
            FinanceCommands::Approve { percent, quarter } => {
                if !(1..=4).contains(quarter) {
                    return Err("Номер квартала должен быть от 1 до 4".into());
                }
                if *percent <= 0.0 {
                    return Err("Процент финансирования должен быть положительным".into());
                }
                let dist = crate::finance::calculate_tranche_distribution(*percent, &conn)?;
                crate::finance::execute_tranche_in_db(*quarter, &dist.project_tranches, &mut conn)?;
                println!("Транш ({:.2}% от плана) за {}-й квартал на сумму {} руб. успешно проведен в БД!",
                    percent, quarter, crate::database::format_money(dist.total_distributed));
            }
            FinanceCommands::Reset { quarter } => {
                if !(1..=4).contains(quarter) {
                    return Err("Номер квартала должен быть от 1 до 4".into());
                }
                crate::finance::reset_quarter_funding(*quarter, &mut conn)?;
                println!("Финансирование {}-го квартала успешно сброшено в 0 руб.!", quarter);
            }
        },
        Some(Commands::Projects(args)) => {
            let filter_where = args.contest.map(|k| format!("codkon = {}", k));
            let projects = crate::models::get_projects(&conn, filter_where.as_deref(), args.sort_key)?;

            let mut table = Table::new();
            table.set_header(&[
                "Код конкурса", "Код НИР", "Код вуза", "Вуз", "ГРНТИ", "План (руб.)", "Факт (руб.)", "Руководитель", "Тема НИР"
            ]);

            let limit = args.limit.unwrap_or(projects.len());
            for p in projects.iter().take(limit) {
                table.add_row(&[
                    p.codkon.to_string(),
                    p.codproj.to_string(),
                    p.codvuz.to_string(),
                    p.vuz_short_name.clone(),
                    p.grnti_code.clone(),
                    crate::database::format_money(p.plan_fin),
                    crate::database::format_money(p.fact_fin),
                    p.leader_fio.clone(),
                    if p.proj_name.chars().count() > 35 {
                        format!("{}...", p.proj_name.chars().take(32).collect::<String>())
                    } else {
                        p.proj_name.clone()
                    },
                ]);
            }
            println!("\n=== Реестр проектов НИР (всего {}) ===", projects.len());
            println!("{}\n", table);
        }
        Some(Commands::Sync) => {
            crate::database::sync_contest_aggregates(&conn, None)?;
            println!("Агрегаты таблицы gr_konk успешно синхронизированы по данным gr_proj.");
        }
        Some(Commands::Gui) | None => {
            // Handled in main
        }
    }
    Ok(())
}
