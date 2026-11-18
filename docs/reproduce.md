# Reproducing the experiment

Run commands from the repository root. The published data records the completed
November 18, 2026 experiment. Rechecking those files requires no board access.
Fresh hardware builds and measurements are separate operations.

## Software and evidence checks

Development requirements: Python 3.9+, C++17-capable `g++`, and `make`.
The recorded build host used GCC 11.5.0; the physical board used GCC 7.3.0.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-test.txt -r requirements-remote.txt
make verify
```

`make verify` runs these checks in order and stops on failure:

1. Regenerate fixtures in a temporary directory, require byte-identical data,
   and validate hidden and final outputs with the independent C++ reference.
   Signed-overflow traps are enabled; this is not a full UBSan run.
2. Run host lifecycle and remote orchestration tests, normally and with Python
   `-O`. These use local mocks and never connect to a board.
3. Verify exported report hashes, reparse HLS/RTL/implementation values, compare
   them with the published CSV, and check the measured hardware source.
4. Recompute board statistics from raw samples, verify correctness/cleanup and
   the common host revision, and bind measurements to the uploaded ZIP hashes.
5. Extract both ZIPs into temporary directories, validate all hashes, check
   notebook syntax, run file-only host preflight, and reject eight types of
   injected package corruption per archive.
6. Check TeX environments/braces, labels, citations, figures, numerical tables
   and unchanged board runtime source hashes. No TeX engine runs.

Collectors rewrite derived JSON/CSV validation summaries. Original board CSVs,
logs and archives are preserved. The C++ check creates an ignored local binary.

## Report and figures

The final report is `report/ffn_report.tex`, with an inline TikZ architecture
diagram and PNG figures. It needs standard LaTeX packages, including TikZ.
This delivery intentionally has no report PDF and has not been typeset.
To regenerate only PNG figures from the published data:

```bash
python -m pip install -r requirements-plot.txt
make figures
python scripts/check_report.py
```

`scripts/collect_results.py` is for actual builds. Without `runs/`, it exits
without changing published tables. Use `scripts/check_evidence.py` to verify
the preserved HLS snapshot.

## Rebuild HLS and RTL

The recorded toolchain is Vitis HLS/Vivado 2025.1, device `xc7z020clg400-1`,
and a 10 ns clock. Source your installation's `Vitis/settings64.sh` to put
`vitis-run`, `vivado` and simulator tools on PATH. Licensed tools are not bundled.

```bash
python scripts/run_experiments.py B11 B44 U44 K44 --cosim --export
python scripts/run_experiments.py S00 B12 B14 B21 B22 B24 B41 B42
python scripts/collect_results.py
```

Each run creates `runs/CONFIG/TIMESTAMP/` with frozen source, configuration,
hashes, logs and reports. Each C simulation checks 206 inferences. Each RTL
suite performs two error-state checks and four LOAD/RUN/RUN groups: 14 calls.

If the execution environment prevents XSIM startup,
`python scripts/verify_run.py PATH_TO_RUN` retries RTL/IP export in an environment
where the simulator is allowed. It preserves the original attempt without
repeating synthesis or substituting new hardware source.

## Rebuild deployment packages

Repeat for the new B11 and K44 run paths:

```bash
python scripts/build_board.py PATH_TO_VERIFIED_RUN
python scripts/verify_control.py PATH_TO_VERIFIED_RUN
python -O scripts/check_interface.py PATH_TO_VERIFIED_RUN/overlay/ffn.hwh
python scripts/verify_done_idle.py PATH_TO_VERIFIED_RUN
python scripts/package_board.py PATH_TO_VERIFIED_RUN --revision audit3
```

Implementation checks setup/hold timing before releasing a matched bit/HWH pair.
Extra simulations exercise the generated reset controller, actual AXI-Lite RTL
and complete FFN RTL, including stalls, bounded DDR accesses, repeated inference
and reset/reload. The done/idle test checks completion before idle. Packaging
requires successful verification records.

Each new build manifest begins with `board_tested=false`. Successful board tests
produce a separate attestation bound to actual package hashes; editing a manifest
is not a substitute. Full build directories are ignored by Git.
`scripts/export_evidence.py` exports selected reports from local builds and
refuses to overwrite an existing snapshot.

## Physical board and timing scope

Follow [board/README.md](../board/README.md) during an authorized reservation.
The tested image had PYNQ 2.5, Python 3.6.5, NumPy 1.13.3 and Linux 4.19.0.
Development dependencies above belong on the workstation, not the course board.

FPGA timing includes input copy/flush, control writes, execution/polling/status,
and output invalidate/copy. It excludes programming, LOAD, shape/type checks,
result comparison and file I/O. CPU timing covers compiled computation on
resident arrays. Each path uses 20 warm-ups and three rounds of 1,000 calls,
checking every output outside timing. The 100-call phase profile is separate.

HLS estimates, top-level RTL cycles, implementation resources/timing, FPGA host
latency and CPU computation have different boundaries. The report keeps them
separate. Board results come from one reservation and boot, without CPU affinity
or OS isolation and without an on-board accelerator cycle counter.
