-- Météo journalière nettoyée
--  * conversion des températures reçues en °F (valeur moyenne > 45 °C impossible en France)
--  * température moyenne manquante -> moyenne de la min et de la max
DROP TABLE IF EXISTS stg_weather;
CREATE TABLE stg_weather AS
WITH typed AS (
    SELECT
        region_code,
        date,
        CAST(temp_mean_c AS REAL) AS temp_mean_raw,
        CAST(temp_min_c  AS REAL) AS temp_min_c,
        CAST(temp_max_c  AS REAL) AS temp_max_c,
        CAST(cloud_cover_pct AS INTEGER) AS cloud_cover_pct
    FROM raw_weather
)
SELECT
    region_code,
    date,
    ROUND(
        CASE
            WHEN temp_mean_raw IS NULL THEN (temp_min_c + temp_max_c) / 2.0
            WHEN temp_mean_raw > 45    THEN (temp_mean_raw - 32) * 5.0 / 9.0
            ELSE temp_mean_raw
        END, 1)                                         AS temp_mean_c,
    temp_min_c,
    temp_max_c,
    cloud_cover_pct,
    CASE
        WHEN temp_mean_raw IS NULL THEN 'imputee_min_max'
        WHEN temp_mean_raw > 45    THEN 'convertie_fahrenheit'
        ELSE 'brute'
    END                                                  AS temp_quality_flag
FROM typed;
