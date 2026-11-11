-- Consommation horaire nettoyée + quarantaine des lignes invalides
--  * dédoublonnage (double envoi de fichiers)
--  * normalisation de l'horodatage
--  * rejet en quarantaine : région manquante, valeur <= 0, pic > 3x la moyenne régionale

DROP TABLE IF EXISTS _tmp_consumption;
CREATE TABLE _tmp_consumption AS
WITH dedup AS (
    SELECT
        region_code,
        REPLACE(datetime, 'T', ' ')                         AS datetime_utc,
        CAST(consumption_mw AS REAL)                        AS consumption_mw,
        _batch_id,
        ROW_NUMBER() OVER (PARTITION BY region_code, datetime ORDER BY rowid) AS rn
    FROM raw_consumption
),
scored AS (
    SELECT
        *,
        AVG(CASE WHEN consumption_mw > 0 THEN consumption_mw END)
            OVER (PARTITION BY region_code)                 AS region_avg_mw
    FROM dedup
    WHERE rn = 1
)
SELECT
    region_code,
    datetime_utc,
    consumption_mw,
    _batch_id,
    CASE
        WHEN region_code IS NULL OR region_code NOT IN (SELECT region_code FROM stg_regions)
                                              THEN 'region_inconnue'
        WHEN consumption_mw IS NULL           THEN 'valeur_manquante'
        WHEN consumption_mw <= 0              THEN 'valeur_negative_ou_nulle'
        WHEN consumption_mw > 3 * region_avg_mw THEN 'pic_aberrant'
    END AS rejection_reason
FROM scored;

DROP TABLE IF EXISTS quarantine_consumption;
CREATE TABLE quarantine_consumption AS
SELECT * FROM _tmp_consumption WHERE rejection_reason IS NOT NULL;

DROP TABLE IF EXISTS stg_consumption;
CREATE TABLE stg_consumption AS
SELECT region_code, datetime_utc, consumption_mw, _batch_id
FROM _tmp_consumption
WHERE rejection_reason IS NULL;

CREATE UNIQUE INDEX idx_stg_consumption ON stg_consumption(region_code, datetime_utc);
DROP TABLE _tmp_consumption;
