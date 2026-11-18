# Board-verified FFN releases — audit3

B11 and K44 passed on PYNQ-Z2 board2 on 2026-11-18: 206 correctness cases and 3,000 measured inferences each, plus normal cleanup. Use these audit3 packages; earlier revisions are retained locally and omitted from Git.

- [B11_20261118T204214272606Z_audit3.zip](B11_20261118T204214272606Z_audit3.zip): SHA-256 `e437e4cc2e03cd56040e0e0ac480f47986a7fd452f58a5f9da8c0116621b069e`
- [K44_20261118T205854106482Z_audit3.zip](K44_20261118T205854106482Z_audit3.zip): SHA-256 `d0786123df1463947d24036fb17cc36f1d6e38460a0d122772b681a426393a72`

The ZIPs are the exact bytes uploaded and tested. Their immutable build-time manifest field `board_tested=false` is superseded by the separate [board validation record](../results/board_results.json), which binds the successful tests to each ZIP/bit/HWH hash. Do not edit the ZIP to change that field.

The README inside each immutable archive describes its pre-board build state.
For the completed experiment and current operating instructions, use this file
and [board/README.md](../board/README.md). The host code and notebook are unchanged.

Each archive includes the staged notebook, guarded host, data, CPU source/runner, and reset/AXI/completion-order simulation evidence. The audit3 host supports the board image’s older NumPy and waits correctly for completion followed by idle.

See [measured results](../results/BOARD_RESULTS.md), [report TeX](../report/ffn_report.tex), and the package README/notebook for operation.
