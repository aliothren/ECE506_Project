#include "fixtures.h"
#include <algorithm>
#include <chrono>
#include <iostream>
#include <iomanip>

static int16_t quantize(int64_t a, bool relu) {
    if (relu && a < 0) a = 0;
    int64_t q = a >= 0 ? (a+512)/1024 : -((-a+512)/1024);
    return static_cast<int16_t>(std::max<int64_t>(-32768, std::min<int64_t>(32767,q)));
}

// Kept out of line to make the benchmark's computation observable and repeatable.
__attribute__((noinline)) void ffn_cpu(const int16_t *p, const int16_t *x,
                                     int16_t *h, int16_t *z) {
    for (int i=0; i<128; ++i) {
        int64_t sum = int64_t(p[8192+i])*1024;
        for (int j=0; j<64; ++j) sum += int64_t(p[i*64+j])*x[j];
        h[i] = quantize(sum, true);
    }
    for (int i=0; i<64; ++i) {
        int64_t sum = int64_t(p[16512+i])*1024;
        for (int j=0; j<128; ++j) sum += int64_t(p[8320+i*128+j])*h[j];
        z[i] = quantize(sum, false);
    }
}

int main(int argc, char **argv) try {
    if (argc < 2) throw std::runtime_error("Usage: ffn_cpu DATA_DIR [benchmark_output.csv]");
    const std::string root=argv[1];
    std::ifstream index(root+"/index.txt");
    if (!index) throw std::runtime_error("Missing index");
    std::string name; int count, total=0;
    int16_t h[128], z[64];
    while (index >> name >> count) {
        auto p=read_i16(root+"/"+name+"/params.bin",16576);
        auto x=read_i16(root+"/"+name+"/input.bin",count*64);
        auto gh=read_i16(root+"/"+name+"/hidden.bin",count*128);
        auto gz=read_i16(root+"/"+name+"/output.bin",count*64);
        for (int n=0; n<count; ++n) {
            ffn_cpu(p.data(),x.data()+n*64,h,z);
            if (!std::equal(h,h+128,gh.data()+n*128) || !std::equal(z,z+64,gz.data()+n*64))
                throw std::runtime_error("Mismatch " + name + " input " + std::to_string(n));
            ++total;
        }
    }
    if (total==0) throw std::runtime_error("Empty fixture index");
    std::cout << "CPU_REFERENCE_PASS: " << total << " inferences, both layers\n";
    if (argc > 2) {
        auto p=read_i16(root+"/random_506/params.bin",16576);
        auto x=read_i16(root+"/random_506/input.bin",64*64);
        auto golden=read_i16(root+"/random_506/output.bin",64*64);
        for (int i=0;i<20;++i) ffn_cpu(p.data(),x.data()+(i%64)*64,h,z);
        std::ofstream out(argv[2]);
        if (!out) throw std::runtime_error("Cannot write benchmark CSV");
        out << "round,iteration,input_index,elapsed_ns,correct\n";
        uint64_t checksum=0;
        for (int r=0;r<3;++r) for (int i=0;i<1000;++i) {
            int idx=i%64;
            auto start=std::chrono::steady_clock::now();
            ffn_cpu(p.data(),x.data()+idx*64,h,z);
            auto stop=std::chrono::steady_clock::now();
            bool correct=std::equal(z,z+64,golden.data()+idx*64);
            if (!correct) throw std::runtime_error("Benchmark mismatch");
            for (int v:z) checksum += static_cast<uint16_t>(v);
            out << r << ',' << i << ',' << idx << ','
                << std::chrono::duration_cast<std::chrono::nanoseconds>(stop-start).count()
                << ",1\n";
        }
        std::cout << "CPU_BENCHMARK_PASS checksum=" << checksum << '\n';
    }
    return 0;
} catch (const std::exception &e) {
    std::cerr << e.what() << '\n';
    return 1;
}
