use rusqlite::{Connection, Result};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ReportData {
    pub title: String,
    pub headers: Vec<String>,
    pub rows: Vec<Vec<String>>,
    pub totals: Vec<String>,
    pub numeric_cols: Vec<usize>,
    pub money_cols: Vec<usize>,
}

pub fn build_contest_report(conn: &Connection, filter_where: &str) -> Result<ReportData> {
    let where_clause = if filter_where.trim().is_empty() {
        String::new()
    } else {
        format!("WHERE {}", filter_where)
    };

    let query = if filter_where.trim().is_empty() {
        "SELECT 
            k.codkon,
            k.konk_name,
            COUNT(p.id) AS nir_count,
            COALESCE(SUM(p.plan_fin), 0) AS total_plan,
            COUNT(DISTINCT p.codvuz) AS vuz_count
        FROM gr_konk k
        LEFT JOIN gr_proj p ON k.codkon = p.codkon
        GROUP BY k.codkon, k.konk_name
        ORDER BY k.codkon".to_string()
    } else {
        format!(
            "WITH filtered_proj AS (
                SELECT * FROM gr_proj WHERE {}
            )
            SELECT 
                k.codkon,
                k.konk_name,
                COUNT(p.id) AS nir_count,
                COALESCE(SUM(p.plan_fin), 0) AS total_plan,
                COUNT(DISTINCT p.codvuz) AS vuz_count
            FROM gr_konk k
            JOIN filtered_proj p ON k.codkon = p.codkon
            GROUP BY k.codkon, k.konk_name
            ORDER BY k.codkon",
            filter_where
        )
    };

    let mut stmt = conn.prepare(&query)?;
    let raw_rows = stmt.query_map([], |r| {
        Ok((
            r.get::<_, i64>(0)?,
            r.get::<_, String>(1)?,
            r.get::<_, i64>(2)?,
            r.get::<_, i64>(3)?,
            r.get::<_, i64>(4)?,
        ))
    })?;

    let headers = vec![
        "№ п/п".to_string(),
        "Код конкурса".to_string(),
        "Наименование конкурса".to_string(),
        "Количество НИР".to_string(),
        "План финансирования".to_string(),
        "Количество вузов".to_string(),
    ];

    let mut rows = Vec::new();
    let mut total_nir: i64 = 0;
    let mut total_plan: i64 = 0;

    for (idx, r) in raw_rows.enumerate() {
        let (codkon, name, n_cnt, p_sum, v_cnt) = r?;
        total_nir += n_cnt;
        total_plan += p_sum;
        rows.push(vec![
            (idx + 1).to_string(),
            codkon.to_string(),
            name,
            n_cnt.to_string(),
            crate::database::format_money(p_sum),
            v_cnt.to_string(),
        ]);
    }

    let tot_query = format!("SELECT COUNT(DISTINCT codvuz) FROM gr_proj {}", where_clause);
    let total_distinct_vuz: i64 = conn.query_row(&tot_query, [], |r| r.get(0)).unwrap_or(0);

    let totals = vec![
        "ИТОГО".to_string(),
        "".to_string(),
        "".to_string(),
        total_nir.to_string(),
        crate::database::format_money(total_plan),
        total_distinct_vuz.to_string(),
    ];

    Ok(ReportData {
        title: "Распределение проектов НИР по конкурсам грантов".to_string(),
        headers,
        rows,
        totals,
        numeric_cols: vec![3, 4, 5],
        money_cols: vec![4],
    })
}

