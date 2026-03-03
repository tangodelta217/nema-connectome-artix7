# Power Methodology (Pre-Board, Estimated Only)

## Scope

This workflow produces estimated post-implementation power only.
No value may be labeled as measured on board.

## Round10b Functional-SAIF Procedure

1. Use existing post-route checkpoints with canonical template path:
   - `build/amd_vivado_artix7_v5/<bench>/post_route.dcp`
   - Example (`b1_small`): `build/amd_vivado_artix7_v5/b1_small/post_route.dcp`
   - Example (`b3_varshney_exec_expanded_gap_300_5824`): `build/amd_vivado_artix7_v5/b3_varshney_exec_expanded_gap_300_5824/post_route.dcp`
2. Export functional netlist: `write_verilog -mode funcsim -force dut_funcsim.v`.
3. Compile and elaborate with xsim front-end:
   - `xvlog -sv dut_funcsim.v tb_tick.sv`
   - `xelab -debug typical tb_tick glbl -s sim_<bench>`
4. Dump SAIF from functional simulation:
   - `open_saif activity_func.saif`
   - `log_saif [get_objects -r /tb_tick/dut/*]`
   - `run -all`
   - `close_saif`
5. Run power on same DCP:
   - `report_power` vectorless baseline
   - `read_saif activity_func.saif` (strip-path fallback attempts)
   - `report_power` SAIF-guided

## Tick Runtime and Scope

| bench | ticks | clock_period_ns | saif_scope | matched_nets | total_nets |
|---|---:|---:|---|---:|---:|
| b1_small | 50 | 5 | /tb_tick/dut/* | 1059 | 1329 |
| b3_varshney_exec_expanded_gap_300_5824 | 10 | 5 | /tb_tick/dut/* | 4147 | 8683 |

## Evidence Artifacts

- `build/amd_power_artix7_v7_funcsaif/b1_small/activity_func.saif`
- `build/amd_power_artix7_v7_funcsaif/b1_small/sim_compile.log`
- `build/amd_power_artix7_v7_funcsaif/b1_small/sim_run.log`
- `build/amd_power_artix7_v7_funcsaif/b1_small/power_saif_func.rpt`
- `build/amd_power_artix7_v7_funcsaif/b3_varshney_exec_expanded_gap_300_5824/activity_func.saif`
- `build/amd_power_artix7_v7_funcsaif/b3_varshney_exec_expanded_gap_300_5824/sim_compile.log`
- `build/amd_power_artix7_v7_funcsaif/b3_varshney_exec_expanded_gap_300_5824/sim_run.log`
- `build/amd_power_artix7_v7_funcsaif/b3_varshney_exec_expanded_gap_300_5824/power_saif_func.rpt`
- `build/amd_power_artix7_v7_funcsaif/summary.json`
- `review_pack/tables/artix7_power_v7_funcsaif.csv`
- `review_pack/tables/artix7_power_final.csv`

## Limitations and Claim Policy

- Label all values as `ESTIMATED_PRE_BOARD_ONLY`.
- This remains pre-board estimation and not board measurement.
- Functional SAIF improves representativity versus synthetic clock-only activity, but does not replace silicon measurement.
