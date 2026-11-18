#include "dense.h"

template<int NIN,int NOUT>
void load_layer(const word_t *parameters, int word_offset,
                weight_t weights[NOUT][FFN_COLS(NIN)], data_t bias[NOUT]) {
#pragma HLS INLINE off
LOAD_ROWS: for (int i=0;i<NOUT;++i) {
#pragma HLS PIPELINE off
    LOAD_WORDS: for (int j=0;j<NIN/4;++j) {
#pragma HLS PIPELINE off
        word_t word=parameters[word_offset+i*(NIN/4)+j];
#if FFN_LAYOUT == 2
        weights[i][j]=word;
#else
        SCATTER: for (int lane=0;lane<4;++lane) {
#pragma HLS PIPELINE off
            weights[i][4*j+lane]=signed_lane(word,lane);
        }
#endif
    }
}
LOAD_BIAS: for (int i=0;i<NOUT/4;++i) {
#pragma HLS PIPELINE II=1
    word_t word=parameters[word_offset+NOUT*NIN/4+i];
    BIAS_LANES: for (int lane=0;lane<4;++lane) {
#pragma HLS UNROLL
        bias[4*i+lane]=signed_lane(word,lane);
    }
}
}

void ffn_compute(weight_t w1[128][FFN_COLS(64)], data_t b1[128],
                 weight_t w2[64][FFN_COLS(128)], data_t b2[64],
                 data_t input[64], data_t output[64]) {
#pragma HLS INLINE off
    data_t hidden[128];
#pragma HLS ARRAY_PARTITION variable=hidden complete
    dense<64,128,true>(w1,b1,input,hidden);
    dense<128,64,false>(w2,b2,hidden,output);
}

int ffn(const word_t *parameters, const word_t *input, word_t *output, unsigned operation) {
#pragma HLS INTERFACE m_axi port=parameters offset=slave bundle=gmem depth=4144
#pragma HLS INTERFACE m_axi port=input offset=slave bundle=gmem depth=16
#pragma HLS INTERFACE m_axi port=output offset=slave bundle=gmem depth=16
#pragma HLS INTERFACE s_axilite port=parameters bundle=control
#pragma HLS INTERFACE s_axilite port=input bundle=control
#pragma HLS INTERFACE s_axilite port=output bundle=control
#pragma HLS INTERFACE s_axilite port=operation bundle=control
#pragma HLS INTERFACE s_axilite port=return bundle=control
    static weight_t w1[128][FFN_COLS(64)], w2[64][FFN_COLS(128)];
    static data_t b1[128],b2[64];
    static bool parameters_ready=false;
#pragma HLS RESET variable=parameters_ready
#pragma HLS RESET variable=w1 off
#pragma HLS RESET variable=w2 off
#pragma HLS RESET variable=b1 off
#pragma HLS RESET variable=b2 off
#pragma HLS BIND_STORAGE variable=w1 type=ram_1p impl=bram
#pragma HLS BIND_STORAGE variable=w2 type=ram_1p impl=bram
#pragma HLS ARRAY_PARTITION variable=b1 complete
#pragma HLS ARRAY_PARTITION variable=b2 complete
#if FFN_LAYOUT != 1 && FFN_P > 1
FFN_PRAGMA(HLS ARRAY_PARTITION variable=w1 cyclic factor=FFN_P dim=1)
FFN_PRAGMA(HLS ARRAY_PARTITION variable=w2 cyclic factor=FFN_P dim=1)
#endif
#if FFN_LAYOUT == 0 && FFN_Q > 1
FFN_PRAGMA(HLS ARRAY_PARTITION variable=w1 cyclic factor=FFN_Q dim=2)
FFN_PRAGMA(HLS ARRAY_PARTITION variable=w2 cyclic factor=FFN_Q dim=2)
#endif
    if (operation==0) {
        parameters_ready=false;
        load_layer<64,128>(parameters,0,w1,b1);
        load_layer<128,64>(parameters,2080,w2,b2);
        parameters_ready=true;
        return 0;
    }
    if (operation!=1) return 2;
    if (!parameters_ready) return 1;
    data_t x[64],z[64];
#pragma HLS ARRAY_PARTITION variable=x complete
#pragma HLS ARRAY_PARTITION variable=z complete
READ_INPUT: for (int i=0;i<16;++i) {
#pragma HLS PIPELINE II=1
    word_t word=input[i];
    READ_LANES: for (int q=0;q<4;++q) {
#pragma HLS UNROLL
        x[4*i+q]=signed_lane(word,q);
    }
}
    ffn_compute(w1,b1,w2,b2,x,z);
WRITE_OUTPUT: for (int i=0;i<16;++i) {
#pragma HLS PIPELINE II=1
    word_t word=0;
    WRITE_LANES: for (int q=0;q<4;++q) {
#pragma HLS UNROLL
        word.range(16*q+15,16*q)=z[4*i+q].range(15,0);
    }
    output[i]=word;
}
    return 0;
}
