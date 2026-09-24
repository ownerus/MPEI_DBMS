CREATE TRIGGER IF NOT EXISTS gr_proj_insert_totals AFTER INSERT ON gr_proj
BEGIN
    UPDATE gr_konk SET
        projects_count = projects_count + 1,
        plan_fin = plan_fin + NEW.plan_fin,
        fact_fin = fact_fin + NEW.fact_fin,
        fin_q1 = fin_q1 + NEW.fin_q1,
        fin_q2 = fin_q2 + NEW.fin_q2,
        fin_q3 = fin_q3 + NEW.fin_q3,
        fin_q4 = fin_q4 + NEW.fin_q4
    WHERE codkon = NEW.codkon;
END;

CREATE TRIGGER IF NOT EXISTS gr_proj_delete_totals AFTER DELETE ON gr_proj
BEGIN
    UPDATE gr_konk SET
        projects_count = projects_count - 1,
        plan_fin = plan_fin - OLD.plan_fin,
        fact_fin = fact_fin - OLD.fact_fin,
        fin_q1 = fin_q1 - OLD.fin_q1,
        fin_q2 = fin_q2 - OLD.fin_q2,
        fin_q3 = fin_q3 - OLD.fin_q3,
        fin_q4 = fin_q4 - OLD.fin_q4
    WHERE codkon = OLD.codkon;
END;

CREATE TRIGGER IF NOT EXISTS gr_proj_update_totals AFTER UPDATE ON gr_proj
BEGIN
    UPDATE gr_konk SET
        projects_count = projects_count - 1,
        plan_fin = plan_fin - OLD.plan_fin,
        fact_fin = fact_fin - OLD.fact_fin,
        fin_q1 = fin_q1 - OLD.fin_q1,
        fin_q2 = fin_q2 - OLD.fin_q2,
        fin_q3 = fin_q3 - OLD.fin_q3,
        fin_q4 = fin_q4 - OLD.fin_q4
    WHERE codkon = OLD.codkon;

    UPDATE gr_konk SET
        projects_count = projects_count + 1,
        plan_fin = plan_fin + NEW.plan_fin,
        fact_fin = fact_fin + NEW.fact_fin,
        fin_q1 = fin_q1 + NEW.fin_q1,
        fin_q2 = fin_q2 + NEW.fin_q2,
        fin_q3 = fin_q3 + NEW.fin_q3,
        fin_q4 = fin_q4 + NEW.fin_q4
    WHERE codkon = NEW.codkon;
END;
