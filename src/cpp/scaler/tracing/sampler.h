#pragma once

#include <cstdint>
#include <optional>
#include <string>
#include <vector>

#include "scaler/tracing/environment.h"

namespace scaler {
namespace tracing {

// The sampler OTEL_TRACES_SAMPLER and OTEL_TRACES_SAMPLER_ARG configure, deciding as the Python SDK's samplers do:
// always_on, always_off, traceidratio, and their parentbased_ forms, which follow a parent's sampled flag.
class Sampler {
public:
    // A setting it cannot use adds a warning, and it falls back as the Python SDK does.
    static Sampler fromEnvironment(const EnvironmentLookup& lookup, std::vector<std::string>& warnings);

    // `parentSampled` is the parent span's sampled flag, nullopt for a root span; `traceIDLow` is the trace id's
    // low 64 bits, which the ratio samplers compare against their bound.
    bool shouldSample(std::optional<bool> parentSampled, uint64_t traceIDLow) const noexcept;

private:
    enum class Decision { alwaysOn, alwaysOff, traceIDRatio };

    Decision _decision;
    bool _parentBased;
    std::optional<uint64_t> _ratioBound;  // sampled when traceIDLow is below it; nullopt samples every trace id

    Sampler(Decision decision, bool parentBased, std::optional<uint64_t> ratioBound) noexcept;
};

}  // namespace tracing
}  // namespace scaler
