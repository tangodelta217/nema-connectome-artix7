# Paper A Sponsor README (Boardless RouteA)

## Comando único

```bash
bash tools/reproduce_paperA_routeA.sh
```

## Qué demuestra hoy (boardless)

- Correctitud reproducible: `pytest` + `tools/independent_check.py --paperA`.
- Evidencia bit-exact por benchmark en:
  - `papers/paperA/artifacts/tables/results_bitexact.csv`
- Evidencia de flujo HW sin placa (HLS + Vivado batch) para RouteA:
  - B3: `build/paperA_routeA/B3/B3_kernel_302_7500/`
  - B4: `build/paperA_routeA/B4/B4_celegans_external_bundle/`
- Timing boardless en Vivado (WNS/TNS/reportes):
  - `.../hw_reports/vivado_batch/vivado_timing_summary.rpt`
  - `.../hw_reports/vivado_batch/vivado_utilization.rpt`
- PDF compilado del preprint:
  - `papers/paperA/text/paper.pdf`

## Qué falta sin placa

- No hay medición real on-board de potencia/latencia.
- No hay validación HW-in-the-loop con digest de salida en dispositivo físico.
- No hay reporte de variabilidad eléctrica/térmica de placa real.

## Qué se mide con placa y cómo (lista concreta)

- Programación de bitstream:
  - `tools/fpga/deploy_bitstream.sh`
  - referencia: `docs/DEPLOY.md`
- Medición de latencia on-board:
  - `tools/fpga_measure/collect_latency.py`
  - referencia: `docs/FPGA_MEASUREMENT.md`
- Medición de potencia on-board:
  - `tools/fpga_measure/collect_power.py`
  - referencia: `docs/FPGA_MEASUREMENT.md`
- Reporte final de medición real (cuando exista placa):
  - `build_hw/fpga_measure/power_latency_report.json`
  - schema: `tools/fpga_measure/schema_power_latency_report.json`

## Outputs esperados del comando único

- Bundle para compartir:
  - `build/paperA_routeA_bundle.tar.gz`
- Incluye como mínimo:
  - `paperA.pdf`
  - tablas `results_bitexact/results_qor/results_throughput`
  - logs de ejecución del pipeline
  - `bench_report.json` de B3/B4
  - reportes Vivado (`run_vivado.log`, `vivado_timing_summary.rpt`, `vivado_utilization.rpt`)

