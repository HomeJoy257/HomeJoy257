# RailRadar · Análisis de datos reales

> Análisis estadístico para un producto **informativo**. Nada de esto valida su uso para seguridad ferroviaria ni para evitar accidentes.

## 1. Procedencia (¿son datos reales y oficiales?)

- Periodo: 2026-10-31T13:38:47.558582+00:00 → 2026-11-01T13:39:56.085427+00:00
- Sondeos OK / error: 17213 / 25  ·  HTTP: {200: 17213}
- Hosts servidores: {'gtfsrt.renfe.com': 17213}
- Hosts NO oficiales: ninguno
- Respuestas originales guardadas y verificadas por SHA-256: 339 (discrepancias: 0) → ver `provenance_manifest.csv`
- Ratio ts vehículo == ts cabecera: 14.1%
- Decimales de las coordenadas (resolución): {0: 1, 1: 11, 2: 75, 3: 5342, 4: 48582, 5: 446268, 6: 560454}  (4 dec ≈ 11 m, 5 ≈ 1,1 m, 6 ≈ 0,11 m)

## cercanias

- **Timestamp:** timestamp de LOTE (pocos valores por respuesta), no de fijación GPS → la regla de 120 s NO se puede garantizar (posiciones repetidas: 81.3 %)
- **Vía:** error GPS no medible (coordenadas repetidas o ajustadas); no se puede afirmar la vía
- **Sentido:** determinable en 16.1 % de los pares de puntos
- **Realismo:** al recibirse, el tren puede haber avanzado p50 0.0 m / p90 187.9 m desde la coordenada publicada

| Métrica | Valor |
|---|---|
| vehicles | 3019 |
| points | 852596 |
| age_at_first_seen_s | {"p50": 11.2, "p90": 16.1, "p99": 21.3} |
| share_age_le_120s | 99.9 % |
| update_interval_s | {"p50": 20.0, "p90": 21.0} |
| implied_speed_kmh | {"p50": 65.4, "p90": 441.8, "p99": 3916.6} |
| implausible_jumps | 21311 |
| non_monotonic_ts | 0 |
| frozen_repeats | 690323 |
| frozen_share | 81.3 % |
| gps_noise_rms_2d_m | {"p50": null, "p90": 0.0, "clusters": 23546} |
| direction_determinable | 16.1 % |
| reported_bearing | 0.0 % |
| reported_speed | 0.0 % |
| direction_id_present | 0.0 % |
| bearing_vs_computed_deg | {"p50": null, "p90": null, "n": 0} |
| direction_reversals | 18679 |
| travel_since_observation_m | {"p50": 0.0, "p90": 187.9, "p99": 1984.4} |
| track | {"points": 852596, "within_10m_of_rail": "79.8 %", "within_25m_of_rail": "84.8 %", "far_gt_50m": "11.9 %", "multi_track_zone": "78.9 %", "track_identifiable_in_multi": "sin σ", "parallel_track_separation_m": {"p50": 4.2, "p10": 3.5}} |
| vehicle_ts_missing | 0 |
| distinct_ts_per_response_p50 | 3.0 |
| ts_semantics | timestamp de LOTE (pocos valores por respuesta), no de fijación GPS |

## larga_distancia

- **Timestamp:** SIN timestamp por vehículo → la regla de 120 s NO se puede garantizar (posiciones repetidas: 0.1 %)
- **Vía:** NO identificable de forma fiable en tramos de doble vía
- **Sentido:** determinable en 90.0 % de los pares de puntos
- **Realismo:** al recibirse, el tren puede haber avanzado p50 0.0 m / p90 0.0 m desde la coordenada publicada

| Métrica | Valor |
|---|---|
| vehicles | 686 |
| points | 208137 |
| age_at_first_seen_s | {"p50": 0.0, "p90": 0.0, "p99": 0.0} |
| share_age_le_120s | 100.0 % |
| update_interval_s | {"p50": 19.9, "p90": 30.2} |
| implied_speed_kmh | {"p50": 83.7, "p90": 241.1, "p99": 669.8} |
| implausible_jumps | 8035 |
| non_monotonic_ts | 237 |
| frozen_repeats | 109 |
| frozen_share | 0.1 % |
| gps_noise_rms_2d_m | {"p50": 20.4, "p90": 33.2, "clusters": 1216} |
| direction_determinable | 90.0 % |
| reported_bearing | 0.0 % |
| reported_speed | 0.0 % |
| direction_id_present | 0.0 % |
| bearing_vs_computed_deg | {"p50": null, "p90": null, "n": 0} |
| direction_reversals | 2422 |
| travel_since_observation_m | {"p50": 0.0, "p90": 0.0, "p99": 0.0} |
| track | {"points": 208137, "within_10m_of_rail": "98.2 %", "within_25m_of_rail": "98.9 %", "far_gt_50m": "0.7 %", "multi_track_zone": "75.9 %", "track_identifiable_in_multi": "0.0 %", "parallel_track_separation_m": {"p50": 4.4, "p10": 3.7}, "note": "σ GPS ≈ 20.4 m. Separación típica entre vías ≈ 4.4 m. Si σ ≥ separación/2, la vía NO es identificable."} |
| vehicle_ts_missing | 208178 |
| distinct_ts_per_response_p50 | 1.0 |
| ts_semantics | SIN timestamp por vehículo |

