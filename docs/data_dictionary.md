# Dictionnaire de données

## Couche RAW (données brutes, non modifiées)

| Table | Grain | Description |
|---|---|---|
| `raw_consumption` | 1 ligne reçue | Consommation horaire par région, telle que reçue (doublons et erreurs inclus) |
| `raw_weather` | 1 ligne reçue | Météo journalière par région (JSON aplati) |
| `raw_regions` | région | Référentiel des régions |
| `meta_ingestion` | lot x source | Volumétrie et horodatage de chaque chargement |

Toutes les tables raw portent `_batch_id` et `_ingested_at` (traçabilité du lot d'origine).

## Couche STAGING (nettoyée)

| Table | Grain | Règles appliquées |
|---|---|---|
| `stg_regions` | région | Codes nettoyés, valeurs nulles exclues |
| `stg_weather` | région x jour | °F convertis en °C, température manquante imputée par (min+max)/2, colonne `temp_quality_flag` |
| `stg_consumption` | région x heure | Dédoublonnage, horodatage normalisé, lignes invalides exclues |
| `quarantine_consumption` | ligne rejetée | Lignes écartées avec `rejection_reason` : `region_inconnue`, `valeur_negative_ou_nulle`, `pic_aberrant` |

## Couche MARTS (publiée)

| Table | Grain | Colonnes clés |
|---|---|---|
| `dim_region` | région | `region_code`, `region_name` |
| `dim_hour` | heure | `datetime_utc`, `date`, `year`, `month`, `hour`, `weekday` (1 = lundi), `is_weekend`, `is_holiday`, `season` |
| `fct_consumption_hourly` | région x heure | `consumption_mw`, `is_imputed` (trou comblé), `temp_mean_c` |
| `fct_consumption_daily` | région x jour | `energy_mwh`, `peak_mw`, `temp_mean_c`, `heating_degree_days`, `imputed_hours` |
| `mart_national_hourly` | heure | `consumption_mw` (somme des régions), `temp_weighted_c` (pondérée par la consommation) |
| `mart_region_kpis` | région x année | `energy_twh`, `peak_mw`, `thermosensitivity_mw_per_c`, `evolution_pct` |
| `mart_load_profile` | saison x jour x heure | `avg_consumption_gw` |
| `mart_peak_hours` | top 10 | `rang`, `datetime_utc`, `consumption_gw`, `temp_weighted_c` |
| `mart_forecast` | heure (période de test) | `actual_mw`, `forecast_mw`, `naive_lag24_mw` |

## Métadonnées et observabilité

| Table | Contenu |
|---|---|
| `dq_results` | Résultat de chaque contrôle qualité par run (`status` : PASS / WARN / FAIL) |
| `meta_pipeline_runs` | Statut, nombre de tentatives et durée de chaque tâche du DAG |
| `meta_model_runs` | Métriques et période de test de chaque entraînement (JSON) |

## Définitions métier

- **Thermosensibilité** : variation de la consommation (MW) pour 1 °C de température en moins, estimée par
  régression linéaire sur les jours ouvrés de chauffage (température < 15 °C).
- **Degrés-jours de chauffage (DJU)** : `max(0, 15 − température moyenne)`.
- **MAPE** : erreur absolue moyenne en pourcentage, `moyenne(|prévu − réalisé| / réalisé)`.
- **Prévision J+1** : prévision de chaque heure du lendemain à partir de l'historique jusqu'à la veille et de la météo du jour.
