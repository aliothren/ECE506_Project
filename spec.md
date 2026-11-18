**FFN specification, revision 1**

All configurations compute 64→128→64, with ReLU only at the first layer.
Signed int16 values represent raw/1024. A dot product uses exact signed
products and a 40-bit accumulator; bias is added as `int64(bias)*1024`.
First apply ReLU where applicable, then divide by 1024, round to nearest
(ties away from zero), and saturate to [-32768,32767]. No intermediate
rounding or saturation occurs inside a dot product.

The canonical parameter file is little-endian int16, row-major:

| Array | int16 offset | Elements |
|---|---:|---:|
| W1[128][64] | 0 | 8192 |
| b1[128] | 8192 | 128 |
| W2[64][128] | 8320 | 8192 |
| b2[64] | 16512 | 64 |

Total 16576 int16 elements = 33152 bytes = 4144 uint64 words.
Each uint64 word holds four raw int16 bit patterns, first element in bits 15:0.
An input/output is 64 int16 elements = 128 bytes = 16 uint64 words.

Top: `int ffn(const word_t *parameters, const word_t *input, word_t *output, unsigned operation)`.
All data ports share a 64-bit m_axi `gmem` bundle; controls use AXI-Lite `control`.
Operation 0 loads all parameters; operation 1 runs one inference.
Return status: 0 success, 1 RUN before LOAD, 2 unsupported operation.
Error operations do not write the output. LOAD and RUN cannot overlap.
Hardware reset clears the parameter-valid flag; reload parameters after reset
or downloading an overlay. Each RUN resets its own accumulators.

Weights use RAM_1P BRAM. Banked configurations partition both matrix dimensions
by P and Q. U44 has no weight partitioning. K44 stores four adjacent signed
weights per 64-bit word, with four output banks. Short vectors and partial
sums are fully partitioned. Both layers have distinct hardware instances and
execute sequentially. Arithmetic and the external interface are identical.

The board target is xc7z020clg400-1 at 100 MHz, Vitis/Vivado 2025.1.
S00 disables the compute pipeline. All other configurations request II=1;
actual II must be read from synthesis. Weight loading is an initialization
cost, not part of inference timing. `ffn_compute` excludes DDR transfers but
includes both layers, reduction, activation and quantization.
