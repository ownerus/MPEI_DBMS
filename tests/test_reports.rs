use mpei_dbms::database::{connect_db, get_default_db_path, sync_contest_aggregates};
use mpei_dbms::reports::{build_contest_report, build_region_report, build_vuz_report};

#[test]
fn test_all_reports_baseline() {
    let db_path = get_default_db_path();
    assert!(db_path.is_file(), "Database file not found at: {:?}", db_path);

    let conn = connect_db(&db_path).expect("Failed to connect to database");
    sync_contest_aggregates(&conn, None).expect("Failed to sync contest aggregates");

    // Form 1: by contest
    let rep1 = build_contest_report(&conn, "").expect("Failed to build form 1");
    assert_eq!(rep1.rows.len(), 17, "Expected 17 contests in Form 1");
    assert_eq!(rep1.totals[3], "400", "Total projects must be 400");
    assert_eq!(rep1.totals[4], "201 270 000", "Total plan must be 201 270 000");
    assert_eq!(rep1.totals[5], "70", "Total distinct VUZ must be 70");

    // Form 2: by university
    let rep2 = build_vuz_report(&conn, "").expect("Failed to build form 2");
    assert_eq!(rep2.rows.len(), 70, "Expected 70 universities in Form 2");
    assert_eq!(rep2.totals[5], "400", "Total projects must be 400");
    assert_eq!(rep2.totals[6], "201 270 000", "Total plan must be 201 270 000");
    assert_eq!(rep2.totals[7], "15", "Total distinct contests must be 15");

    // Form 3: by region / subject
    let rep3 = build_region_report(&conn, "").expect("Failed to build form 3");
    assert_eq!(rep3.rows.len(), 35, "Expected 35 subjects in Form 3");
    assert_eq!(rep3.totals[4], "400", "Total projects must be 400");
    assert_eq!(rep3.totals[5], "201 270 000", "Total plan must be 201 270 000");
    assert_eq!(rep3.totals[6], "70", "Total distinct VUZ must be 70");
}

#[test]
fn test_reports_with_filter() {
    let db_path = get_default_db_path();
    let conn = connect_db(&db_path).expect("Failed to connect to database");

    // Filter by contest 1
    let rep1 = build_contest_report(&conn, "codkon = 1").expect("Form 1 filtered");
    assert_eq!(rep1.rows.len(), 1, "Only contest 1 in Form 1");

    let rep2 = build_vuz_report(&conn, "codkon = 1").expect("Form 2 filtered");
    assert_eq!(rep2.rows.len(), 22, "22 universities participate in contest 1");
    assert_eq!(rep2.totals[7], "1", "Only 1 distinct contest in Form 2");

    let rep3 = build_region_report(&conn, "codkon = 1").expect("Form 3 filtered");
    assert_eq!(rep3.rows.len(), 15, "15 regions participate in contest 1");
}
