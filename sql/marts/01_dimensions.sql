-- Dimensions : régions et calendrier horaire complet

DROP TABLE IF EXISTS dim_region;
CREATE TABLE dim_region AS
SELECT region_code, region_name FROM stg_regions ORDER BY region_code;

-- Calendrier horaire généré (CTE récursive) : sert de grille pour détecter et combler les trous
DROP TABLE IF EXISTS dim_hour;
CREATE TABLE dim_hour AS
WITH RECURSIVE hours(ts) AS (
    SELECT (SELECT MIN(datetime_utc) FROM stg_consumption)
    UNION ALL
    SELECT strftime('%Y-%m-%d %H:%M:%S', ts, '+1 hour') FROM hours
    WHERE ts < (SELECT MAX(datetime_utc) FROM stg_consumption)
)
SELECT
    ts                                                   AS datetime_utc,
    substr(ts, 1, 10)                                    AS date,
    CAST(strftime('%Y', ts) AS INTEGER)                  AS year,
    CAST(strftime('%m', ts) AS INTEGER)                  AS month,
    CAST(strftime('%H', ts) AS INTEGER)                  AS hour,
    -- 1 = lundi ... 7 = dimanche
    ((CAST(strftime('%w', ts) AS INTEGER) + 6) % 7) + 1  AS weekday,
    CASE WHEN strftime('%w', ts) IN ('0', '6') THEN 1 ELSE 0 END AS is_weekend,
    CASE WHEN substr(ts, 1, 10) IN (SELECT date FROM ref_holidays) THEN 1 ELSE 0 END AS is_holiday,
    CASE
        WHEN CAST(strftime('%m', ts) AS INTEGER) IN (12, 1, 2) THEN 'Hiver'
        WHEN CAST(strftime('%m', ts) AS INTEGER) IN (3, 4, 5)  THEN 'Printemps'
        WHEN CAST(strftime('%m', ts) AS INTEGER) IN (6, 7, 8)  THEN 'Été'
        ELSE 'Automne'
    END                                                  AS season
FROM hours;
CREATE UNIQUE INDEX idx_dim_hour ON dim_hour(datetime_utc);
