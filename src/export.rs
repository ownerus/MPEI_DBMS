use crate::reports::ReportData;
use chrono::Local;
use comfy_table::Table;
use rust_xlsxwriter::{Color, Format, FormatBorder, Workbook};
use std::fs::File;
use std::io::Write;
use std::path::Path;

pub fn export_report_to_file(
    file_path: &Path,
    report: &ReportData,
    filter_summary: &str,
) -> Result<(), Box<dyn std::error::Error>> {
    let ext = file_path
        .extension()
        .and_then(|s| s.to_str())
        .unwrap_or("")
        .to_lowercase();

    match ext.as_str() {
        "xlsx" => export_to_xlsx(file_path, report, filter_summary),
        "html" | "htm" => export_to_html(file_path, report, filter_summary),
        "csv" => export_to_csv(file_path, report),
        "txt" => export_to_txt(file_path, report, filter_summary),
        _ => export_to_xlsx(file_path, report, filter_summary),
    }
}

pub fn export_to_xlsx(
    file_path: &Path,
    report: &ReportData,
    filter_summary: &str,
) -> Result<(), Box<dyn std::error::Error>> {
    let mut workbook = Workbook::new();
    let worksheet = workbook.add_worksheet();

    let title_format = Format::new().set_bold().set_font_size(14);
    let meta_format = Format::new().set_italic().set_font_size(10);
    let header_format = Format::new()
        .set_bold()
        .set_background_color(Color::RGB(0xE8EEF4))
        .set_border(FormatBorder::Thin);
    let cell_format = Format::new().set_border(FormatBorder::Thin);
    let total_format = Format::new()
        .set_bold()
        .set_background_color(Color::RGB(0xF1F3F5))
        .set_border(FormatBorder::Thin);

    let mut current_row: u32 = 0;

    worksheet.write_string_with_format(current_row, 0, &report.title, &title_format)?;
    current_row += 1;

    let now_str = Local::now().format("%d.%m.%Y %H:%M:%S").to_string();
    worksheet.write_string_with_format(
        current_row,
        0,
        &format!("Дата формирования: {}", now_str),
        &meta_format,
    )?;
    current_row += 1;

    if !filter_summary.trim().is_empty() {
        worksheet.write_string_with_format(
            current_row,
            0,
            &format!("Условия отбора: {}", filter_summary),
            &meta_format,
        )?;
        current_row += 1;
    }
    current_row += 1; // Пустая строка перед таблицей

    // Заголовки таблицы
    for (col_idx, header) in report.headers.iter().enumerate() {
        worksheet.write_string_with_format(current_row, col_idx as u16, header, &header_format)?;
    }
    current_row += 1;

    // Строки данных
    for row in &report.rows {
        for (col_idx, val) in row.iter().enumerate() {
            worksheet.write_string_with_format(current_row, col_idx as u16, val, &cell_format)?;
        }
        current_row += 1;
    }

    // Итоговая строка
    if !report.totals.is_empty() {
        for (col_idx, val) in report.totals.iter().enumerate() {
            worksheet.write_string_with_format(current_row, col_idx as u16, val, &total_format)?;
        }
    }

    worksheet.autofit();
    workbook.save(file_path)?;
    Ok(())
}

