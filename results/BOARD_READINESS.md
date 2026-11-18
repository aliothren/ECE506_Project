> Update after board testing: B11 and K44 passed on board2 with the audit3 host. See [BOARD_RESULTS.md](BOARD_RESULTS.md) for final data and the two host fixes. The text below preserves the earlier local-only audit.

# ECE 506 FFN — historical pre-board audit

Snapshot: before board testing on 2026-11-18. **Historical state, superseded by BOARD_RESULTS.md and the audit3 releases.**
Use the revised `audit1` deployment archives and their staged notebook. This audit
does not authorize or perform a connection to the course boards.

## Findings and changes

The current FFN overlays already use the corrected reset wiring. The previous
lab incident was an active-low auxiliary reset tied low, keeping the peripheral
in reset and preventing a control read from completing. This audit uses each
FFN build's actual vendor reset netlist: it reproduces the held-reset failure
with the old connection and verifies release and AXI read completion with the
implemented connection. The bitstreams and HLS computation source were not
changed by this deployment audit.

The original FFN runner had gaps that could make failure handling unsafe:

- Construction immediately programmed the FPGA and bound the driver. It now
  performs only file checks; programming and the first PL read are separate cells.
- Pointer writes and the initial control read were outside the protected call
  region. Every MMIO access in a call, including return-status reads, is now
  protected; idle/start/auto-restart state is checked before launch.
- Replacing a timed-out session object could bypass its flags and lose buffer
  references. The runner now retains an owning reference, uses a cooperative OS
  lock, and persists an unclosed-session marker across notebook kernel restarts.
- The output allocation was not explicitly initialized/flushed before the first
  hardware write. All three allocations are now initialized and flushed; input
  flush and output invalidate remain in the inference path.
- An earlier successful validation could remain available after a failed repeat.
  Validation is revoked before rerunning the suite; wrong output/status poisons
  the session and blocks timing and reuse.
- HWH checks used Python `assert`, which disappears under `python -O`. They now
  raise explicit exceptions. The exact FFN register ABI, file completeness,
  bitstream device/payload, and audit-to-bit/HWH binding are checked before use.

An allocation failure before launch can be closed safely after an idle check.
Uncertain MMIO, timeout, interruption, or incorrect output deliberately blocks
normal close and free. The notebook explains the recovery path and never
attempts automatic reprogramming, PS initialization, or DDR reconfiguration.

## Verification evidence

| Check | Result | Scope |
|---|---|---|
| Existing C simulation | 12/12 configurations; 2,472 comparisons | 206 inferences/configuration |
| Existing RTL co-simulation | B11/B44/U44/K44 pass | 14 calls each, including 8 inferences |
| Implementation | B11 and K44 pass at 100 MHz | Positive setup and hold slack |
| Vendor reset and control read | Both released overlays pass | Old tie-low failure reproduced; corrected tie-high releases |
| AXI-Lite register simulation | Both pass | Pointer halves, strobes, operation, repeated launch, done clear, stalls, reset |
| Complete FFN RTL lifecycle | Both pass | LOAD, repeat RUN, reset, stale-state guard, reload, changed parameters |
| DDR model checks | Both pass | 8,336 reads / 48 writes; correct output; exact buffer bounds, burst protocol and stalls |
| HWH fault injection | 14/14 rejected for each overlay | Also run with Python optimization enabled |
| Host/ownership fault tests | 16/16 pass in normal and optimized Python | First/last MMIO, timeout, interrupt, nonidle, ownership, crash marker |
| ZIP release check | Both pass | Fresh extraction, all hashes, notebook syntax, extracted-host preflight, 8 injected package faults |

The three new RTL tests per overlay run against frozen copies of the actual
synthesized Verilog and generated vendor reset netlist. Sources, commands, file
hashes and logs are in each selected run's `control_verification/`. The full RTL
lifecycle model uses delayed reads/writes and verifies all three inference
outputs against independent fixtures. It checks RUN before LOAD both at startup
and after reset, with no DDR requests in either case. No test relies on a
mocked arithmetic result.

Initial runs passed but emitted missing initialization-file warnings because
HLS-generated `.dat` files were in a subdirectory. Those runs are retained in
`control_verification_initial_missing_init_files/`. The runner was corrected to
stage those generated files in the simulator working directory, and both suites
were rerun successfully without those warnings. Hardware source and bitstreams
were unchanged.

Machine-readable records: `board_readiness.json`, `release_validation.json`,
`interface_validation_B11.json`, `interface_validation_K44.json`, and
`report_source_validation.json`. Host logs: `host_tests.txt` and
`host_tests_optimized.txt`. Original sweep results remain in `hls_results.csv`.

## Remaining limits and board procedure

These simulations do not include the PS7, SmartConnect behavior, board DDR,
PYNQ Linux, cache maintenance implementation, or the actual installed PYNQ
version. The physical test remains necessary. A Python polling timeout cannot
interrupt a memory-mapped access that stalls in the bus fabric. The software
lock coordinates this runner only; unrelated programs must not program another
overlay during the session. A forced kernel exit may release buffers while
hardware is still active, which is why the recovery instructions prohibit
kernel restarts after uncertain access and require board recovery instead.

Start with the B11 archive: preflight → program/clock → first control read and
unloaded guards → allocation → one-input smoke → 206-input validation → timing
→ normal close. Only then test K44 in a fresh notebook kernel. Compile/run the
included CPU reference on the board and retain its compiler/frequency metadata.
Download the raw measurements and stage logs. Full instructions are in
`board/README.md` and each archive's `ffn_board.ipynb`.

## Report

`report/ffn_report.tex` reports the completed architecture, numerical rules,
12-point comparison, RTL measurements, implementation results, and deployment
verification. It distinguishes HLS estimates, simulation cycles, and physical
implementation. Board latency and CPU speedup are explicitly pending. Existing
PNG figures are referenced. Source structure, references to figures/labels, and
the numerical HLS table were checked; **no TeX engine was run and no report PDF
was generated**.
