#pragma once
#include "ffn_types.h"

template<int NIN, int NOUT, bool RELU>
void dense(weight_t weights[NOUT][FFN_COLS(NIN)], data_t bias[NOUT],
           data_t input[NIN], data_t output[NOUT]) {
#pragma HLS INLINE off
#pragma HLS ARRAY_PARTITION variable=bias complete
#pragma HLS ARRAY_PARTITION variable=input complete
#pragma HLS ARRAY_PARTITION variable=output complete
OUTPUT_GROUP: for (int ob=0;ob<NOUT;ob+=FFN_P) {
#pragma HLS PIPELINE off
#pragma HLS LOOP_FLATTEN off
        acc_t partial[FFN_P][FFN_Q];
#pragma HLS ARRAY_PARTITION variable=partial complete dim=0
    INIT_P: for (int p=0;p<FFN_P;++p) {
#pragma HLS UNROLL
        INIT_Q: for (int q=0;q<FFN_Q;++q) {
#pragma HLS UNROLL
            partial[p][q]=0;
        }
    }
    INPUT_GROUP: for (int ib=0;ib<NIN;ib+=FFN_Q) {
#if FFN_PIPELINE
#pragma HLS PIPELINE II=1
#else
#pragma HLS PIPELINE off
#endif
        OUTPUT_LANE: for (int p=0;p<FFN_P;++p) {
#pragma HLS UNROLL
#if FFN_LAYOUT == 2
            word_t packed=weights[ob+p][ib/4];
#endif
            INPUT_LANE: for (int q=0;q<FFN_Q;++q) {
#pragma HLS UNROLL
#if FFN_LAYOUT == 2
                data_t w=signed_lane(packed,q);
#else
                data_t w=weights[ob+p][ib+q];
#endif
                product_t product=w*input[ib+q];
                partial[p][q] += acc_t(product);
            }
        }
    }
    FINISH_P: for (int p=0;p<FFN_P;++p) {
#pragma HLS UNROLL
        acc_t total=0;
        FINISH_Q: for (int q=0;q<FFN_Q;++q) {
#pragma HLS UNROLL
            total += partial[p][q];
        }
        total += acc_t(bias[ob+p])*acc_t(1024);
        output[ob+p]=quantize(total,RELU);
    }
}
}
