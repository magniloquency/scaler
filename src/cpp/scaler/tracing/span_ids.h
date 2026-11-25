#pragma once

#include <cstdint>

namespace scaler {
namespace tracing {

// A random, never zero 64-bit value: a span id, or half of a trace id; each thread draws from its own generator.
uint64_t generateID();

}  // namespace tracing
}  // namespace scaler
