#include "../hls/nema_kernel.h"

#include <array>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <string>

namespace {
constexpr const char* kLutPath = "/home/tangodelta/Escritorio/NEMA/artifacts/luts/tanh_q8_8.bin";

inline uint32_t rotr(uint32_t x, uint32_t n) {
    return (x >> n) | (x << (32U - n));
}

void sha256_transform(const uint8_t block[64], uint32_t state[8]) {
    static constexpr uint32_t k[64] = {
        0x428a2f98U, 0x71374491U, 0xb5c0fbcfU, 0xe9b5dba5U, 0x3956c25bU, 0x59f111f1U,
        0x923f82a4U, 0xab1c5ed5U, 0xd807aa98U, 0x12835b01U, 0x243185beU, 0x550c7dc3U,
        0x72be5d74U, 0x80deb1feU, 0x9bdc06a7U, 0xc19bf174U, 0xe49b69c1U, 0xefbe4786U,
        0x0fc19dc6U, 0x240ca1ccU, 0x2de92c6fU, 0x4a7484aaU, 0x5cb0a9dcU, 0x76f988daU,
        0x983e5152U, 0xa831c66dU, 0xb00327c8U, 0xbf597fc7U, 0xc6e00bf3U, 0xd5a79147U,
        0x06ca6351U, 0x14292967U, 0x27b70a85U, 0x2e1b2138U, 0x4d2c6dfcU, 0x53380d13U,
        0x650a7354U, 0x766a0abbU, 0x81c2c92eU, 0x92722c85U, 0xa2bfe8a1U, 0xa81a664bU,
        0xc24b8b70U, 0xc76c51a3U, 0xd192e819U, 0xd6990624U, 0xf40e3585U, 0x106aa070U,
        0x19a4c116U, 0x1e376c08U, 0x2748774cU, 0x34b0bcb5U, 0x391c0cb3U, 0x4ed8aa4aU,
        0x5b9cca4fU, 0x682e6ff3U, 0x748f82eeU, 0x78a5636fU, 0x84c87814U, 0x8cc70208U,
        0x90befffaU, 0xa4506cebU, 0xbef9a3f7U, 0xc67178f2U,
    };

    uint32_t w[64] = {0};
    for (int i = 0; i < 16; ++i) {
        w[i] = (static_cast<uint32_t>(block[i * 4 + 0]) << 24U) |
               (static_cast<uint32_t>(block[i * 4 + 1]) << 16U) |
               (static_cast<uint32_t>(block[i * 4 + 2]) << 8U) |
               (static_cast<uint32_t>(block[i * 4 + 3]));
    }
    for (int i = 16; i < 64; ++i) {
        const uint32_t s0 = rotr(w[i - 15], 7U) ^ rotr(w[i - 15], 18U) ^ (w[i - 15] >> 3U);
        const uint32_t s1 = rotr(w[i - 2], 17U) ^ rotr(w[i - 2], 19U) ^ (w[i - 2] >> 10U);
        w[i] = w[i - 16] + s0 + w[i - 7] + s1;
    }

    uint32_t a = state[0];
    uint32_t b = state[1];
    uint32_t c = state[2];
    uint32_t d = state[3];
    uint32_t e = state[4];
    uint32_t f = state[5];
    uint32_t g = state[6];
    uint32_t h = state[7];
    for (int i = 0; i < 64; ++i) {
        const uint32_t s1 = rotr(e, 6U) ^ rotr(e, 11U) ^ rotr(e, 25U);
        const uint32_t ch = (e & f) ^ ((~e) & g);
        const uint32_t temp1 = h + s1 + ch + k[i] + w[i];
        const uint32_t s0 = rotr(a, 2U) ^ rotr(a, 13U) ^ rotr(a, 22U);
        const uint32_t maj = (a & b) ^ (a & c) ^ (b & c);
        const uint32_t temp2 = s0 + maj;
        h = g;
        g = f;
        f = e;
        e = d + temp1;
        d = c;
        c = b;
        b = a;
        a = temp1 + temp2;
    }

    state[0] += a;
    state[1] += b;
    state[2] += c;
    state[3] += d;
    state[4] += e;
    state[5] += f;
    state[6] += g;
    state[7] += h;
}

std::string sha256_hex(const uint8_t* data, std::size_t len) {
    uint32_t state[8] = {
        0x6a09e667U, 0xbb67ae85U, 0x3c6ef372U, 0xa54ff53aU,
        0x510e527fU, 0x9b05688cU, 0x1f83d9abU, 0x5be0cd19U,
    };

    std::size_t full_blocks = len / 64U;
    for (std::size_t i = 0; i < full_blocks; ++i) {
        sha256_transform(data + i * 64U, state);
    }

    uint8_t tail[128] = {0};
    const std::size_t rem = len % 64U;
    for (std::size_t i = 0; i < rem; ++i) {
        tail[i] = data[full_blocks * 64U + i];
    }
    tail[rem] = 0x80U;

    const uint64_t bit_len = static_cast<uint64_t>(len) * 8ULL;
    const bool one_block = rem < 56U;
    const std::size_t len_offset = one_block ? 56U : 120U;
    tail[len_offset + 0] = static_cast<uint8_t>((bit_len >> 56U) & 0xFFU);
    tail[len_offset + 1] = static_cast<uint8_t>((bit_len >> 48U) & 0xFFU);
    tail[len_offset + 2] = static_cast<uint8_t>((bit_len >> 40U) & 0xFFU);
    tail[len_offset + 3] = static_cast<uint8_t>((bit_len >> 32U) & 0xFFU);
    tail[len_offset + 4] = static_cast<uint8_t>((bit_len >> 24U) & 0xFFU);
    tail[len_offset + 5] = static_cast<uint8_t>((bit_len >> 16U) & 0xFFU);
    tail[len_offset + 6] = static_cast<uint8_t>((bit_len >> 8U) & 0xFFU);
    tail[len_offset + 7] = static_cast<uint8_t>((bit_len >> 0U) & 0xFFU);

    sha256_transform(tail, state);
    if (!one_block) {
        sha256_transform(tail + 64U, state);
    }

    std::ostringstream oss;
    oss << std::hex << std::setfill('0');
    for (int i = 0; i < 8; ++i) {
        oss << std::setw(8) << state[i];
    }
    return oss.str();
}

bool load_lut(std::array<int16_t, nema_model::LUT_SIZE>& lut) {
    std::ifstream in(kLutPath, std::ios::binary);
    if (!in) {
        return false;
    }
    std::array<uint8_t, nema_model::LUT_SIZE * 2> raw{};
    in.read(reinterpret_cast<char*>(raw.data()), static_cast<std::streamsize>(raw.size()));
    if (in.gcount() != static_cast<std::streamsize>(raw.size())) {
        return false;
    }
    for (std::size_t i = 0; i < lut.size(); ++i) {
        const uint16_t lo = static_cast<uint16_t>(raw[i * 2 + 0]);
        const uint16_t hi = static_cast<uint16_t>(raw[i * 2 + 1]) << 8U;
        lut[i] = static_cast<int16_t>(lo | hi);
    }
    return true;
}

inline uint64_t uabs64(int64_t value) {
    return value < 0 ? static_cast<uint64_t>(-(value + 1)) + 1ULL : static_cast<uint64_t>(value);
}

inline int64_t round_div_rne_i64(int64_t numerator, int64_t denominator) {
    if (denominator <= 0) {
        return 0;
    }
    const bool negative = numerator < 0;
    const uint64_t den = static_cast<uint64_t>(denominator);
    const uint64_t mag = uabs64(numerator);
    uint64_t q = mag / den;
    const uint64_t r = mag % den;
    const uint64_t twice_r = r * 2ULL;
    if (twice_r > den || (twice_r == den && (q & 1ULL))) {
        ++q;
    }
    return negative ? -static_cast<int64_t>(q) : static_cast<int64_t>(q);
}

inline int32_t sat_accum_i64(int64_t value) {
    if (value > nema_model::ACCUM_MAX) {
        return nema_model::ACCUM_MAX;
    }
    if (value < nema_model::ACCUM_MIN) {
        return nema_model::ACCUM_MIN;
    }
    return static_cast<int32_t>(value);
}

inline int16_t sat_i16_i64(int64_t value) {
    if (value > 32767) {
        return 32767;
    }
    if (value < -32768) {
        return -32768;
    }
    return static_cast<int16_t>(value);
}

inline int32_t sat_add_accum(int32_t a, int32_t b) {
    return sat_accum_i64(static_cast<int64_t>(a) + static_cast<int64_t>(b));
}

inline int32_t quantize_to_accum(int64_t coeff_num, int64_t coeff_den, int32_t input_raw_q8_8) {
    const int64_t prod = coeff_num * static_cast<int64_t>(input_raw_q8_8);
    return sat_accum_i64(round_div_rne_i64(prod, coeff_den));
}

inline int16_t quantize_to_v(int64_t coeff_num, int64_t coeff_den, int32_t input_raw_q8_8) {
    const int64_t prod = coeff_num * static_cast<int64_t>(input_raw_q8_8);
    return sat_i16_i64(round_div_rne_i64(prod, coeff_den));
}

inline int16_t tanh_lookup(const std::array<int16_t, nema_model::LUT_SIZE>& lut, int16_t v_raw) {
    const uint16_t lut_idx =
        static_cast<uint16_t>(static_cast<int32_t>(v_raw) - static_cast<int32_t>(-32768));
    return lut[static_cast<std::size_t>(lut_idx)];
}

void delayed_tick(
    const std::array<int16_t, nema_model::NODE_STORAGE>& v_in,
    std::array<int16_t, nema_model::NODE_STORAGE>& v_out,
    const std::array<int16_t, nema_model::LUT_SIZE>& lut,
    std::array<int16_t, nema_model::NODE_STORAGE * nema_model::DELAY_RING_SIZE>& v_ring,
    std::array<int16_t, nema_model::NODE_STORAGE * nema_model::DELAY_RING_SIZE>& a_ring,
    int& ring_cursor) {
    std::array<int16_t, nema_model::NODE_STORAGE> v_snapshot{};
    std::array<int16_t, nema_model::NODE_STORAGE> a_snapshot{};
    std::array<int32_t, nema_model::NODE_STORAGE> i_chem{};
    std::array<int32_t, nema_model::NODE_STORAGE> i_gap{};

    for (int i = 0; i < nema_model::NODE_COUNT; ++i) {
        v_snapshot[static_cast<std::size_t>(i)] = v_in[static_cast<std::size_t>(i)];
        a_snapshot[static_cast<std::size_t>(i)] = tanh_lookup(lut, v_snapshot[static_cast<std::size_t>(i)]);
        i_chem[static_cast<std::size_t>(i)] = 0;
        i_gap[static_cast<std::size_t>(i)] = 0;
    }

    for (int post = 0; post < nema_model::NODE_COUNT; ++post) {
        const int begin = static_cast<int>(nema_model::CHEM_ROW_PTR[post]);
        const int end = static_cast<int>(nema_model::CHEM_ROW_PTR[post + 1]);
        for (int edge = begin; edge < end; ++edge) {
            const int pre = static_cast<int>(nema_model::CHEM_PRE_IDX[edge]);
            const int delay = static_cast<int>(nema_model::CHEM_DELAY_TICKS[edge]);
            int32_t pre_out = static_cast<int32_t>(a_snapshot[static_cast<std::size_t>(pre)]);
            if (delay > 0) {
                const int slot =
                    (ring_cursor - delay + nema_model::DELAY_RING_SIZE) % nema_model::DELAY_RING_SIZE;
                const std::size_t ring_index =
                    static_cast<std::size_t>(slot * nema_model::NODE_STORAGE + pre);
                pre_out = static_cast<int32_t>(a_ring[ring_index]);
            }
            const int32_t msg = quantize_to_accum(
                nema_model::CHEM_WEIGHT_NUM[edge],
                nema_model::CHEM_WEIGHT_DEN[edge],
                pre_out);
            i_chem[static_cast<std::size_t>(post)] =
                sat_add_accum(i_chem[static_cast<std::size_t>(post)], msg);
        }
    }

    for (int edge = 0; edge < nema_model::GAP_EDGE_COUNT; ++edge) {
        const int a = static_cast<int>(nema_model::GAP_A_IDX[edge]);
        const int b = static_cast<int>(nema_model::GAP_B_IDX[edge]);
        const int delay = static_cast<int>(nema_model::GAP_DELAY_TICKS[edge]);
        int32_t va = static_cast<int32_t>(v_snapshot[static_cast<std::size_t>(a)]);
        int32_t vb = static_cast<int32_t>(v_snapshot[static_cast<std::size_t>(b)]);
        if (delay > 0) {
            const int slot =
                (ring_cursor - delay + nema_model::DELAY_RING_SIZE) % nema_model::DELAY_RING_SIZE;
            const std::size_t a_ring_index =
                static_cast<std::size_t>(slot * nema_model::NODE_STORAGE + a);
            const std::size_t b_ring_index =
                static_cast<std::size_t>(slot * nema_model::NODE_STORAGE + b);
            va = static_cast<int32_t>(v_ring[a_ring_index]);
            vb = static_cast<int32_t>(v_ring[b_ring_index]);
        }
        const int32_t dv = vb - va;
        const int32_t msg = quantize_to_accum(
            nema_model::GAP_CONDUCTANCE_NUM[edge],
            nema_model::GAP_CONDUCTANCE_DEN[edge],
            dv);
        i_gap[static_cast<std::size_t>(a)] = sat_add_accum(i_gap[static_cast<std::size_t>(a)], msg);
        i_gap[static_cast<std::size_t>(b)] = sat_add_accum(i_gap[static_cast<std::size_t>(b)], -msg);
    }

    for (int i = 0; i < nema_model::NODE_COUNT; ++i) {
        const int32_t total_i =
            sat_add_accum(i_chem[static_cast<std::size_t>(i)], i_gap[static_cast<std::size_t>(i)]);
        const int16_t delta_v = quantize_to_v(
            nema_model::INV_TAU_NUM[i],
            nema_model::INV_TAU_DEN[i],
            total_i);
        v_out[static_cast<std::size_t>(i)] = sat_i16_i64(
            static_cast<int64_t>(v_snapshot[static_cast<std::size_t>(i)]) +
            static_cast<int64_t>(delta_v));
    }

    for (int i = 0; i < nema_model::NODE_COUNT; ++i) {
        const std::size_t ring_index =
            static_cast<std::size_t>(ring_cursor * nema_model::NODE_STORAGE + i);
        v_ring[ring_index] = v_snapshot[static_cast<std::size_t>(i)];
        a_ring[ring_index] = a_snapshot[static_cast<std::size_t>(i)];
    }
    ring_cursor = (ring_cursor + 1) % nema_model::DELAY_RING_SIZE;
}
}  // namespace

