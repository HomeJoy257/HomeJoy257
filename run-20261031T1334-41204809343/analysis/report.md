# RailRadar · Análisis de datos reales

> Análisis estadístico para un producto **informativo**. Nada de esto valida su uso para seguridad ferroviaria ni para evitar accidentes.

## 1. Procedencia (¿son datos reales y oficiales?)

- Periodo: 2026-10-31T13:16:37.513384+00:00 → 2026-10-31T13:31:28.222367+00:00
- Sondeos OK / error: 180 / 0  ·  HTTP: {200: 180}
- Hosts servidores: {'gtfsrt.renfe.com': 180}
- Hosts NO oficiales: ninguno
- Respuestas originales guardadas y verificadas por SHA-256: 4 (discrepancias: 0) → ver `provenance_manifest.csv`
- Ratio ts vehículo == ts cabecera: 11.8%
- Decimales de las coordenadas (resolución): {2: 1, 3: 58, 4: 553, 5: 5405, 6: 6505}  (4 dec ≈ 11 m, 5 ≈ 1,1 m, 6 ≈ 0,11 m)

## cercanias

- **Vía:** identificable en general
- **Sentido:** determinable en 15.0 % de los pares de puntos
- **Realismo:** al recibirse, el tren puede haber avanzado p50 0.0 m / p90 226.8 m desde la coordenada publicada

| Métrica | Valor |
|---|---|
| vehicles | 352 |
| points | 12522 |
| age_at_first_seen_s | {"p50": 16.5, "p90": 16.5, "p99": 26.5} |
| share_age_le_120s | 100.0 % |
| update_interval_s | {"p50": 20.0, "p90": 22.0} |
| implied_speed_kmh | {"p50": 63.8, "p90": 424.4, "p99": 5748.6} |
| implausible_jumps | 267 |
| non_monotonic_ts | 0 |
| frozen_repeats | 10044 |
| gps_noise_rms_2d_m | {"p50": 0.0, "p90": 0.0, "clusters": 363} |
| direction_determinable | 15.0 % |
| reported_bearing | 0.0 % |
| reported_speed | 0.0 % |
| direction_id_present | 0.0 % |
| bearing_vs_computed_deg | {"p50": null, "p90": null, "n": 0} |
| direction_reversals | 217 |
| travel_since_observation_m | {"p50": 0.0, "p90": 226.8, "p99": 2558.4} |
| track | {"points": 12522, "within_10m_of_rail": "79.8 %", "within_25m_of_rail": "84.1 %", "far_gt_50m": "12.4 %", "multi_track_zone": "79.4 %", "track_identifiable_in_multi": "sin σ", "parallel_track_separation_m": {"p50": 4.2, "p10": 3.5}} |

