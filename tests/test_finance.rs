use mpei_dbms::database::{get_default_db_path, sync_contest_aggregates};
use mpei_dbms::finance::{
    calculate_tranche_distribution, execute_tranche_in_db, get_finance_summary, reset_quarter_funding,
};
use rusqlite::Connection;
use std::fs;
use std::path::PathBuf;
use std::time::{SystemTime, UNIX_EPOCH};

fn create_temp_db_copy() -> (PathBuf, Connection) {
    let src = get_default_db_path();
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    let temp_dir = std::env::temp_dir().join(format!("mpei_fin_test_{}_{}", std::process::id(), nanos));
    fs::create_dir_all(&temp_dir).expect("Create temp dir");
    let dest = temp_dir.join("grants_test.db");

    let src_conn = Connection::open_with_flags(&src, rusqlite::OpenFlags::SQLITE_OPEN_READ_ONLY)
        .expect("Open source DB readonly");
    let mut dest_conn = Connection::open(&dest).expect("Open dest DB");
    {
        let backup = rusqlite::backup::Backup::new(&src_conn, &mut dest_conn).expect("Init backup");
        backup.run_to_completion(100, std::time::Duration::from_millis(50), None).expect("Run backup");
    }

    (dest, dest_conn)
}

#[test]
fn test_finance_summary_baseline() {
    let (_path, conn) = create_temp_db_copy();
    sync_contest_aggregates(&conn, None).expect("Sync");

    let sum = get_finance_summary(&conn).expect("Get summary");
    assert_eq!(sum.vuz_count, 70, "Distinct VUZ in projects must be 70");
    assert_eq!(sum.proj_count, 400, "Projects count must be 400");
    assert_eq!(sum.total_plan, 201_270_000, "Total plan must be 201 270 000");
    assert_eq!(sum.total_fact, 0, "Initial fact must be 0");
    assert_eq!(sum.q1, 0);
    assert_eq!(sum.q2, 0);
    assert_eq!(sum.q3, 0);
    assert_eq!(sum.q4, 0);
    assert_eq!(sum.fact_pct, 0.0);
}

#[test]
fn test_tranche_calculation_discrete_rounding() {
    let (_path, conn) = create_temp_db_copy();

    // 25% tranche
    let dist_25 = calculate_tranche_distribution(25.0, &conn).expect("Calc 25%");
    assert_eq!(dist_25.total_plan, 201_270_000);
    assert_eq!(dist_25.total_distributed, 50_317_500, "25% must be exactly 50 317 500");
    assert_eq!(dist_25.total_proj_count, 400);
    assert_eq!(dist_25.vuz_rows.len(), 70);

    // 33.33% tranche: tests discrete integer rounding
    let dist_33 = calculate_tranche_distribution(33.33, &conn).expect("Calc 33.33%");
    assert_eq!(dist_33.total_plan, 201_270_000);
    assert_eq!(dist_33.total_distributed, 67_083_293, "33.33% must be 67 083 293");
    assert_eq!(dist_33.total_proj_count, 400);
    assert_eq!(dist_33.vuz_rows.len(), 70);
}

#[test]
fn test_tranche_execution_and_reset_in_db() {
    let (path, mut conn) = create_temp_db_copy();

    // 1. Commit Q1 (25%)
    let dist_q1 = calculate_tranche_distribution(25.0, &conn).expect("Calc Q1");
    execute_tranche_in_db(1, &dist_q1.project_tranches, &mut conn).expect("Commit Q1");

    let sum1 = get_finance_summary(&conn).expect("Summary 1");
    assert_eq!(sum1.q1, 50_317_500);
    assert_eq!(sum1.total_fact, 50_317_500);

    // Verify contest aggregates in gr_konk
    let (k_fact, k_q1): (i64, i64) = conn
        .query_row("SELECT SUM(fact_fin), SUM(fin_q1) FROM gr_konk", [], |r| {
            Ok((r.get(0)?, r.get(1)?))
        })
        .expect("Query gr_konk");
    assert_eq!(k_fact, 50_317_500);
    assert_eq!(k_q1, 50_317_500);

    // 2. Commit Q4 (25%)
    let dist_q4 = calculate_tranche_distribution(25.0, &conn).expect("Calc Q4");
    execute_tranche_in_db(4, &dist_q4.project_tranches, &mut conn).expect("Commit Q4");

    let sum2 = get_finance_summary(&conn).expect("Summary 2");
    assert_eq!(sum2.q1, 50_317_500);
    assert_eq!(sum2.q4, 50_317_500);
    assert_eq!(sum2.total_fact, 100_635_000);
    assert!((sum2.fact_pct - 50.0).abs() < 0.001);

    // 3. Reset Q4
    reset_quarter_funding(4, &mut conn).expect("Reset Q4");

    let sum3 = get_finance_summary(&conn).expect("Summary 3");
    assert_eq!(sum3.q4, 0, "Q4 must be 0 after reset");
    assert_eq!(sum3.q1, 50_317_500, "Q1 must remain intact after Q4 reset");
    assert_eq!(sum3.total_fact, 50_317_500);

    // 4. Reset Q1
    reset_quarter_funding(1, &mut conn).expect("Reset Q1");

    let sum4 = get_finance_summary(&conn).expect("Summary 4");
    assert_eq!(sum4.total_fact, 0, "Fact must be back to 0");
    assert_eq!(sum4.q1, 0);
    assert_eq!(sum4.q4, 0);

    drop(conn);
    let _ = fs::remove_file(&path);
}
