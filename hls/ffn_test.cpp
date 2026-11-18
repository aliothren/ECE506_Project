#include "ffn_types.h"
#include "../reference/fixtures.h"
#include <iostream>

static void pack(const int16_t *in, word_t *out, int count) {
    for (int i=0;i<count/4;++i) {
        word_t word=0;
        for (int j=0;j<4;++j) word.range(16*j+15,16*j)=ap_uint<16>(in[4*i+j]);
        out[i]=word;
    }
}

int main(int argc,char **argv) try {
    if (argc<2) throw std::runtime_error("Usage: test DATA_DIR [rtl]");
    std::string root=argv[1]; bool rtl=argc>2;
    word_t params[PARAM_WORDS]={}, input[VECTOR_WORDS]={},output[VECTOR_WORDS];
    for (int i=0;i<VECTOR_WORDS;++i) output[i]=word_t(0x123456789abcdef0ULL);
    if (ffn(params,input,output,1)!=1 || ffn(params,input,output,99)!=2)
        throw std::runtime_error("Missing operation/state guard");
    for (int i=0;i<VECTOR_WORDS;++i)
        if (output[i]!=word_t(0x123456789abcdef0ULL)) throw std::runtime_error("Error wrote output");
    std::ifstream index(root+"/index.txt");
    if (!index) throw std::runtime_error("Cannot open index");
    std::string name; int count,total=0,models=0;
    while (index>>name>>count) {
        // RTL keeps two random models plus full-range and signed rounding cases.
        if (rtl && name!="random_506" && name!="random_507" && name!="extremes" && name!="rounding") continue;
        auto p=read_i16(root+"/"+name+"/params.bin",16576);
        auto x=read_i16(root+"/"+name+"/input.bin",count*64);
        auto gold=read_i16(root+"/"+name+"/output.bin",count*64);
        pack(p.data(),params,16576);
        if (ffn(params,input,output,0)!=0) throw std::runtime_error("LOAD failed");
        int runs=rtl ? std::min(count,2) : count;
        for (int n=0;n<runs;++n) {
            pack(x.data()+n*64,input,64);
            if (ffn(params,input,output,1)!=0) throw std::runtime_error("RUN failed");
            for (int i=0;i<64;++i) {
                int actual=signed_lane(output[i/4],i%4).to_int();
                if (actual!=gold[n*64+i]) {
                    std::cerr<<name<<" n="<<n<<" i="<<i<<" expected="<<gold[n*64+i]<<" actual="<<actual<<'\n';
                    throw std::runtime_error("Output mismatch");
                }
            }
            ++total;
        }
        ++models;
    }
    if (!total) throw std::runtime_error("No tests executed");
    std::cout<<"FFN_TEST_PASS P="<<FFN_P<<" Q="<<FFN_Q<<" layout="<<FFN_LAYOUT
             <<" models="<<models<<" inferences="<<total<<" mode="<<(rtl?"rtl":"full")<<'\n';
    return 0;
} catch (const std::exception &e) { std::cerr<<e.what()<<'\n'; return 1; }
