#pragma once
#include <cstdint>

namespace nema_model {
static constexpr int NODE_COUNT = 2;
static constexpr int NODE_STORAGE = NODE_COUNT > 0 ? NODE_COUNT : 1;
static constexpr int CHEM_EDGE_COUNT = 1;
static constexpr int CHEM_EDGE_STORAGE = CHEM_EDGE_COUNT > 0 ? CHEM_EDGE_COUNT : 1;
static constexpr int GAP_EDGE_COUNT = 1;
static constexpr int GAP_EDGE_STORAGE = GAP_EDGE_COUNT > 0 ? GAP_EDGE_COUNT : 1;
static constexpr int LUT_SIZE = 65536;
static constexpr int SYNAPSE_LANES = 1;
static constexpr int NEURON_LANES = 1;
static constexpr int DELAY_MAX = 0;
static constexpr int DELAY_RING_SIZE = DELAY_MAX + 1;
static constexpr bool HAS_DELAY = DELAY_MAX > 0;
static constexpr int32_t ACCUM_MIN = -524288;
static constexpr int32_t ACCUM_MAX = 524287;

static constexpr int16_t V_INIT[NODE_STORAGE] = {0, 0};
static constexpr int64_t INV_TAU_NUM[NODE_STORAGE] = {1, 1};
static constexpr int64_t INV_TAU_DEN[NODE_STORAGE] = {1, 1};

static constexpr uint16_t CHEM_ROW_PTR[NODE_COUNT + 1] = {0, 0, 1};
static constexpr uint16_t CHEM_PRE_IDX[CHEM_EDGE_STORAGE] = {0};
static constexpr int64_t CHEM_WEIGHT_NUM[CHEM_EDGE_STORAGE] = {1};
static constexpr int64_t CHEM_WEIGHT_DEN[CHEM_EDGE_STORAGE] = {2};
static constexpr uint8_t CHEM_MODEL_ID[CHEM_EDGE_STORAGE] = {0};
static constexpr uint16_t CHEM_DELAY_TICKS[CHEM_EDGE_STORAGE] = {0};
static constexpr uint8_t CHEM_PADDING[CHEM_EDGE_STORAGE] = {0};

static constexpr uint16_t GAP_A_IDX[GAP_EDGE_STORAGE] = {0};
static constexpr uint16_t GAP_B_IDX[GAP_EDGE_STORAGE] = {1};
static constexpr int64_t GAP_CONDUCTANCE_NUM[GAP_EDGE_STORAGE] = {1};
static constexpr int64_t GAP_CONDUCTANCE_DEN[GAP_EDGE_STORAGE] = {8};
static constexpr uint8_t GAP_MODEL_ID[GAP_EDGE_STORAGE] = {0};
static constexpr uint16_t GAP_DELAY_TICKS[GAP_EDGE_STORAGE] = {0};
static constexpr uint8_t GAP_PADDING[GAP_EDGE_STORAGE] = {0};
}  // namespace nema_model

void nema_kernel(
    const int16_t v_in[nema_model::NODE_STORAGE],
    const int16_t tanh_lut[nema_model::LUT_SIZE],
    int16_t v_out[nema_model::NODE_STORAGE]);
