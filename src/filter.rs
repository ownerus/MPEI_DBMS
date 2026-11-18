use rusqlite::{Connection, Result};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct FilterCriteria {
    pub codkon: Option<i64>,
    pub region: Option<String>,
    pub obl_name: Option<String>,
    pub city: Option<String>,
    pub codvuz: Option<i64>,
}

impl FilterCriteria {
    pub fn is_empty(&self) -> bool {
        self.codkon.is_none()
            && self.region.is_none()
            && self.obl_name.is_none()
            && self.city.is_none()
            && self.codvuz.is_none()
    }

    pub fn clear(&mut self) {
        *self = Self::default();
    }

    pub fn build_where_clause(&self) -> String {
        let mut clauses = Vec::new();

        if let Some(k) = self.codkon {
            clauses.push(format!("codkon = {}", k));
        }

        if let Some(v) = self.codvuz {
            clauses.push(format!("codvuz = {}", v));
        } else if let Some(ref city) = self.city {
            let safe_city = city.replace('\'', "''");
            if let Some(ref obl) = self.obl_name {
                let safe_obl = obl.replace('\'', "''");
                clauses.push(format!(
                    "codvuz IN (SELECT codvuz FROM vuz WHERE city = '{}' AND obl_name = '{}')",
                    safe_city, safe_obl
                ));
            } else {
                clauses.push(format!(
                    "codvuz IN (SELECT codvuz FROM vuz WHERE city = '{}')",
                    safe_city
                ));
            }
        } else if let Some(ref obl) = self.obl_name {
            let safe_obl = obl.replace('\'', "''");
            clauses.push(format!(
                "codvuz IN (SELECT codvuz FROM vuz WHERE obl_name = '{}')",
                safe_obl
            ));
        } else if let Some(ref reg) = self.region {
            let safe_reg = reg.replace('\'', "''");
            clauses.push(format!(
                "codvuz IN (SELECT codvuz FROM vuz WHERE region = '{}')",
                safe_reg
            ));
        }

        clauses.join(" AND ")
    }

    pub fn build_summary(&self, conn: &Connection) -> String {
        let mut labels = Vec::new();

        if let Some(k) = self.codkon {
            let name: String = conn
                .query_row("SELECT konk_name FROM gr_konk WHERE codkon = ?", [k], |r| r.get(0))
                .unwrap_or_default();
            if !name.is_empty() {
                labels.push(format!("Конкурс {}: {}", k, name));
            } else {
                labels.push(format!("Конкурс {}", k));
            }
        }

        if let Some(v) = self.codvuz {
            let name: String = conn
                .query_row("SELECT vuz_short_name FROM vuz WHERE codvuz = ?", [v], |r| r.get(0))
                .unwrap_or_default();
            labels.push(format!("Вуз: {}", name));
        } else if let Some(ref city) = self.city {
            if let Some(ref obl) = self.obl_name {
                labels.push(format!("Город: {} ({})", city, obl));
            } else {
                labels.push(format!("Город: {}", city));
            }
        } else if let Some(ref obl) = self.obl_name {
            labels.push(format!("Субъект: {}", obl));
        } else if let Some(ref reg) = self.region {
            labels.push(format!("Округ: {}", reg));
        }

        labels.join(", ")
    }
}

pub fn get_distinct_regions(conn: &Connection) -> Result<Vec<String>> {
    let mut stmt = conn.prepare("SELECT DISTINCT region FROM vuz WHERE region IS NOT NULL AND region != '' ORDER BY region ASC")?;
    let rows = stmt.query_map([], |r| r.get(0))?;
    let mut list = Vec::new();
    for r in rows {
        list.push(r?);
    }
    Ok(list)
}

pub fn get_distinct_obls(conn: &Connection, region: Option<&str>) -> Result<Vec<String>> {
    let sql = if let Some(r) = region {
        format!("SELECT DISTINCT obl_name FROM vuz WHERE region = '{}' AND obl_name IS NOT NULL AND obl_name != '' ORDER BY obl_name ASC", r.replace('\'', "''"))
    } else {
        "SELECT DISTINCT obl_name FROM vuz WHERE obl_name IS NOT NULL AND obl_name != '' ORDER BY obl_name ASC".to_string()
    };
    let mut stmt = conn.prepare(&sql)?;
    let rows = stmt.query_map([], |r| r.get(0))?;
    let mut list = Vec::new();
    for r in rows {
        list.push(r?);
    }
    Ok(list)
}

pub fn get_distinct_cities(conn: &Connection, obl: Option<&str>) -> Result<Vec<String>> {
    let sql = if let Some(o) = obl {
        format!("SELECT DISTINCT city FROM vuz WHERE obl_name = '{}' AND city IS NOT NULL AND city != '' ORDER BY city ASC", o.replace('\'', "''"))
    } else {
        "SELECT DISTINCT city FROM vuz WHERE city IS NOT NULL AND city != '' ORDER BY city ASC".to_string()
    };
    let mut stmt = conn.prepare(&sql)?;
    let rows = stmt.query_map([], |r| r.get(0))?;
    let mut list = Vec::new();
    for r in rows {
        list.push(r?);
    }
    Ok(list)
}

pub fn get_vuz_list_filtered(conn: &Connection, city: Option<&str>, obl: Option<&str>) -> Result<Vec<(i64, String)>> {
    let mut clauses = Vec::new();
    if let Some(c) = city {
        clauses.push(format!("city = '{}'", c.replace('\'', "''")));
    }
    if let Some(o) = obl {
        clauses.push(format!("obl_name = '{}'", o.replace('\'', "''")));
    }
    let sql = if clauses.is_empty() {
        "SELECT codvuz, vuz_short_name FROM vuz ORDER BY vuz_short_name ASC".to_string()
    } else {
        format!("SELECT codvuz, vuz_short_name FROM vuz WHERE {} ORDER BY vuz_short_name ASC", clauses.join(" AND "))
    };
    let mut stmt = conn.prepare(&sql)?;
    let rows = stmt.query_map([], |r| Ok((r.get(0)?, r.get(1)?)))?;
    let mut list = Vec::new();
    for r in rows {
        list.push(r?);
    }
    Ok(list)
}
