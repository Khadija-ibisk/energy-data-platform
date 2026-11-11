-- Marts analytiques prêts pour la BI, l'API et le Machine Learning

-- Série nationale horaire (entrée du modèle de prévision)
DROP TABLE IF EXISTS mart_national_hourly;
CREATE TABLE mart_national_hourly AS
SELECT
    f.datetime_utc,
    h.date, h.year, h.month, h.hour, h.weekday, h.is_weekend, h.is_holiday, h.season,
    ROUND(SUM(f.consumption_mw), 0)                                         AS consumption_mw,
    -- température nationale pondérée par le poids de consommation de chaque région
    ROUND(SUM(f.temp_mean_c * f.consumption_mw) / SUM(f.consumption_mw), 2) AS temp_weighted_c
FROM fct_consumption_hourly f
JOIN dim_hour h ON h.datetime_utc = f.datetime_utc
GROUP BY f.datetime_utc;

-- KPI annuels par région, avec la thermosensibilité estimée par régression linéaire en SQL :
-- pente = cov(T, E) / var(T) sur les jours de chauffage (T < 15 °C)
DROP TABLE IF EXISTS mart_region_kpis;
CREATE TABLE mart_region_kpis AS
WITH yearly AS (
    SELECT
        d.region_code,
        CAST(substr(d.date, 1, 4) AS INTEGER)  AS year,
        SUM(d.energy_mwh) / 1e6                AS energy_twh,
        MAX(d.peak_mw)                         AS peak_mw,
        AVG(d.temp_mean_c)                     AS avg_temp_c
    FROM fct_consumption_daily d
    GROUP BY d.region_code, year
),
heating_days AS (
    SELECT region_code, temp_mean_c AS t, energy_mwh / 24.0 AS mw
    FROM fct_consumption_daily
    WHERE temp_mean_c < 15 AND is_weekend = 0 AND is_holiday = 0
),
thermo AS (
    SELECT
        region_code,
        (AVG(t * mw) - AVG(t) * AVG(mw)) / (AVG(t * t) - AVG(t) * AVG(t)) AS slope_mw_per_c
    FROM heating_days
    GROUP BY region_code
)
SELECT
    r.region_name,
    y.region_code,
    y.year,
    ROUND(y.energy_twh, 2)                                  AS energy_twh,
    ROUND(y.peak_mw, 0)                                     AS peak_mw,
    ROUND(y.avg_temp_c, 1)                                  AS avg_temp_c,
    ROUND(-t.slope_mw_per_c, 0)                             AS thermosensitivity_mw_per_c,
    ROUND(100.0 * (y.energy_twh / LAG(y.energy_twh) OVER (PARTITION BY y.region_code ORDER BY y.year) - 1), 2)
                                                            AS evolution_pct
FROM yearly y
JOIN dim_region r ON r.region_code = y.region_code
JOIN thermo t     ON t.region_code = y.region_code;

-- Profil moyen par heure et type de jour (pour les heatmaps et le pilotage de la pointe)
DROP TABLE IF EXISTS mart_load_profile;
CREATE TABLE mart_load_profile AS
SELECT
    season,
    weekday,
    hour,
    ROUND(AVG(consumption_mw) / 1000.0, 2) AS avg_consumption_gw
FROM mart_national_hourly
GROUP BY season, weekday, hour;

-- Top 10 des heures de pointe nationales (risque de tension sur le réseau)
DROP TABLE IF EXISTS mart_peak_hours;
CREATE TABLE mart_peak_hours AS
SELECT
    RANK() OVER (ORDER BY consumption_mw DESC) AS rang,
    datetime_utc,
    ROUND(consumption_mw / 1000.0, 1)          AS consumption_gw,
    temp_weighted_c
FROM mart_national_hourly
ORDER BY consumption_mw DESC
LIMIT 10;
