use rusqlite::{Connection, Result};
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FinanceSummary {
    pub vuz_count: i64,
    pub proj_count: i64,
    pub total_plan: i64,
    pub total_fact: i64,
    pub q1: i64,
    pub q2: i64,
    pub q3: i64,
    pub q4: i64,
    pub fact_pct: f64,
}

pub fn get_finance_summary(conn: &Connection) -> Result<FinanceSummary> {
    let row = conn.query_row(
        "SELECT 
            COUNT(DISTINCT codvuz),
            COUNT(*),
            COALESCE(SUM(plan_fin), 0),
            COALESCE(SUM(fact_fin), 0),
            COALESCE(SUM(fin_q1), 0),
            COALESCE(SUM(fin_q2), 0),
            COALESCE(SUM(fin_q3), 0),
            COALESCE(SUM(fin_q4), 0)
        FROM gr_proj",
        [],
        |r| {
            Ok((
                r.get::<_, i64>(0)?,
                r.get::<_, i64>(1)?,
                r.get::<_, i64>(2)?,
                r.get::<_, i64>(3)?,
                r.get::<_, i64>(4)?,
                r.get::<_, i64>(5)?,
                r.get::<_, i64>(6)?,
                r.get::<_, i64>(7)?,
            ))
        },
    )?;

    let (vuz_cnt, proj_cnt, plan, fact, q1, q2, q3, q4) = row;
    let pct = if plan > 0 {
        (fact as f64 / plan as f64) * 100.0
    } else {
        0.0
    };

    Ok(FinanceSummary {
        vuz_count: vuz_cnt,
        proj_count: proj_cnt,
        total_plan: plan,
        total_fact: fact,
        q1,
        q2,
        q3,
        q4,
        fact_pct: pct,
    })
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct VuzDistributionRow {
    pub codvuz: i64,
    pub vuz_short_name: String,
    pub city: String,
    pub proj_count: i64,
    pub plan_sum: i64,
    pub tranche_sum: i64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TrancheDistribution {
    pub percent: f64,
    pub total_plan: i64,
    pub total_distributed: i64,
    pub total_proj_count: usize,
    pub project_tranches: Vec<(i64, i64)>, // (proj_id, tranche_amount)
    pub vuz_rows: Vec<VuzDistributionRow>,
}

/// Округление к ближайшему четному (Banker's rounding), как в Python 3 round()
pub fn round_half_to_even(x: f64) -> i64 {
    let floor = x.floor();
    let diff = x - floor;
    const EPSILON: f64 = 1e-9;
    if (diff - 0.5).abs() < EPSILON {
        let int_val = floor as i64;
        if int_val % 2 == 0 {
            int_val
        } else {
            int_val + 1
        }
    } else if diff > 0.5 {
        (floor + 1.0) as i64
    } else {
        floor as i64
    }
}

pub fn calculate_tranche_distribution(percent: f64, conn: &Connection) -> Result<TrancheDistribution> {
    let mut stmt = conn.prepare(
        "SELECT 
            p.id,
            p.codkon,
            p.codproj,
            p.codvuz,
            p.plan_fin,
            COALESCE(v.vuz_short_name, 'Вуз #' || p.codvuz),
            COALESCE(v.city, '')
        FROM gr_proj p
        LEFT JOIN vuz v ON p.codvuz = v.codvuz
        ORDER BY p.codvuz, p.codkon, p.codproj",
    )?;

    let rows = stmt.query_map([], |r| {
        Ok((
            r.get::<_, i64>(0)?,
            r.get::<_, i64>(1)?,
            r.get::<_, i64>(2)?,
            r.get::<_, i64>(3)?,
            r.get::<_, i64>(4)?,
            r.get::<_, String>(5)?,
            r.get::<_, String>(6)?,
        ))
    })?;

    let pct_fraction = percent / 100.0;
    let mut total_plan: i64 = 0;
    let mut project_tranches = Vec::new();
    let mut vuz_map: BTreeMap<i64, VuzDistributionRow> = BTreeMap::new();

    for r in rows {
        let (p_id, _codkon, _codproj, codvuz, plan_fin, vuz_short, city) = r?;
        total_plan += plan_fin;

        // Округление до целого рубля по каждому проекту (банковское округление, как в Python)
        let p_tranche = round_half_to_even(plan_fin as f64 * pct_fraction);
        project_tranches.push((p_id, p_tranche));

        let entry = vuz_map.entry(codvuz).or_insert_with(|| VuzDistributionRow {
            codvuz,
            vuz_short_name: vuz_short,
            city,
            proj_count: 0,
            plan_sum: 0,
            tranche_sum: 0,
        });
        entry.proj_count += 1;
        entry.plan_sum += plan_fin;
        entry.tranche_sum += p_tranche;
    }

    let total_distributed: i64 = project_tranches.iter().map(|(_, t)| *t).sum();
    let total_proj_count = project_tranches.len();
    let vuz_rows: Vec<VuzDistributionRow> = vuz_map.into_values().collect();

    Ok(TrancheDistribution {
        percent,
        total_plan,
        total_distributed,
        total_proj_count,
        project_tranches,
        vuz_rows,
    })
}

pub fn execute_tranche_in_db(
    quarter: u8,
    project_tranches: &[(i64, i64)],
    conn: &mut Connection,
) -> Result<()> {
    let col_q = format!("fin_q{}", quarter);
    let tx = conn.transaction()?;

    for (p_id, tranche_val) in project_tranches {
        let sql = format!(
            "UPDATE gr_proj SET {} = {} + ?1, fact_fin = fact_fin + ?2 WHERE id = ?3",
            col_q, col_q
        );
        tx.execute(&sql, rusqlite::params![tranche_val, tranche_val, p_id])?;
    }

    tx.commit()?;
    crate::database::sync_contest_aggregates(conn, None)?;
    Ok(())
}

pub fn reset_quarter_funding(quarter: u8, conn: &mut Connection) -> Result<()> {
    let col_q = format!("fin_q{}", quarter);
    let tx = conn.transaction()?;

    let sql = format!(
        "UPDATE gr_proj SET fact_fin = MAX(0, fact_fin - {}), {} = 0",
        col_q, col_q
    );
    tx.execute(&sql, [])?;

    tx.commit()?;
    crate::database::sync_contest_aggregates(conn, None)?;
    Ok(())
}

pub fn build_finance_document_report(
    dist: &TrancheDistribution,
    quarter: u8,
) -> crate::reports::ReportData {
    let headers = vec![
        "№ п/п".to_string(),
        "Код вуза".to_string(),
        "Вуз-исполнитель".to_string(),
        "Город".to_string(),
        "Количество НИР".to_string(),
        "Сумма выплат (руб.)".to_string(),
    ];

    let mut rows = Vec::new();
    for (idx, v) in dist.vuz_rows.iter().enumerate() {
        rows.push(vec![
            (idx + 1).to_string(),
            v.codvuz.to_string(),
            v.vuz_short_name.clone(),
            v.city.clone(),
            v.proj_count.to_string(),
            crate::database::format_money(v.tranche_sum),
        ]);
    }

    let totals = vec![
        "ИТОГО".to_string(),
        "".to_string(),
        "".to_string(),
        "".to_string(),
        dist.total_proj_count.to_string(),
        crate::database::format_money(dist.total_distributed),
    ];

    crate::reports::ReportData {
        title: format!(
            "Распоряжение о финансировании проектов НИР по грантам ({}-й квартал, {:.2}% от плана)",
            quarter, dist.percent
        ),
        headers,
        rows,
        totals,
        numeric_cols: vec![4, 5],
        money_cols: vec![5],
    }
}
