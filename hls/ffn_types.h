#pragma once
#include "ap_int.h"

#ifndef FFN_P
#define FFN_P 1
#endif
#ifndef FFN_Q
#define FFN_Q 1
#endif
#ifndef FFN_PIPELINE
#define FFN_PIPELINE 1
#endif
#ifndef FFN_LAYOUT
// 0 banked, 1 unpartitioned, 2 packed.
#define FFN_LAYOUT 0
#endif
#define FFN_PRAGMA_INNER(x) _Pragma(#x)
#define FFN_PRAGMA(x) FFN_PRAGMA_INNER(x)

typedef ap_int<16> data_t;
typedef ap_int<32> product_t;
typedef ap_int<40> acc_t;
typedef ap_uint<64> word_t;
#if FFN_LAYOUT == 2
typedef word_t weight_t;
#define FFN_COLS(n) ((n)/4)
static_assert(FFN_Q == 4, "Packed organization requires Q=4");
#else
typedef data_t weight_t;
#define FFN_COLS(n) (n)
#endif
static_assert(FFN_P==1 || FFN_P==2 || FFN_P==4, "Invalid P");
static_assert(FFN_Q==1 || FFN_Q==2 || FFN_Q==4, "Invalid Q");
static const int PARAM_WORDS=4144;
static const int VECTOR_WORDS=16;
int ffn(const word_t *parameters, const word_t *input, word_t *output, unsigned operation);

inline data_t signed_lane(word_t word, int lane) {
#pragma HLS INLINE
    data_t value;
    value.range(15,0)=word.range(lane*16+15,lane*16);
    return value;
}

inline data_t quantize(acc_t value, bool relu) {
#pragma HLS INLINE
    if (relu && value < 0) value=0;
    acc_t rounded;
    if (value >= 0) rounded=(value+acc_t(512)) >> 10;
    else rounded=-(((-value)+acc_t(512)) >> 10);
    if (rounded > 32767) return data_t(32767);
    if (rounded < -32768) return data_t(-32768);
    return data_t(rounded);
}
