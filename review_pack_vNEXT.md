# Paper A Review Pack vNEXT

- generatedAtUtc: `2026-02-28T15:46:33.315430+00:00`

## Preflight Status

- pytest_q: `0`
- independent_check_paperA: `0`
- make_clean_paper: `0`

## Freshness (mtime + sha256)

| artifact | path | mtime_utc | sha256 |
|---|---|---|---|
| results_bitexact.csv | `papers/paperA/artifacts/tables/results_bitexact.csv` | `2026-02-28T15:45:20.240752+00:00` | `ff0ee3486cec70dbcc289f1ca178d0e2e9c4e8ef6e30df634b31ae647d78a862` |
| results_qor.csv | `papers/paperA/artifacts/tables/results_qor.csv` | `2026-02-28T15:45:20.406044+00:00` | `e4e933c52e7ea1bf595b3b212ed1517b36c1d7eb7c95c1b2b9fac075baf5af41` |
| results_throughput.csv | `papers/paperA/artifacts/tables/results_throughput.csv` | `2026-02-28T15:45:20.550113+00:00` | `df8f00311f866e48ed8c47bb622641e147fc9a6a908bcc478d2d522133e52b01` |
| vivado_coverage_report.md | `papers/paperA/artifacts/evidence/vivado_coverage_report.md` | `2026-02-28T15:15:19.179910+00:00` | `6042b1142328d9dd6c31101bb1cf63fcfc0d90b92a7af9ec10ebfa3354bd957a` |

## Preview: results_bitexact.csv

```csv
benchmarkId,modelId,verify_ok,mismatches_len,digestMatchOk,ticks,ir_sha256,bench_report_path
B1,example_b1_small_subgraph,true,0,true,20,31b5a208c287eaec92e2e39f4f19442a7c080a2ff000c0f667cd984b7e1e8286,build/paperA_routeA/B1/example_b1_small_subgraph/bench_report.json
B2,B2_mid_64_1024,true,0,true,20,61d1c9b1b97d3d8509c59349445472ed8cf76bf0205e560a1cacffd21509e98b,build/paperA_routeA/B2/B2_mid_64_1024/bench_report.json
B3,B3_kernel_302_7500,true,0,true,20,05ce6de59b1518129c3d690c5fca81e507dd8c109193fd83b2ae1301e8447080,build/paperA_routeA/B3/B3_kernel_302_7500/bench_report.json
B4,B4_celegans_external_bundle,true,0,true,20,5b21d1db4975db16c02802eaba409f4ac194535880a15b215f7bd02d01071473,build/paperA_routeA/B4/B4_celegans_external_bundle/bench_report.json
```

## Preview: results_qor.csv

```csv
benchmarkId,ii,latencyCycles,lut,ff,bram,dsp,wns,csim_ok,csynth_ok,cosim_ok,vivado_impl_ok,vivado_impl_status,vivado_impl_reason,chosen_bench_report_path
B1,32,31,1148,355,0,0,1.129,true,true,-,true,OK,-,build/paperA_routeA/B1/example_b1_small_subgraph/bench_report.json
B2,614,613,4818,4738,1,1,0.957,true,true,-,true,OK,-,build/paperA_routeA/B2/B2_mid_64_1024/bench_report.json
B3,2746,2745,3172,3110,7,1,0.988,true,true,-,true,OK,-,build/paperA_routeA/B3/B3_kernel_302_7500/bench_report.json
B4,100,99,2584,2633,0,0,1.032,true,true,-,true,OK,-,build/paperA_routeA/B4/B4_celegans_external_bundle/bench_report.json
```

## Preview: results_throughput.csv

```csv
benchmarkId,cpuTicksPerSecond,hwIiCyclesPerTick,clkNs,wnsNs,fmaxMhzEstimated,hwTicksPerSecondEstimated,speedupEstimated,vivadoImplStatus,vivadoImplReason,cpuBenchReportPath,hwBenchReportPath
B1,495514.358427,32.000000,5.000000,1.129000,258.331181,8072849.392922,16.291858,OK,-,paper_cpu_runs/b1/example_b1_small_subgraph/bench_report.json,build/paperA_routeA/B1/example_b1_small_subgraph/bench_report.json
B2,162602.683651,614.000000,5.000000,0.957000,247.341083,402835.640642,2.477423,OK,-,paper_cpu_runs/b2/B2_mid_64_1024/bench_report.json,build/paperA_routeA/B2/B2_mid_64_1024/bench_report.json
B3,44480.467700,2746.000000,5.000000,0.988000,249.252243,90769.207309,2.040653,OK,-,paper_cpu_runs/b3/B3_kernel_302_7500/bench_report.json,build/paperA_routeA/B3/B3_kernel_302_7500/bench_report.json
```

## Preflight Logs

- `build/paperA_preflight_out_vNEXT/pytest_q.stdout.txt`
- `build/paperA_preflight_out_vNEXT/pytest_q.stderr.txt`
- `build/paperA_preflight_out_vNEXT/pytest_q.exitcode.txt`
- `build/paperA_preflight_out_vNEXT/independent_check_paperA.stdout.txt`
- `build/paperA_preflight_out_vNEXT/independent_check_paperA.stderr.txt`
- `build/paperA_preflight_out_vNEXT/independent_check_paperA.exitcode.txt`
- `build/paperA_preflight_out_vNEXT/make_clean_paper.stdout.txt`
- `build/paperA_preflight_out_vNEXT/make_clean_paper.stderr.txt`
- `build/paperA_preflight_out_vNEXT/make_clean_paper.exitcode.txt`
