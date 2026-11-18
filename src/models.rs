use rusqlite::{params, Connection, Result, Row};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Project {
    pub id: i64,
    pub codkon: i64,
    pub codproj: i64,
    pub codvuz: i64,
    pub vuz_short_name: String,
    pub grnti_code: String,
    pub plan_fin: i64,
    pub fact_fin: i64,
    pub fin_q1: i64,
    pub fin_q2: i64,
    pub fin_q3: i64,
    pub fin_q4: i64,
    pub leader_fio: String,
    pub leader_post: String,
    pub leader_rank: String,
    pub leader_degree: String,
    pub proj_name: String,
}

impl Project {
    pub fn from_row(row: &Row) -> Result<Self> {
        Ok(Self {
            id: row.get(0)?,
            codkon: row.get(1)?,
            codproj: row.get(2)?,
            codvuz: row.get(3)?,
            vuz_short_name: row.get(4)?,
            grnti_code: row.get(5)?,
            plan_fin: row.get(6)?,
            fact_fin: row.get(7)?,
            fin_q1: row.get(8)?,
            fin_q2: row.get(9)?,
            fin_q3: row.get(10)?,
            fin_q4: row.get(11)?,
            leader_fio: row.get(12)?,
            leader_post: row.get(13)?,
            leader_rank: row.get(14)?,
            leader_degree: row.get(15)?,
            proj_name: row.get(16)?,
        })
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Contest {
    pub codkon: i64,
    pub konk_name: String,
    pub plan_fin: i64,
    pub fact_fin: i64,
    pub fin_q1: i64,
    pub fin_q2: i64,
    pub fin_q3: i64,
    pub fin_q4: i64,
    pub projects_count: i64,
}

impl Contest {
    pub fn from_row(row: &Row) -> Result<Self> {
        Ok(Self {
            codkon: row.get(0)?,
            konk_name: row.get(1)?,
            plan_fin: row.get(2)?,
            fact_fin: row.get(3)?,
            fin_q1: row.get(4)?,
            fin_q2: row.get(5)?,
            fin_q3: row.get(6)?,
            fin_q4: row.get(7)?,
            projects_count: row.get(8)?,
        })
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct University {
    pub codvuz: i64,
    pub vuz_short_name: String,
    pub vuz_name: String,
    pub vuz_full_name: String,
    pub status: String,
    pub city: String,
    pub region: String,
    pub obl_name: String,
    pub obl_code: String,
    pub profile: String,
    pub department: String,
}

impl University {
    pub fn from_row(row: &Row) -> Result<Self> {
        Ok(Self {
            codvuz: row.get(0)?,
            vuz_short_name: row.get(1)?,
            vuz_name: row.get(2)?,
            vuz_full_name: row.get(3)?,
            status: row.get(4)?,
            city: row.get(5)?,
            region: row.get(6)?,
            obl_name: row.get(7)?,
            obl_code: row.get(8)?,
            profile: row.get(9)?,
            department: row.get(10)?,
        })
    }
}

/// Проверка валидности формата кода ГРНТИ: XX.XX.XX (или нескольких кодов через точку с запятой)
pub fn validate_grnti(code: &str) -> bool {
    let parts: Vec<&str> = code.split(';').map(|s| s.trim()).collect();
    if parts.is_empty() {
        return false;
    }
    for part in parts {
        let sub: Vec<&str> = part.split('.').collect();
        if sub.len() != 3 {
            return false;
        }
        for s in sub {
            if s.len() != 2 || !s.chars().all(|c| c.is_ascii_digit()) {
                return false;
            }
        }
    }
    true
}

/// Предложение следующего шифра проекта внутри выбранного конкурса: MAX(codproj) + 1
pub fn suggest_next_codproj(conn: &Connection, codkon: i64) -> Result<i64> {
    let mut stmt = conn.prepare("SELECT COALESCE(MAX(codproj), 0) + 1 FROM gr_proj WHERE codkon = ?")?;
    let next_id: i64 = stmt.query_row([codkon], |row| row.get(0))?;
    Ok(next_id)
}

/// Проверка уникальности составного ключа (codkon, codproj)
pub fn check_unique_project_code(
    conn: &Connection,
    codkon: i64,
    codproj: i64,
    exclude_id: Option<i64>,
) -> Result<bool> {
    let count: i64 = if let Some(id) = exclude_id {
        conn.query_row(
            "SELECT COUNT(*) FROM gr_proj WHERE codkon = ? AND codproj = ? AND id != ?",
            params![codkon, codproj, id],
            |row| row.get(0),
        )?
    } else {
        conn.query_row(
            "SELECT COUNT(*) FROM gr_proj WHERE codkon = ? AND codproj = ?",
            params![codkon, codproj],
            |row| row.get(0),
        )?
    };
    Ok(count == 0)
}

pub fn insert_project(conn: &Connection, p: &Project) -> Result<i64> {
    conn.execute(
        "INSERT INTO gr_proj (
            codkon, codproj, codvuz, vuz_short_name, grnti_code,
            plan_fin, fact_fin, fin_q1, fin_q2, fin_q3, fin_q4,
            leader_fio, leader_post, leader_rank, leader_degree, proj_name
        ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14, ?15, ?16)",
        params![
            p.codkon,
            p.codproj,
            p.codvuz,
            p.vuz_short_name,
            p.grnti_code,
            p.plan_fin,
            p.fact_fin,
            p.fin_q1,
            p.fin_q2,
            p.fin_q3,
            p.fin_q4,
            p.leader_fio,
            p.leader_post,
            p.leader_rank,
            p.leader_degree,
            p.proj_name,
        ],
    )?;
    let new_id = conn.last_insert_rowid();
    crate::database::sync_contest_aggregates(conn, Some(p.codkon))?;
    Ok(new_id)
}

pub fn update_project(conn: &Connection, p: &Project) -> Result<()> {
    // Получаем старый codkon для синхронизации, если конкурс изменился
    let old_codkon: Option<i64> = conn
        .query_row("SELECT codkon FROM gr_proj WHERE id = ?", [p.id], |r| r.get(0))
        .ok();

    conn.execute(
        "UPDATE gr_proj SET
            codkon = ?1, codproj = ?2, codvuz = ?3, vuz_short_name = ?4, grnti_code = ?5,
            plan_fin = ?6, fact_fin = ?7, fin_q1 = ?8, fin_q2 = ?9, fin_q3 = ?10, fin_q4 = ?11,
            leader_fio = ?12, leader_post = ?13, leader_rank = ?14, leader_degree = ?15, proj_name = ?16
        WHERE id = ?17",
        params![
            p.codkon,
            p.codproj,
            p.codvuz,
            p.vuz_short_name,
            p.grnti_code,
            p.plan_fin,
            p.fact_fin,
            p.fin_q1,
            p.fin_q2,
            p.fin_q3,
            p.fin_q4,
            p.leader_fio,
            p.leader_post,
            p.leader_rank,
            p.leader_degree,
            p.proj_name,
            p.id,
        ],
    )?;

    crate::database::sync_contest_aggregates(conn, Some(p.codkon))?;
    if let Some(old_k) = old_codkon {
        if old_k != p.codkon {
            crate::database::sync_contest_aggregates(conn, Some(old_k))?;
        }
    }
    Ok(())
}

pub fn delete_project(conn: &Connection, id: i64) -> Result<()> {
    let codkon: Option<i64> = conn
        .query_row("SELECT codkon FROM gr_proj WHERE id = ?", [id], |r| r.get(0))
        .ok();

    conn.execute("DELETE FROM gr_proj WHERE id = ?", [id])?;

    if let Some(k) = codkon {
        crate::database::sync_contest_aggregates(conn, Some(k))?;
    }
    Ok(())
}

pub fn get_projects(conn: &Connection, filter_where: Option<&str>, sort_key: bool) -> Result<Vec<Project>> {
    let mut sql = String::from(
        "SELECT id, codkon, codproj, codvuz, vuz_short_name, grnti_code,
                plan_fin, fact_fin, fin_q1, fin_q2, fin_q3, fin_q4,
                leader_fio, leader_post, leader_rank, leader_degree, proj_name
         FROM gr_proj",
    );
    if let Some(fw) = filter_where {
        if !fw.trim().is_empty() {
            sql.push_str(&format!(" WHERE {}", fw));
        }
    }
    if sort_key {
        sql.push_str(" ORDER BY codkon ASC, codproj ASC");
    } else {
        sql.push_str(" ORDER BY id ASC");
    }

    let mut stmt = conn.prepare(&sql)?;
    let rows = stmt.query_map([], Project::from_row)?;
    let mut list = Vec::new();
    for r in rows {
        list.push(r?);
    }
    Ok(list)
}

pub fn get_contests(conn: &Connection) -> Result<Vec<Contest>> {
    let mut stmt = conn.prepare(
        "SELECT codkon, konk_name, plan_fin, fact_fin, fin_q1, fin_q2, fin_q3, fin_q4, projects_count
         FROM gr_konk ORDER BY codkon ASC",
    )?;
    let rows = stmt.query_map([], Contest::from_row)?;
    let mut list = Vec::new();
    for r in rows {
        list.push(r?);
    }
    Ok(list)
}

pub fn get_universities(conn: &Connection) -> Result<Vec<University>> {
    let mut stmt = conn.prepare(
        "SELECT codvuz, vuz_short_name, vuz_name, vuz_full_name, status, city, region, obl_name, obl_code, profile, department
         FROM vuz ORDER BY codvuz ASC",
    )?;
    let rows = stmt.query_map([], University::from_row)?;
    let mut list = Vec::new();
    for r in rows {
        list.push(r?);
    }
    Ok(list)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_validate_grnti() {
        assert!(validate_grnti("55.03.35"));
        assert!(validate_grnti("20.15.01"));
        assert!(validate_grnti("55.03.35; 20.15.01"));
        assert!(!validate_grnti("55.03"));
        assert!(!validate_grnti("55.3.35"));
        assert!(!validate_grnti("abc.de.fg"));
        assert!(!validate_grnti(""));
    }
}
