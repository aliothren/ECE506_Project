#pragma once
#include <cstdint>
#include <fstream>
#include <stdexcept>
#include <string>
#include <vector>

inline std::vector<int16_t> read_i16(const std::string &path, size_t expected) {
    std::ifstream f(path, std::ios::binary);
    if (!f) throw std::runtime_error("Cannot open " + path);
    std::vector<unsigned char> bytes(expected*2);
    f.read(reinterpret_cast<char*>(bytes.data()), bytes.size());
    if (static_cast<size_t>(f.gcount()) != bytes.size() || f.peek() != EOF)
        throw std::runtime_error("Wrong length " + path);
    std::vector<int16_t> out(expected);
    for (size_t i=0; i<expected; ++i) {
        int u = bytes[2*i] | (int(bytes[2*i+1])<<8);
        out[i] = static_cast<int16_t>(u >= 32768 ? u-65536 : u);
    }
    return out;
}
