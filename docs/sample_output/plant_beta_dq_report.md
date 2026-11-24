# Data-quality report: plant_beta

Overall: **PASSED**

## Threshold rules

| Source | Rule | Observed | Of total | Measure | Limit | Result |
|---|---|---:|---:|---:|---:|---|
| asset_register | assets_without_register_id | 0 | 3 | 0 | 2 | pass |
| readings | null_value | 8 | 841 | 0.9512% | 2.00% | pass |
| readings | unparseable_timestamp | 0 | 841 | 0.0000% |  | n/a |
| readings | unknown_unit | 0 | 841 | 0.0000% |  | n/a |
| readings | unmapped_sensor | 0 | 841 | 0.0000% |  | n/a |
| readings | quantity_mismatch | 0 | 841 | 0.0000% |  | n/a |
| readings | out_of_range | 0 | 841 | 0.0000% |  | n/a |
| readings | unmatched_asset | 0 | 841 | 0.0000% | 1.00% | pass |
| readings | duplicates_removed | 1 | 841 | 0.1189% | 5.00% | pass |
| maintenance | duplicates_removed | 0 | 5 | 0.0000% | 10.00% | pass |
| maintenance | missing_work_order | 0 | 5 | 0.0000% |  | n/a |
| maintenance | unparseable_timestamp | 0 | 5 | 0.0000% |  | n/a |
| maintenance | unmatched_asset | 0 | 5 | 0.0000% | 10.00% | pass |

## Information

| Source | Metric | Value | Note |
|---|---|---:|---|
| asset_register | assets_loaded | 3 | distinct assets in register |
| entity_resolution | maintenance_names_matched | 5 | distinct raw names |
| entity_resolution | readings_names_matched | 9 | distinct raw names |
| readings | rows_in | 841 | raw CSV rows after header parsing |
| readings | unit_c_rows | 505 | normalised to SI degC (scale 1.0, offset 0.0) |
| readings | unit_bar_rows | 336 | normalised to SI kPa (scale 100.0, offset 0.0) |
| readings | spikes_flagged | 0 | kept in model; jump vs previous sample above spike_delta |
| readings | gaps_detected | 0 | sample follows a gap longer than 120 minutes |
| readings | anomalies_flagged | 0 | |z| > 3.0 vs first 3 days of each series |
| maintenance | rows_in | 5 | raw CSV rows |

## Unresolved asset names (review queue)

- none
