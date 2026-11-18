# FFN deployment packages

B11 and K44 target PYNQ-Z2 / XC7Z020 at 100 MHz. Both designs pass 206 correctness
cases and 3,000 measured inferences on the board.

- [B11_20261118T204214272606Z_release1.zip](B11_20261118T204214272606Z_release1.zip): SHA-256 `d1e2202371d6315c6cf08de43c59fa6909e5f1dc00f298e5c21c97e9cb47c221`
- [K44_20261118T205854106482Z_release1.zip](K44_20261118T205854106482Z_release1.zip): SHA-256 `89971668b74ec4b6b6a59fabad219bd918ce89604f39674e1cabb11bfec9469a`

Each package includes the bitstream/HWH pair, staged notebook, host, reference
implementation, deterministic data, and integration-verification records.
The bitstream, runtime source, fixtures, and notebook code match those used in
the board measurements. This correspondence is checked by
`scripts/collect_board_results.py` and recorded in
[board_results.json](../results/board_results.json).

Follow [board/README.md](../board/README.md) for operation. See
[board results](../results/BOARD_RESULTS.md) and the [report](../report/ffn_report.tex)
for the measurement protocol and analysis.
