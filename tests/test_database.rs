use mpei_dbms::database::{get_default_db_path, sync_contest_aggregates};
use mpei_dbms::models::{
    check_unique_project_code, delete_project, get_contests, get_projects, get_universities,
    insert_project, suggest_next_codproj, update_project, validate_grnti, Project,
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
    let temp_dir = std::env::temp_dir().join(format!("mpei_db_crud_test_{}_{}", std::process::id(), nanos));
    fs::create_dir_all(&temp_dir).expect("Create temp dir");
    let dest = temp_dir.join("grants_crud.db");

    // Copy via SQLite backup to avoid file locks
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
fn test_database_counts_and_lookups() {
    let (_path, conn) = create_temp_db_copy();
    sync_contest_aggregates(&conn, None).expect("Sync");

    let projects = get_projects(&conn, None, false).expect("Get projects");
    assert_eq!(projects.len(), 400);

    let contests = get_contests(&conn).expect("Get contests");
    assert_eq!(contests.len(), 17);

    let universities = get_universities(&conn).expect("Get universities");
    assert_eq!(universities.len(), 342);
}

#[test]
fn test_project_crud_and_validation() {
    let (_path, conn) = create_temp_db_copy();

    // 1. Suggest next code for contest 1
    let next_code = suggest_next_codproj(&conn, 1).expect("Suggest next code");
    assert_eq!(next_code, 122, "Next project code in contest 1 should be 122");

    // 2. Validate GRNTI
    assert!(validate_grnti("55.03.35"));
    assert!(validate_grnti("20.15.01; 55.03.35"));
    assert!(!validate_grnti("55.3"));
    assert!(!validate_grnti("invalid"));

    // 3. Uniqueness check: (1, next_code=122) is free; (1, 2) is already occupied
    assert!(check_unique_project_code(&conn, 1, next_code, None).unwrap());
    assert!(!check_unique_project_code(&conn, 1, 2, None).unwrap());

    // 4. Insert new project
    let new_proj = Project {
        id: 0,
        codkon: 1,
        codproj: next_code,
        codvuz: 1,
        vuz_short_name: "МЭИ".to_string(),
        grnti_code: "55.03.35".to_string(),
        plan_fin: 1_500_000,
        fact_fin: 0,
        fin_q1: 0,
        fin_q2: 0,
        fin_q3: 0,
        fin_q4: 0,
        leader_fio: "Тестовый Руководитель".to_string(),
        leader_post: "Профессор".to_string(),
        leader_rank: "Профессор".to_string(),
        leader_degree: "д.т.н.".to_string(),
        proj_name: "Тестовое исследование на Rust".to_string(),
    };

    let new_id = insert_project(&conn, &new_proj).expect("Insert project");
    assert!(new_id > 0);

    let after_insert = get_projects(&conn, None, false).unwrap();
    assert_eq!(after_insert.len(), 401);

    // 5. Update project
    let mut updated = new_proj.clone();
    updated.id = new_id;
    updated.proj_name = "Обновленная тема на Rust".to_string();
    update_project(&conn, &updated).expect("Update project");

    // 6. Delete project
    delete_project(&conn, new_id).expect("Delete project");
    let after_delete = get_projects(&conn, None, false).unwrap();
    assert_eq!(after_delete.len(), 400);
}
