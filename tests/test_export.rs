use mpei_dbms::database::{connect_db, get_default_db_path};
use mpei_dbms::export::export_report_to_file;
use mpei_dbms::reports::build_contest_report;
use std::fs;

#[test]
fn test_export_all_formats() {
    let db_path = get_default_db_path();
    let conn = connect_db(&db_path).expect("Connect DB");
    let report = build_contest_report(&conn, "").expect("Build report");

    let temp_dir = std::env::temp_dir().join(format!("mpei_export_test_{}", std::process::id()));
    fs::create_dir_all(&temp_dir).expect("Create temp dir");

    let formats = ["xlsx", "html", "csv", "txt"];
    for ext in formats {
        let file_path = temp_dir.join(format!("report_export.{}", ext));
        export_report_to_file(&file_path, &report, "Тестовый фильтр").expect("Export");
        assert!(file_path.is_file(), "File {:?} should exist", file_path);
        let size = fs::metadata(&file_path).expect("Metadata").len();
        assert!(size > 500, "File {:?} must be non-empty (size: {})", file_path, size);
    }

    let _ = fs::remove_dir_all(&temp_dir);
}
