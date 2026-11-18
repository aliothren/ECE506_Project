# ECE 506: HLS optimization of a two-layer FFN

A fixed-point **64 → 128 → 64** feed-forward network for PYNQ-Z2 / XC7Z020.
The project studies output/input parallelism and on-chip weight banking versus
packing. Parameters are loaded at runtime and retained between inferences.

**Authors:** Yuxin Ren and Dongwei Wang · Fall 2026 · Experiments: November 18, 2026.

## Completed results

| Measurement | B11 baseline | K44 packed | Interpretation |
|---|---:|---:|---|
| HLS compute cycles | 18,181 | 1,669 | 10.89x improvement in the computation estimate |
| Implemented clock | 100 MHz | 100 MHz | Both meet setup and hold constraints |
| Board Python/FPGA median | 1,103.991 µs | 964.715 µs | 1.14x end-to-end improvement |
| Board C++ CPU median after each FPGA test | 143.499 µs | 142.971 µs | The measured FPGA host path remains slower |

All **12 configurations** pass 206 C-simulation comparisons each; B11, B44,
U44 and K44 pass RTL co-simulation. B11 and K44 complete implementation and
physical-board validation: 206 correctness cases, 3,000 measured calls, and
100 separate diagnostic calls each.

At P=Q=4, unpartitioned weight memory limits the main loop to II=16. Banking
restores II=1; packing keeps the same 1,669-cycle computation estimate while
reducing HLS-estimated BRAM from 36 to 20 BRAM_18K units. Board measurements
include host control and buffer synchronization; HLS cycles do not.

Read the [complete report (TeX)](report/ffn_report.tex),
[local results](results/LOCAL_RESULTS.md), and [board results](results/BOARD_RESULTS.md).
The report includes architecture, methods, all measured results, limitations,
and references.

## Verify a fresh clone

Use Python 3.9+ and a C++17 compiler on the development machine:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-test.txt -r requirements-remote.txt
make verify
```

This verifies fixture regeneration and the independent C++ reference, host and
remote-runner guards, archived HLS reports, raw board measurements, release contents, and report-source consistency. It does not access a board or
require Vitis/Vivado. See [reproduction instructions](docs/reproduce.md) for
HLS builds, figures, and the detailed measurement boundaries.

## Repository contents

| Path | Purpose |
|---|---|
| `hls/` | Accelerator, configuration pragmas, HLS testbench, tool scripts |
| `reference/`, `data/` | Independent Python/C++ reference and deterministic fixtures |
| `board/` | Staged notebook, PYNQ host, metadata and ownership checks |
| `tests/` | Host lifecycle/remote-runner regressions and RTL integration testbenches |
| `vivado/` | Overlay construction and attributed PYNQ-Z2 board definition |
| `scripts/` | Build, verification, collection, plotting and staged remote tooling |
| `results/hls_reports/` | Original selected reports and their hash manifest |
| `results/board2_20261118/{B11,K44}/` | Final raw board measurements and execution records |
| `deploy/` | Deployment packages and their manifests |
| `report/`, `figures/` | Final TeX report and PNG figures |

The [numerical/interface contract](spec.md) and [configuration matrix](experiments.csv)
define the experiment. Generated vendor build directories and local credentials
are excluded from Git. The selected tool reports and measurement data are
included for independent analysis.

## Board use

Use the [two verified releases](deploy/README.md) and follow the
[staged board procedure](board/README.md). A new board session requires its own
reservation and working environment checks. The optional [remote helper](docs/remote-board.md)
requires an explicit board number, reservation deadline and local Jupyter login.
The helper executes the packaged notebook one stage at a time.

Third-party board definitions and references are documented in [THIRD_PARTY.md](THIRD_PARTY.md).
