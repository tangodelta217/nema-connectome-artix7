#pragma once

#include "nema_kernel.h"

#include <array>
#include <algorithm>
#include <cstddef>
#include <cctype>
#include <cstdint>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

namespace nema_tb {

inline std::string trim_copy(std::string value) {
    auto not_space = [](unsigned char ch) { return !std::isspace(ch); };
    value.erase(value.begin(), std::find_if(value.begin(), value.end(), not_space));
    value.erase(std::find_if(value.rbegin(), value.rend(), not_space).base(), value.end());
    return value;
}

inline uint32_t rotr(uint32_t x, uint32_t n) {
    return (x >> n) | (x << (32U - n));
}

inline void sha256_transform(const uint8_t block[64], uint32_t state[8]) {
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

inline std::string sha256_hex(const uint8_t* data, std::size_t len) {
    uint32_t state[8] = {
        0x6a09e667U, 0xbb67ae85U, 0x3c6ef372U, 0xa54ff53aU,
        0x510e527fU, 0x9b05688cU, 0x1f83d9abU, 0x5be0cd19U,
    };

    const std::size_t full_blocks = len / 64U;
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

inline std::vector<std::string> candidate_lut_paths() {
    std::vector<std::string> out;
    const char* env = std::getenv("NEMA_LUT_PATH");
    if (env != nullptr && env[0] != '\0') {
        out.emplace_back(env);
    }
    namespace fs = std::filesystem;
    fs::path base = fs::current_path();
    for (int i = 0; i < 16; ++i) {
        fs::path p = base / "artifacts" / "luts" / "tanh_q8_8.bin";
        out.emplace_back(p.string());
        if (!base.has_parent_path()) {
            break;
        }
        base = base.parent_path();
    }
    return out;
}

inline bool load_lut(std::array<int16_t, nema_model::LUT_SIZE>& lut, std::string* used_path) {
    for (const std::string& candidate : candidate_lut_paths()) {
        std::ifstream in(candidate, std::ios::binary);
        if (!in) {
            continue;
        }
        std::array<uint8_t, nema_model::LUT_SIZE * 2> raw{};
        in.read(reinterpret_cast<char*>(raw.data()), static_cast<std::streamsize>(raw.size()));
        if (in.gcount() != static_cast<std::streamsize>(raw.size())) {
            continue;
        }
        for (std::size_t i = 0; i < lut.size(); ++i) {
            const uint16_t lo = static_cast<uint16_t>(raw[i * 2 + 0]);
            const uint16_t hi = static_cast<uint16_t>(raw[i * 2 + 1]) << 8U;
            lut[i] = static_cast<int16_t>(lo | hi);
        }
        if (used_path != nullptr) {
            *used_path = candidate;
        }
        return true;
    }
    return false;
}

inline std::string resolve_bench_id(const char* fallback_id) {
    const char* env = std::getenv("NEMA_BENCH_ID");
    if (env != nullptr && env[0] != '\0') {
        return std::string(env);
    }
    return std::string(fallback_id);
}

inline bool is_hex_digest(const std::string& token) {
    if (token.size() != 64) {
        return false;
    }
    for (char ch : token) {
        const bool ok = (ch >= '0' && ch <= '9') || (ch >= 'a' && ch <= 'f');
        if (!ok) {
            return false;
        }
    }
    return true;
}

inline bool load_expected_digests_from_env(std::vector<std::string>* out, std::string* source, std::string* error) {
    if (out == nullptr) {
        if (error != nullptr) {
            *error = "internal error: null output vector";
        }
        return false;
    }
    out->clear();
    const char* env = std::getenv("NEMA_EXPECTED_DIGESTS_FILE");
    if (env == nullptr || env[0] == '\0') {
        if (error != nullptr) {
            *error = "NEMA_EXPECTED_DIGESTS_FILE not set";
        }
        return false;
    }
    std::ifstream in(env);
    if (!in) {
        if (error != nullptr) {
            *error = std::string("cannot open expected digest file: ") + env;
        }
        return false;
    }

    std::string line;
    std::size_t line_no = 0;
    while (std::getline(in, line)) {
        ++line_no;
        std::string token = trim_copy(line);
        if (token.empty() || token[0] == '#') {
            continue;
        }
        if (!is_hex_digest(token)) {
            if (error != nullptr) {
                std::ostringstream oss;
                oss << "invalid digest token at " << env << ":" << line_no << " -> '" << token << "'";
                *error = oss.str();
            }
            out->clear();
            return false;
        }
        out->push_back(token);
    }
    if (source != nullptr) {
        *source = std::string(env);
    }
    return !out->empty();
}

inline int run_with_expected_vector(const std::string& bench_id, int ticks, const std::vector<std::string>& expected) {
    if (ticks < 0) {
        std::cerr << "tb_error: ticks must be >= 0\n";
        return 2;
    }
    if (static_cast<std::size_t>(ticks) != expected.size()) {
        std::cerr << "tb_error: expected digest count mismatch; ticks=" << ticks << " expected=" << expected.size() << "\n";
        return 10;
    }

    std::array<int16_t, nema_model::LUT_SIZE> lut{};
    std::string lut_path;
    if (!load_lut(lut, &lut_path)) {
        std::cerr << "tb_error: failed to load LUT tanh_q8_8.bin via known search paths\n";
        return 3;
    }

    std::array<int16_t, nema_model::NODE_STORAGE> v_cur{};
    std::array<int16_t, nema_model::NODE_STORAGE> v_next{};
    for (int i = 0; i < nema_model::NODE_COUNT; ++i) {
        v_cur[static_cast<std::size_t>(i)] = nema_model::V_INIT[static_cast<std::size_t>(i)];
    }

    std::array<uint8_t, nema_model::NODE_STORAGE * 2> packed{};
    bool mismatch = false;
    int first_mismatch_tick = -1;
    std::string first_expected;
    std::string first_actual;
    std::cout << "tb_begin bench=" << bench_id << " ticks=" << ticks << " lut=" << lut_path << "\n";
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
        std::cout << "tick=" << tick << " digest=" << digest << "\n";
        if (digest != expected[static_cast<std::size_t>(tick)]) {
            std::cerr
                << "tb_mismatch bench=" << bench_id
                << " tick=" << tick
                << " expected=" << expected[static_cast<std::size_t>(tick)]
                << " actual=" << digest
                << "\n";
            if (!mismatch) {
                first_mismatch_tick = tick;
                first_expected = expected[static_cast<std::size_t>(tick)];
                first_actual = digest;
            }
            mismatch = true;
        }
    }
    if (mismatch) {
        std::cerr
            << "tb_first_mismatch bench=" << bench_id
            << " tick=" << first_mismatch_tick
            << " expected=" << first_expected
            << " actual=" << first_actual
            << "\n";
    }
    std::cout << "tb_end bench=" << bench_id << " status=" << (mismatch ? "FAIL" : "PASS") << "\n";
    return mismatch ? 11 : 0;
}

template <std::size_t N>
int run_with_expected(const char* bench_id, int ticks, const std::array<const char*, N>& expected) {
    std::vector<std::string> values;
    values.reserve(N);
    for (std::size_t i = 0; i < N; ++i) {
        values.emplace_back(expected[i]);
    }
    return run_with_expected_vector(resolve_bench_id(bench_id), ticks, values);
}

inline int run_with_expected_from_env(const char* bench_id_fallback, int ticks, bool allow_fallback = false) {
    std::vector<std::string> expected;
    std::string source;
    std::string error;
    if (!load_expected_digests_from_env(&expected, &source, &error)) {
        if (allow_fallback) {
            std::cerr << "tb_warn: failed to load expected digests from env: " << error << "\n";
            return 12;
        }
        std::cerr << "tb_error: failed to load expected digests from env: " << error << "\n";
        return 12;
    }
    const std::string bench_id = resolve_bench_id(bench_id_fallback);
    std::cout << "tb_expected_source bench=" << bench_id << " file=" << source << "\n";
    std::cout << "tb_expected_mode bench=" << bench_id << " mode=manifest_or_golden_file no_legacy_baseline=1\n";
    return run_with_expected_vector(bench_id, ticks, expected);
}

}  // namespace nema_tb
