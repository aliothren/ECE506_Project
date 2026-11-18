# Third-party inputs

The PYNQ-Z2 board definition under `vivado/board_files/pynq-z2/A.0/` was
obtained from the official XilinxBoardStore TUL/PYNQ-Z2 directory, as recorded
in its `SOURCE.txt`: https://github.com/Xilinx/XilinxBoardStore/tree/master/boards/TUL/pynq-z2/A.0.
Its original XML and image contents are preserved. It supplies the board preset
used by `vivado/build.tcl`.
The upstream copyright/license notice is preserved as `LICENSE.upstream` in
that directory, alongside the full Apache 2.0 text in `LICENSE-2.0.txt`.
These notices apply to the upstream board files, not as a project-wide license.

Vitis HLS, Vivado, PYNQ, NumPy, Matplotlib, Requests, and websocket-client are
external dependencies. Vendor tool installations and generated simulation/build
projects are not included in this repository. The two small deployment archives
contain the exact generated bitstream/HWH pairs and project host files used in
the board experiment; their build and measurement provenance is recorded under
`results/`.

The project report cites Cilardo and Gallo (DATE 2015) and FINN-R (2018) as related
work. Their papers are linked in the report rather than redistributed here.
