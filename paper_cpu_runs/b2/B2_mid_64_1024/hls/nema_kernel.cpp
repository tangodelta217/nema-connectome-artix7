#include "nema_kernel.h"

#include <cstdint>

namespace {
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
}  // namespace

void nema_kernel(
    const int16_t v_in[nema_model::NODE_STORAGE],
    const int16_t tanh_lut[nema_model::LUT_SIZE],
    int16_t v_out[nema_model::NODE_STORAGE]) {
    int16_t v_snapshot[nema_model::NODE_STORAGE];
    int16_t a_snapshot[nema_model::NODE_STORAGE];
    int32_t i_chem[nema_model::NODE_STORAGE];
    int32_t i_gap[nema_model::NODE_STORAGE];
    static bool delay_initialized = false;
    static int delay_cursor = 0;
    static int16_t delay_v_ring[nema_model::DELAY_RING_SIZE][nema_model::NODE_STORAGE];
    static int16_t delay_a_ring[nema_model::DELAY_RING_SIZE][nema_model::NODE_STORAGE];
    #pragma HLS BIND_STORAGE variable=delay_v_ring type=RAM_2P impl=BRAM
    #pragma HLS BIND_STORAGE variable=delay_a_ring type=RAM_2P impl=BRAM

    for (int i = 0; i < nema_model::NODE_COUNT; ++i) {
        v_snapshot[i] = v_in[i];
        i_chem[i] = 0;
        i_gap[i] = 0;
    }

    for (int i = 0; i < nema_model::NODE_COUNT; ++i) {
        const uint16_t lut_idx =
            static_cast<uint16_t>(static_cast<int32_t>(v_snapshot[i]) - static_cast<int32_t>(-32768));
        a_snapshot[i] = tanh_lut[lut_idx];
    }

    if (nema_model::HAS_DELAY && !delay_initialized) {
        for (int slot = 0; slot < nema_model::DELAY_RING_SIZE; ++slot) {
            for (int i = 0; i < nema_model::NODE_COUNT; ++i) {
                delay_v_ring[slot][i] = v_snapshot[i];
                delay_a_ring[slot][i] = a_snapshot[i];
            }
        }
        delay_cursor = 0;
        delay_initialized = true;
    }

    for (int post = 0; post < nema_model::NODE_COUNT; ++post) {
        const int begin = static_cast<int>(nema_model::CHEM_ROW_PTR[post]);
        const int end = static_cast<int>(nema_model::CHEM_ROW_PTR[post + 1]);
        const int chem_edges = end - begin;
        const int chem_tiles =
            (chem_edges + nema_model::SYNAPSE_LANES - 1) / nema_model::SYNAPSE_LANES;
        for (int tile = 0; tile < chem_tiles; ++tile) {
            #pragma HLS UNROLL factor=1
            for (int lane = 0; lane < nema_model::SYNAPSE_LANES; ++lane) {
                const int edge = begin + tile * nema_model::SYNAPSE_LANES + lane;
                if (edge >= end) {
                    continue;
                }
                const int pre = static_cast<int>(nema_model::CHEM_PRE_IDX[edge]);
                int32_t pre_output = static_cast<int32_t>(a_snapshot[pre]);
                if (nema_model::HAS_DELAY) {
                    const int delay_ticks = static_cast<int>(nema_model::CHEM_DELAY_TICKS[edge]);
                    if (delay_ticks > 0) {
                        const int delayed_slot =
                            (delay_cursor - delay_ticks + nema_model::DELAY_RING_SIZE) %
                            nema_model::DELAY_RING_SIZE;
                        pre_output = static_cast<int32_t>(delay_a_ring[delayed_slot][pre]);
                    }
                }
                const int32_t msg = quantize_to_accum(
                    nema_model::CHEM_WEIGHT_NUM[edge],
                    nema_model::CHEM_WEIGHT_DEN[edge],
                    pre_output);
                i_chem[post] = sat_add_accum(i_chem[post], msg);
            }
        }
    }

    for (int edge = 0; edge < nema_model::GAP_EDGE_COUNT; ++edge) {
        const int a = static_cast<int>(nema_model::GAP_A_IDX[edge]);
        const int b = static_cast<int>(nema_model::GAP_B_IDX[edge]);
        int32_t va = static_cast<int32_t>(v_snapshot[a]);
        int32_t vb = static_cast<int32_t>(v_snapshot[b]);
        if (nema_model::HAS_DELAY) {
            const int delay_ticks = static_cast<int>(nema_model::GAP_DELAY_TICKS[edge]);
            if (delay_ticks > 0) {
                const int delayed_slot =
                    (delay_cursor - delay_ticks + nema_model::DELAY_RING_SIZE) %
                    nema_model::DELAY_RING_SIZE;
                va = static_cast<int32_t>(delay_v_ring[delayed_slot][a]);
                vb = static_cast<int32_t>(delay_v_ring[delayed_slot][b]);
            }
        }
        const int32_t dv = vb - va;
        const int32_t msg = quantize_to_accum(
            nema_model::GAP_CONDUCTANCE_NUM[edge],
            nema_model::GAP_CONDUCTANCE_DEN[edge],
            dv);
        i_gap[a] = sat_add_accum(i_gap[a], msg);
        i_gap[b] = sat_add_accum(i_gap[b], -msg);
    }

    const int neuron_tiles =
        (nema_model::NODE_COUNT + nema_model::NEURON_LANES - 1) / nema_model::NEURON_LANES;
    for (int tile = 0; tile < neuron_tiles; ++tile) {
        #pragma HLS UNROLL factor=1
        for (int lane = 0; lane < nema_model::NEURON_LANES; ++lane) {
            const int i = tile * nema_model::NEURON_LANES + lane;
            if (i >= nema_model::NODE_COUNT) {
                continue;
            }
            const int32_t total_i = sat_add_accum(i_chem[i], i_gap[i]);
            const int16_t delta_v = quantize_to_v(
                nema_model::INV_TAU_NUM[i],
                nema_model::INV_TAU_DEN[i],
                total_i);
            v_out[i] = sat_i16_i64(static_cast<int64_t>(v_snapshot[i]) + static_cast<int64_t>(delta_v));
        }
    }

    if (nema_model::HAS_DELAY) {
        for (int i = 0; i < nema_model::NODE_COUNT; ++i) {
            delay_v_ring[delay_cursor][i] = v_snapshot[i];
            delay_a_ring[delay_cursor][i] = a_snapshot[i];
        }
        delay_cursor = (delay_cursor + 1) % nema_model::DELAY_RING_SIZE;
    }
}
