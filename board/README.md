# FFN board operation

Use the B11 and K44 archives listed in `deploy/README.md`. The design is
for the course **PYNQ-Z2 / XC7Z020**, using its existing PYNQ Linux image. It has
passed local simulation, implementation, and physical-board validation on
November 18, 2026.
Start with B11. Run K44 only after B11 passes and its session closes normally.

## Before the reserved board session

Upload and extract the entire archive to a writable Jupyter directory. Keep
`ffn.bit` and `ffn.hwh` together with the notebook, Python files, `manifest.json`,
`data/`, `reference/`, and `audit/`. Use the assigned PYNQ-Z2 reservation and the
course VPN/tunnel. Do not run `ps7_init`, change DDR setup, replace the SD image,
or alter the board's network configuration. The running PYNQ image owns PS/DDR.
The CPU check needs the board's `g++` with C++17 support; the notebook needs NumPy
and PYNQ with `allocate`, `MMIO`, `Overlay`, and `Clocks` (the `allocate` API is
available in PYNQ 2.5+). The tested image used PYNQ 2.5, Python 3.6.5 and NumPy
1.13.3; check the environment again for a new reservation.

## Execute `ffn_board.ipynb` one cell at a time

Do not use **Run All** for the first session. Stop on any exception or unexpected
output. The stages are:

1. `FFNSession('.')`: read-only package integrity, part, timing, HWH wiring and
   fixture checks. No PYNQ import, FPGA download, allocation, or MMIO.
2. `session.program()`: take the cooperative board lock, check platform/manager,
   parse metadata, program, and check the 100 MHz clock. No FFN-register access.
3. `session.check_control()`: the first explicit PL read, reset register values,
   invalid operation, and RUN-before-LOAD guards. Both guards must return without
   accessing DDR. They are tested against the actual synthesized RTL locally.
4. `session.allocate_buffers()`: allocate nonoverlapping, cache-line-aligned
   buffers inside the 512 MiB HP0 DDR window; initialize and flush all three.
5. `session.smoke()`: one parameter load and one known inference.
6. `session.validate()`: all 206 inferences with all nine parameter sets.
7. `session.benchmark()`: 20 warm-ups and 3 × 1000 measured calls, checking every
   output outside the timed interval. LOAD time is separate.
8. `session.close()`: recheck idle, release buffers, clear ownership normally.
9. `python3 run_cpu.py`: compile and validate both CPU layers; collect the same
   3 × 1000 workload on the board CPU, with compiler/frequency metadata.

Notebook cells keep these operations separate. Save/download `load_stages.jsonl`,
`board_validation.json`, `board_raw.csv`, `board_results.json`, `cpu_run.log`,
`cpu_raw.csv`, and `cpu_results.json` with the configuration's manifest.
A normal B11 close allows K44 to be programmed in the same board boot. Use a new
notebook kernel for the second package **only after a successful close** so Python
cannot reuse the first directory's imported modules. Do not run two board sessions
or another overlay application concurrently.

## Stop/recovery behavior

A timeout, interrupt during MMIO, wrong return status, or incorrect output poisons
the session. Further calls, normal close/free, and another session are blocked.
A module-owned strong reference retains the session and buffers even if a notebook
variable is overwritten. An OS file lock prevents cooperating processes from
programming simultaneously; `/tmp/ece506_ffn.state.json` records an unclosed session
across kernel restarts. Do not delete or bypass this marker. A clean physical
board reboot changes the boot ID and permits a new session.

**A Python timeout cannot interrupt a stalled memory-mapped bus transaction.**
If a cell hangs, do not repeatedly interrupt, rerun download, restart Jupyter,
free buffers, or clear the guard file. Preserve the latest stage log and arrange
board recovery with the course staff. After recovery, start from preflight. These
protections reduce known risks but do not prove that a physical board cannot hang.
An allocation failure before launch permits `session.close()`; uncertain MMIO does
not. The locks only coordinate this runner, not unrelated PYNQ programs.

## Measurement boundaries

FPGA host timing includes copying the packed input into its DMA buffer, flush,
register writes, polling until both completion and idle have been observed, return status, output invalidate and copy. Python input
shape/type checks, parameter LOAD, output comparison, CSV/log I/O and programming
are outside this interval. Durable logs are written at stage boundaries, not for
each measured inference. CPU timing measures only the compiled C++ computation on
resident arrays, excluding file I/O/validation. Report these distinct boundaries;
do not label HLS cycles or local x86 CPU timings as board latency. The completed
experiment measured a 1.14x B11/K44 host speedup; K44's host path took 6.75x the
corresponding CPU computation time.

The package manifest binds the local control tests to this exact bit/HWH pair. The
RTL test covers the generated FFN, vendor reset controller and a bounded, stalling
AXI memory model. It does not simulate PS7, SmartConnect, Linux, or CPU caches.

PYNQ API references: [Overlay](https://pynq.readthedocs.io/en/v2.7.0/pynq_libraries/overlay.html),
[MMIO](https://github.com/Xilinx/PYNQ/blob/master/docs/source/overlay_design_methodology/pspl_interface.rst),
[buffer synchronization](https://pynq.readthedocs.io/en/v2.6.1/pynq_libraries/allocate.html).


The host uses filename strings for NumPy input and latches the clear-on-read
completion flag while waiting for the independently registered idle flag.
