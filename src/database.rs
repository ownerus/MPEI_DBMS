use rusqlite::Connection;
use std::path::{Path, PathBuf};

pub const EMBEDDED_SEED_DB: &[u8] = include_bytes!("../databases/grants.db");

pub fn get_default_db_path() -> PathBuf {
    // 1. Check relative to current executable location
    if let Ok(exe) = std::env::current_exe() {
        if let Some(exe_dir) = exe.parent() {
            let exe_local = exe_dir.join("databases").join("grants.db");
            if exe_local.is_file() {
                return exe_local;
            }
            let exe_parent = exe_dir.join("..").join("databases").join("grants.db");
            if exe_parent.is_file() {
                return exe_parent;
            }
            let exe_root = exe_dir.join("..").join("..").join("databases").join("grants.db");
            if exe_root.is_file() {
                return exe_root;
            }
        }
    }

    // 2. Check current working directory variants
    for candidate in &[
        "databases/grants.db",
        "СУБД/databases/grants.db",
        "../databases/grants.db",
        "../../databases/grants.db",
    ] {
        let p = PathBuf::from(candidate);
        if p.is_file() {
            return p;
        }
    }

    // 3. Check %LOCALAPPDATA%/MPEI_DBMS/grants.db (or automatically seed if running standalone)
    if let Ok(appdata) = std::env::var("LOCALAPPDATA") {
        let dir = PathBuf::from(appdata).join("MPEI_DBMS");
        let user_path = dir.join("grants.db");
        if user_path.is_file() {
            return user_path;
        }
        let _ = std::fs::create_dir_all(&dir);
        if std::fs::write(&user_path, EMBEDDED_SEED_DB).is_ok() {
            return user_path;
        }
    }

    PathBuf::from("databases/grants.db")
}

pub fn connect_db(path: &Path) -> Result<Connection, rusqlite::Error> {
    Connection::open(path)
}

pub fn sync_contest_aggregates(conn: &Connection, codkon: Option<i64>) -> Result<(), rusqlite::Error> {
    let mut sql = String::from(
        "UPDATE gr_konk
         SET projects_count = (SELECT COUNT(*) FROM gr_proj WHERE gr_proj.codkon = gr_konk.codkon),
             plan_fin = (SELECT COALESCE(SUM(plan_fin), 0) FROM gr_proj WHERE gr_proj.codkon = gr_konk.codkon),
             fact_fin = (SELECT COALESCE(SUM(fact_fin), 0) FROM gr_proj WHERE gr_proj.codkon = gr_konk.codkon),
             fin_q1 = (SELECT COALESCE(SUM(fin_q1), 0) FROM gr_proj WHERE gr_proj.codkon = gr_konk.codkon),
             fin_q2 = (SELECT COALESCE(SUM(fin_q2), 0) FROM gr_proj WHERE gr_proj.codkon = gr_konk.codkon),
             fin_q3 = (SELECT COALESCE(SUM(fin_q3), 0) FROM gr_proj WHERE gr_proj.codkon = gr_konk.codkon),
             fin_q4 = (SELECT COALESCE(SUM(fin_q4), 0) FROM gr_proj WHERE gr_proj.codkon = gr_konk.codkon)",
    );
    if let Some(c) = codkon {
        sql.push_str(" WHERE codkon = ?");
        conn.execute(&sql, [c])?;
    } else {
        conn.execute(&sql, [])?;
    }
    Ok(())
}

pub fn format_money(val: i64) -> String {
    let s = val.abs().to_string();
    let mut result = String::new();
    let len = s.len();
    for (i, ch) in s.chars().enumerate() {
        if i > 0 && (len - i) % 3 == 0 {
            result.push(' ');
        }
        result.push(ch);
    }
    if val < 0 {
        format!("-{}", result)
    } else {
        result
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_format_money() {
        assert_eq!(format_money(0), "0");
        assert_eq!(format_money(100), "100");
        assert_eq!(format_money(1000), "1 000");
        assert_eq!(format_money(50317500), "50 317 500");
        assert_eq!(format_money(201270000), "201 270 000");
        assert_eq!(format_money(-5000), "-5 000");
    }
}
