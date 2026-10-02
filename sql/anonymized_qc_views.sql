-- =====================================================================
-- Analytical SQL views for the anonymized industrial quality-control data
-- Database: industrial_qc.db (SQLite; window functions need SQLite >= 3.25)
-- Source tables (created by run_pipeline.py from the packaged CSVs):
--   qc_batch_production, qc_density_samples
-- =====================================================================

DROP VIEW IF EXISTS view_executive_quality_summary;
DROP VIEW IF EXISTS view_sku_defect_performance;
DROP VIEW IF EXISTS view_pareto_failure_modes;
DROP VIEW IF EXISTS view_rolling_batch_quality;
DROP VIEW IF EXISTS view_monthly_quality;

-- 1. Executive summary per phase (COPQ uses an ASSUMED flat unit cost)
CREATE VIEW view_executive_quality_summary AS
SELECT
    phase,
    COUNT(batch_id) AS total_batches,
    SUM(total_pcs) AS total_manufactured_pcs,
    SUM(passed_pcs) AS total_passed_pcs,
    SUM(reject_pcs) AS total_scrapped_pcs,
    ROUND(SUM(reject_pcs) * 100.0 / SUM(total_pcs), 2) AS overall_volume_reject_pct,
    ROUND(AVG(reject_rate_pct), 2) AS mean_batch_reject_pct,
    ROUND(AVG(mean_density_kgm3), 1) AS avg_density_kgm3,
    SUM(reject_pcs) * 45000 AS total_assumed_copq_idr,
    ROUND((SUM(reject_pcs) * 45000.0) / SUM(total_pcs), 0) AS assumed_copq_per_unit_idr
FROM qc_batch_production
GROUP BY phase;

-- 2. Performance by SKU, split by phase so before/after is visible per SKU
CREATE VIEW view_sku_defect_performance AS
SELECT
    size AS sku_dimension,
    phase,
    COUNT(batch_id) AS batch_count,
    SUM(total_pcs) AS total_produced_pcs,
    SUM(reject_pcs) AS total_reject_pcs,
    ROUND(SUM(reject_pcs) * 100.0 / SUM(total_pcs), 2) AS volume_reject_rate_pct,
    ROUND(AVG(reject_rate_pct), 2) AS avg_batch_reject_pct,
    SUM(reject_pcs) * 45000 AS assumed_copq_idr,
    ROUND((SUM(reject_pcs) * 45000.0) / SUM(total_pcs), 0) AS assumed_copq_per_unit_idr
FROM qc_batch_production
GROUP BY size, phase
ORDER BY size, phase DESC;

-- 3. Pareto of rejects by defect category (one category per batch, from free-text notes)
CREATE VIEW view_pareto_failure_modes AS
WITH defects AS (
    SELECT
        phase,
        COALESCE(defect_category, 'No category recorded') AS failure_mode,
        SUM(reject_pcs) AS scrapped_units
    FROM qc_batch_production
    GROUP BY phase, defect_category
    HAVING SUM(reject_pcs) > 0
),
ranked AS (
    SELECT
        phase,
        failure_mode,
        scrapped_units,
        SUM(scrapped_units) OVER (
            PARTITION BY phase ORDER BY scrapped_units DESC
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS cumulative_units,
        SUM(scrapped_units) OVER (PARTITION BY phase) AS phase_total
    FROM defects
)
SELECT
    phase,
    failure_mode,
    scrapped_units,
    ROUND(scrapped_units * 100.0 / phase_total, 2) AS defect_pct_share,
    ROUND(cumulative_units * 100.0 / phase_total, 2) AS cumulative_share_pct
FROM ranked
ORDER BY phase DESC, scrapped_units DESC;

-- 4. Rolling 5-batch reject rate (volume-weighted, never crosses the phase boundary)
--    and FIXED-THRESHOLD operational flags. These are NOT Laney control limits;
--    the Laney p'-chart limits are computed in src/spc_laney_engine.py.
CREATE VIEW view_rolling_batch_quality AS
SELECT
    batch_id,
    date,
    phase,
    size AS sku_size,
    total_pcs,
    reject_pcs,
    ROUND(reject_rate_pct, 2) AS batch_reject_pct,
    ROUND(100.0 * SUM(reject_pcs) OVER w / SUM(total_pcs) OVER w, 2) AS rolling_5_batch_reject_pct,
    mean_density_kgm3,
    CASE
        WHEN reject_rate_pct > 30.0 THEN 'Severe (>30%)'
        WHEN reject_rate_pct > 15.0 THEN 'Elevated (>15%) - investigate'
        ELSE 'Below fixed thresholds'
    END AS fixed_threshold_flag
FROM qc_batch_production
WINDOW w AS (
    PARTITION BY phase
    ORDER BY date, rowid
    ROWS BETWEEN 4 PRECEDING AND CURRENT ROW)
ORDER BY date, rowid;

-- 5. Monthly view - exposes how unevenly batches are spread over calendar time
CREATE VIEW view_monthly_quality AS
SELECT
    strftime('%Y-%m', date) AS month,
    phase,
    COUNT(batch_id) AS batches,
    SUM(total_pcs) AS pcs,
    SUM(reject_pcs) AS rejects,
    ROUND(SUM(reject_pcs) * 100.0 / SUM(total_pcs), 2) AS reject_rate_pct
FROM qc_batch_production
GROUP BY month, phase
ORDER BY month;