int main(int argc, char** argv) {
    int ticks = 8;
    if (argc > 1) {
        ticks = std::atoi(argv[1]);
    }
    if (ticks < 0) {
        std::cerr << "ticks must be >= 0\n";
        return 2;
    }

    std::array<int16_t, nema_model::LUT_SIZE> lut{};
    if (!load_lut(lut)) {
        std::cerr << "failed to load LUT from " << kLutPath << "\n";
        return 3;
    }

    std::array<int16_t, nema_model::NODE_STORAGE> v_cur{};
    std::array<int16_t, nema_model::NODE_STORAGE> v_next{};
    for (int i = 0; i < nema_model::NODE_COUNT; ++i) {
        v_cur[static_cast<std::size_t>(i)] = nema_model::V_INIT[static_cast<std::size_t>(i)];
    }

    std::array<uint8_t, nema_model::NODE_STORAGE * 2> packed{};
    std::cout << "{\"ticks\":" << ticks << ",\"tickDigestsSha256\":[";
    for (int tick = 0; tick < ticks; ++tick) {
        nema_kernel(v_cur.data(), lut.data(), v_next.data());
        v_cur = v_next;

        for (int i = 0; i < nema_model::NODE_COUNT; ++i) {
            const uint16_t bits = static_cast<uint16_t>(v_cur[static_cast<std::size_t>(i)]);
            packed[static_cast<std::size_t>(i * 2 + 0)] = static_cast<uint8_t>(bits & 0xFFU);
            packed[static_cast<std::size_t>(i * 2 + 1)] = static_cast<uint8_t>((bits >> 8U) & 0xFFU);
        }
        const std::string digest = sha256_hex(
            packed.data(),
            static_cast<std::size_t>(nema_model::NODE_COUNT) * 2U);
        if (tick > 0) {
            std::cout << ",";
        }
        std::cout << "\"" << digest << "\"";
    }
    std::cout << "]}\n";
    return 0;
}
