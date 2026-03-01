#include "nema_digest_tb_common.hpp"

namespace {
constexpr int kTicks = 20;
}  // namespace

int main() { return nema_tb::run_with_expected_from_env("b3_varshney_exec_expanded_gap_300_5824", kTicks); }
