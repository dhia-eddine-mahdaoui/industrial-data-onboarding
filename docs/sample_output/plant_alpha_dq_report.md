# Data-quality report: plant_alpha

Overall: **PASSED**

## Threshold rules

| Source | Rule | Observed | Of total | Measure | Limit | Result |
|---|---|---:|---:|---:|---:|---|
| asset_register | assets_without_register_id | 1 | 11 | 1 | 2 | pass |
| readings | null_value | 80 | 21757 | 0.3677% | 2.00% | pass |
| readings | unparseable_timestamp | 18 | 21757 | 0.0827% | 0.50% | pass |
| readings | unknown_unit | 11 | 21757 | 0.0506% | 0.50% | pass |
| readings | unmapped_sensor | 0 | 21757 | 0.0000% |  | n/a |
| readings | quantity_mismatch | 0 | 21757 | 0.0000% | 0.10% | pass |
| readings | out_of_range | 89 | 21757 | 0.4091% | 2.00% | pass |
| readings | unmatched_asset | 0 | 21757 | 0.0000% | 1.00% | pass |
| readings | duplicates_removed | 216 | 21757 | 0.9928% | 5.00% | pass |
| maintenance | duplicates_removed | 4 | 58 | 6.8966% | 10.00% | pass |
| maintenance | missing_work_order | 0 | 58 | 0.0000% |  | n/a |
| maintenance | unparseable_timestamp | 0 | 58 | 0.0000% | 1.00% | pass |
| maintenance | unmatched_asset | 9 | 58 | 15.5172% | 20.00% | pass |

## Information

| Source | Metric | Value | Note |
|---|---|---:|---|
| asset_register | assets_loaded | 11 | distinct assets in register |
| entity_resolution | maintenance_names_matched | 26 | distinct raw names |
| entity_resolution | maintenance_names_review | 6 | distinct raw names |
| entity_resolution | maintenance_names_unmatched | 1 | distinct raw names |
| entity_resolution | readings_names_matched | 27 | distinct raw names |
| readings | rows_in | 21757 | raw CSV rows after header parsing |
| readings | unit_k_rows | 11 | not in unit table |
| readings | unit_psi_rows | 2565 | normalised to SI kPa (scale 6.894757, offset 0.0) |
| readings | unit_c_rows | 7754 | normalised to SI degC (scale 1.0, offset 0.0) |
| readings | unit_bar_rows | 6122 | normalised to SI kPa (scale 100.0, offset 0.0) |
| readings | unit_degf_rows | 5305 | normalised to SI degC (scale 0.5555556, offset -17.777778) |
| readings | spikes_flagged | 122 | kept in model; jump vs previous sample above spike_delta |
| readings | gaps_detected | 5 | sample follows a gap longer than 120 minutes |
| readings | anomalies_flagged | 379 | |z| > 3.0 vs first 7 days of each series |
| maintenance | rows_in | 58 | raw CSV rows |

## Unresolved asset names (review queue)

- maintenance: 'Compressor C-7' -> CMP-01 (status review, confidence 0.8)
- maintenance: 'MPP-03B' -> PMP-03B (status review, confidence 0.8)
- maintenance: 'Miexr Motor 1' -> MTR-01 (status review, confidence 0.889)
- maintenance: 'P-1A' -> PMP-01A (status review, confidence 0.75)
- maintenance: 'P-3A (north)' -> PMP-03A (status review, confidence 0.75)
- maintenance: 'Pump 9' -> no candidate (status unmatched, confidence 0.667)
- maintenance: 'Pup 1A' -> PMP-01A (status review, confidence 0.8)