pub fn build_vuz_report(conn: &Connection, filter_where: &str) -> Result<ReportData> {
    let where_clause = if filter_where.trim().is_empty() {
        String::new()
    } else {
        format!("WHERE {}", filter_where)
    };

    let query = format!(
        "WITH filtered_proj AS (
            SELECT * FROM gr_proj {}
        )
        SELECT 
            v.codvuz,
            COALESCE(v.vuz_short_name, v.vuz_name) AS vuz_name,
            COALESCE(v.city, '') AS city,
            COALESCE(v.obl_name, '') AS obl_name,
            COUNT(p.id) AS nir_count,
            COALESCE(SUM(p.plan_fin), 0) AS total_plan,
            COUNT(DISTINCT p.codkon) AS contest_count
        FROM filtered_proj p
        JOIN vuz v ON p.codvuz = v.codvuz
        GROUP BY v.codvuz, v.vuz_short_name, v.city, v.obl_name
        ORDER BY nir_count DESC, total_plan DESC, v.codvuz ASC",
        where_clause
    );

    let mut stmt = conn.prepare(&query)?;
    let raw_rows = stmt.query_map([], |r| {
        Ok((
            r.get::<_, i64>(0)?,
            r.get::<_, String>(1)?,
            r.get::<_, String>(2)?,
            r.get::<_, String>(3)?,
            r.get::<_, i64>(4)?,
            r.get::<_, i64>(5)?,
            r.get::<_, i64>(6)?,
        ))
    })?;

    let headers = vec![
        "№ п/п".to_string(),
        "Код вуза".to_string(),
        "Вуз".to_string(),
        "Город".to_string(),
        "Субъект РФ".to_string(),
        "Количество НИР".to_string(),
        "План финансирования".to_string(),
        "Количество конкурсов".to_string(),
    ];

    let mut rows = Vec::new();
    let mut total_nir: i64 = 0;
    let mut total_plan: i64 = 0;

    for (idx, r) in raw_rows.enumerate() {
        let (codvuz, name, city, obl, n_cnt, p_sum, c_cnt) = r?;
        total_nir += n_cnt;
        total_plan += p_sum;
        rows.push(vec![
            (idx + 1).to_string(),
            codvuz.to_string(),
            name,
            city,
            obl,
            n_cnt.to_string(),
            crate::database::format_money(p_sum),
            c_cnt.to_string(),
        ]);
    }

    let tot_query = format!("SELECT COUNT(DISTINCT codkon) FROM gr_proj {}", where_clause);
    let total_distinct_konk: i64 = conn.query_row(&tot_query, [], |r| r.get(0)).unwrap_or(0);

    let totals = vec![
        "ИТОГО".to_string(),
        "".to_string(),
        "".to_string(),
        "".to_string(),
        "".to_string(),
        total_nir.to_string(),
        crate::database::format_money(total_plan),
        total_distinct_konk.to_string(),
    ];

    Ok(ReportData {
        title: "Распределение проектов НИР по вузам-исполнителям".to_string(),
        headers,
        rows,
        totals,
        numeric_cols: vec![5, 6, 7],
        money_cols: vec![6],
    })
}

pub fn build_region_report(conn: &Connection, filter_where: &str) -> Result<ReportData> {
    let where_clause = if filter_where.trim().is_empty() {
        String::new()
    } else {
        format!("WHERE {}", filter_where)
    };

    let query = format!(
        "WITH filtered_proj AS (
            SELECT * FROM gr_proj {}
        )
        SELECT 
            COALESCE(v.obl_code, '') AS obl_code,
            COALESCE(v.obl_name, 'Не указан') AS obl_name,
            COALESCE(v.region, '') AS region,
            COUNT(p.id) AS nir_count,
            COALESCE(SUM(p.plan_fin), 0) AS total_plan,
            COUNT(DISTINCT p.codvuz) AS vuz_count
        FROM filtered_proj p
        JOIN vuz v ON p.codvuz = v.codvuz
        GROUP BY v.obl_code, v.obl_name, v.region
        ORDER BY nir_count DESC, total_plan DESC, v.obl_name ASC",
        where_clause
    );

    let mut stmt = conn.prepare(&query)?;
    let raw_rows = stmt.query_map([], |r| {
        Ok((
            r.get::<_, String>(0)?,
            r.get::<_, String>(1)?,
            r.get::<_, String>(2)?,
            r.get::<_, i64>(3)?,
            r.get::<_, i64>(4)?,
            r.get::<_, i64>(5)?,
        ))
    })?;

    let headers = vec![
        "№ п/п".to_string(),
        "Код региона".to_string(),
        "Субъект РФ".to_string(),
        "Федеральный округ".to_string(),
        "Количество НИР".to_string(),
        "План финансирования".to_string(),
        "Количество вузов".to_string(),
    ];

    let mut rows = Vec::new();
    let mut total_nir: i64 = 0;
    let mut total_plan: i64 = 0;

    for (idx, r) in raw_rows.enumerate() {
        let (obl_code, obl_name, reg, n_cnt, p_sum, v_cnt) = r?;
        total_nir += n_cnt;
        total_plan += p_sum;
        rows.push(vec![
            (idx + 1).to_string(),
            obl_code,
            obl_name,
            reg,
            n_cnt.to_string(),
            crate::database::format_money(p_sum),
            v_cnt.to_string(),
        ]);
    }

    let tot_query = format!("SELECT COUNT(DISTINCT codvuz) FROM gr_proj {}", where_clause);
    let total_distinct_vuz: i64 = conn.query_row(&tot_query, [], |r| r.get(0)).unwrap_or(0);

    let totals = vec![
        "ИТОГО".to_string(),
        "".to_string(),
        "".to_string(),
        "".to_string(),
        total_nir.to_string(),
        crate::database::format_money(total_plan),
        total_distinct_vuz.to_string(),
    ];

    Ok(ReportData {
        title: "Распределение проектов НИР по субъектам РФ".to_string(),
        headers,
        rows,
        totals,
        numeric_cols: vec![4, 5, 6],
        money_cols: vec![5],
    })
}