pub fn export_to_html(
    file_path: &Path,
    report: &ReportData,
    filter_summary: &str,
) -> Result<(), Box<dyn std::error::Error>> {
    let now_str = Local::now().format("%d.%m.%Y %H:%M:%S").to_string();
    let mut html = String::new();

    html.push_str("<!DOCTYPE html>\n<html lang=\"ru\">\n<head>\n");
    html.push_str("<meta charset=\"utf-8\">\n");
    html.push_str(&format!("<title>{}</title>\n", report.title));
    html.push_str("<style>\n");
    html.push_str("body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; margin: 24px; color: #1c2430; background: #fafafa; }\n");
    html.push_str("h1 { font-size: 20px; color: #1e3a5f; margin-bottom: 8px; }\n");
    html.push_str(".meta { font-size: 13px; color: #5c6b7a; margin-bottom: 16px; }\n");
    html.push_str("table { border-collapse: collapse; width: 100%; background: #fff; box-shadow: 0 1px 3px rgba(0,0,0,0.1); border-radius: 6px; overflow: hidden; }\n");
    html.push_str("th, td { border: 1px solid #d8dde3; padding: 8px 12px; font-size: 13px; }\n");
    html.push_str("th { background: #e8eef4; color: #1e3a5f; font-weight: 600; text-align: left; }\n");
    html.push_str(".total { background: #f1f3f5; font-weight: bold; }\n");
    html.push_str(".num { text-align: right; }\n");
    html.push_str("</style>\n</head>\n<body>\n");

    html.push_str(&format!("<h1>{}</h1>\n", report.title));
    html.push_str(&format!("<div class=\"meta\">Дата формирования: {}</div>\n", now_str));
    if !filter_summary.trim().is_empty() {
        html.push_str(&format!("<div class=\"meta\">Условия отбора: {}</div>\n", filter_summary));
    }

    html.push_str("<table>\n<thead>\n<tr>\n");
    for (i, h) in report.headers.iter().enumerate() {
        let align_class = if report.numeric_cols.contains(&i) { " class=\"num\"" } else { "" };
        html.push_str(&format!("<th{}>{}</th>", align_class, h));
    }
    html.push_str("\n</tr>\n</thead>\n<tbody>\n");

    for row in &report.rows {
        html.push_str("<tr>\n");
        for (i, cell) in row.iter().enumerate() {
            let align_class = if report.numeric_cols.contains(&i) { " class=\"num\"" } else { "" };
            html.push_str(&format!("<td{}>{}</td>", align_class, cell));
        }
        html.push_str("\n</tr>\n");
    }

    if !report.totals.is_empty() {
        html.push_str("<tr class=\"total\">\n");
        for (i, cell) in report.totals.iter().enumerate() {
            let align_class = if report.numeric_cols.contains(&i) { " class=\"num\"" } else { "" };
            html.push_str(&format!("<td{}>{}</td>", align_class, cell));
        }
        html.push_str("\n</tr>\n");
    }

    html.push_str("</tbody>\n</table>\n</body>\n</html>");

    let mut file = File::create(file_path)?;
    file.write_all(html.as_bytes())?;
    Ok(())
}

pub fn export_to_csv(
    file_path: &Path,
    report: &ReportData,
) -> Result<(), Box<dyn std::error::Error>> {
    let mut file = File::create(file_path)?;
    // UTF-8 BOM for Microsoft Excel compatibility
    file.write_all(&[0xEF, 0xBB, 0xBF])?;

    let mut wtr = csv::WriterBuilder::new()
        .delimiter(b';')
        .from_writer(file);

    wtr.write_record(&report.headers)?;
    for row in &report.rows {
        wtr.write_record(row)?;
    }
    if !report.totals.is_empty() {
        wtr.write_record(&report.totals)?;
    }
    wtr.flush()?;
    Ok(())
}

pub fn export_to_txt(
    file_path: &Path,
    report: &ReportData,
    filter_summary: &str,
) -> Result<(), Box<dyn std::error::Error>> {
    let now_str = Local::now().format("%d.%m.%Y %H:%M:%S").to_string();
    let mut table = Table::new();
    table.set_header(&report.headers);
    for row in &report.rows {
        table.add_row(row);
    }
    if !report.totals.is_empty() {
        table.add_row(&report.totals);
    }

    let mut output = String::new();
    output.push_str(&report.title);
    output.push('\n');
    output.push_str(&format!("Дата формирования: {}\n", now_str));
    if !filter_summary.trim().is_empty() {
        output.push_str(&format!("Условия отбора: {}\n", filter_summary));
    }
    output.push('\n');
    output.push_str(&table.to_string());
    output.push('\n');

    let mut file = File::create(file_path)?;
    file.write_all(output.as_bytes())?;
    Ok(())
}
