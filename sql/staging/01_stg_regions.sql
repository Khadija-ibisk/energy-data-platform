-- Référentiel des régions nettoyé
DROP TABLE IF EXISTS stg_regions;
CREATE TABLE stg_regions AS
SELECT DISTINCT
    TRIM(region_code) AS region_code,
    TRIM(region_name) AS region_name
FROM raw_regions
WHERE region_code IS NOT NULL;
