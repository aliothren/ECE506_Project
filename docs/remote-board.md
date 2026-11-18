# Optional staged remote helper

The main procedure is the notebook in [board/README.md](../board/README.md).
`scripts/run_board.py` automates **one stage per invocation** through an existing
local Jupyter tunnel. It does not establish SSH/VPN or reserve a board. The
helper executes the notebook from the selected deployment archive.

Install `requirements-remote.txt` on the workstation. Use the course's current
connection instructions to expose the assigned board's Jupyter on localhost
port `9090 + board number` (9092 for board 2). Keep it bound to localhost.
The remote hostname must be `pynq1`, `pynq2` or `pynq3`, matching `--board`.

Each command requires a configuration, board, reservation deadline with UTC
offset, and a unique run ID. Reuse exactly these values for subsequent stages.
Substitute your actual authorized deadline for `YOUR_DEADLINE`:

```bash
python scripts/run_board.py setup --config B11 --board 2 \
  --reservation-end YOUR_DEADLINE --run-id my-reservation
```

The deadline format is `YYYY-MM-DDTHH:MM:SS-07:00` for Arizona time. Expired
deadlines are rejected before network access. The password is requested privately
in an interactive terminal; unattended callers must supply `PYNQ_PASSWORD`
locally. No password is embedded, logged or saved in the repository.

After setup, invoke these actions **individually**, checking each result:
`preflight`, `program`, `control`, `buffers`, `smoke`, `validate`, `benchmark`,
`close`, `cpu`, `files`, then `finish`. Do not put them in an unattended loop.
Close B11 normally before starting K44 in a new kernel.

`collect` downloads available evidence without launching another notebook cell.
`finish` requires a normal close before stopping this run's kernel. Outputs go
to ignored `results/board_runs/RUN_ID/CONFIG/`, separate from published records.
The result collector targets the November 18 experiment; analyze new
sessions separately.

A failed or uncertain stage blocks relaunch. Preserve the state file and kernel
and follow the board recovery procedure. The helper reserves a time margin for
saving, but cannot guarantee completion of stalled MMIO.
