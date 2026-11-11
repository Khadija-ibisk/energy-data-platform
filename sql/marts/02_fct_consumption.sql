-- Faits de consommation : grille complète région x heure, trous comblés et tracés

DROP TABLE IF EXISTS fct_consumption_hourly;
CREATE TABLE fct_consumption_hourly AS
WITH grid AS (
    SELECT r.region_code, h.datetime_utc, h.date, h.hour, h.weekday, h.is_weekend, h.is_holiday
    FROM dim_region r CROSS JOIN dim_hour h
),
joined AS (
    SELECT g.*, c.consumption_mw AS measured_mw
    FROM grid g
    LEFT JOIN stg_consumption c
      ON c.region_code = g.region_code AND c.datetime_utc = g.datetime_utc
),
filled AS (
    SELECT
        *,
        -- trou isolé : moyenne de l'heure précédente et suivante ; sinon même heure la veille
        COALESCE(
            measured_mw,
            (LAG(measured_mw) OVER w + LEAD(measured_mw) OVER w) / 2.0,
            LAG(measured_mw, 24) OVER w
        ) AS consumption_mw
    FROM joined
    WINDOW w AS (PARTITION BY region_code ORDER BY datetime_utc)
)
SELECT
    f.region_code,
    f.datetime_utc,
    f.date,
    f.hour,
    f.weekday,
    f.is_weekend,
    f.is_holiday,
    ROUND(f.consumption_mw, 1)                           AS consumption_mw,
    CASE WHEN f.measured_mw IS NULL THEN 1 ELSE 0 END    AS is_imputed,
    w.temp_mean_c
FROM filled f
LEFT JOIN stg_weather w ON w.region_code = f.region_code AND w.date = f.date;
CREATE INDEX idx_fct_hourly ON fct_consumption_hourly(region_code, datetime_utc);

-- Agrégat journalier par région (MWh, pointe, degrés-jours de chauffage)
DROP TABLE IF EXISTS fct_consumption_daily;
CREATE TABLE fct_consumption_daily AS
SELECT
    region_code,
    date,
    ROUND(SUM(consumption_mw), 0)                       AS energy_mwh,
    ROUND(MAX(consumption_mw), 0)                       AS peak_mw,
    MAX(temp_mean_c)                                     AS temp_mean_c,
    ROUND(MAX(0, 15 - MAX(temp_mean_c)), 1)              AS heating_degree_days,
    MAX(is_weekend)                                      AS is_weekend,
    MAX(is_holiday)                                      AS is_holiday,
    SUM(is_imputed)                                      AS imputed_hours
FROM fct_consumption_hourly
GROUP BY region_code, date;
CREATE INDEX idx_fct_daily ON fct_consumption_daily(region_code, date);
