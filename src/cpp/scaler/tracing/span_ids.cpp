#include "scaler/tracing/span_ids.h"

#include <random>

namespace scaler {
namespace tracing {

uint64_t generateID()
{
    thread_local std::mt19937_64 generator {std::random_device {}()};
    uint64_t value = 0;
    while (value == 0) {  // W3C trace context reserves all-zero ids as invalid
        value = generator();
    }
    return value;
}

}  // namespace tracing
}  // namespace scaler
