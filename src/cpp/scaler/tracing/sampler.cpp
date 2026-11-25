#include "scaler/tracing/sampler.h"

#include <algorithm>
#include <cctype>
#include <charconv>
#include <cmath>
#include <system_error>

namespace scaler {
namespace tracing {

namespace {

constexpr const char* samplerVariable         = "OTEL_TRACES_SAMPLER";
constexpr const char* samplerArgumentVariable = "OTEL_TRACES_SAMPLER_ARG";
constexpr const char* defaultSampler          = "parentbased_always_on";
constexpr const char* parentBasedPrefix       = "parentbased_";

constexpr double fullRate = 1.0;
// 2^64: the ratio bound is round(rate * 2^64), as the Python SDK's TraceIdRatioBased computes it
constexpr long double traceIDLowRange = 18446744073709551616.0L;

std::string lowercase(std::string text)
{
    std::transform(text.begin(), text.end(), text.begin(), [](unsigned char letter) { return std::tolower(letter); });
    return text;
}

std::optional<double> parseRate(const std::optional<std::string>& argument)
{
    if (!argument) {
        return std::nullopt;
    }
    double rate             = 0;
    const char* end         = argument->data() + argument->size();
    const auto [ptr, error] = std::from_chars(argument->data(), end, rate);
    if (error != std::errc {} || ptr != end || !(rate >= 0.0 && rate <= fullRate)) {
        return std::nullopt;
    }
    return rate;
}

std::optional<uint64_t> boundForRate(double rate)
{
    const long double bound = std::round(static_cast<long double>(rate) * traceIDLowRange);
    if (bound >= traceIDLowRange) {
        return std::nullopt;
    }
    return static_cast<uint64_t>(bound);
}

}  // namespace

Sampler::Sampler(Decision decision, bool parentBased, std::optional<uint64_t> ratioBound) noexcept
    : _decision {decision}, _parentBased {parentBased}, _ratioBound {ratioBound}
{
}

Sampler Sampler::fromEnvironment(const EnvironmentLookup& lookup, std::vector<std::string>& warnings)
{
    std::string name = lowercase(lookup(samplerVariable).value_or(defaultSampler));

    const bool known = name == "always_on" || name == "always_off" || name == "traceidratio" ||
                       name == "parentbased_always_on" || name == "parentbased_always_off" ||
                       name == "parentbased_traceidratio";
    if (!known) {
        warnings.push_back(
            std::string {samplerVariable} + "=" + name + " is not supported, using " + defaultSampler + " instead");
        name = defaultSampler;
    }

    const bool parentBased = name.starts_with(parentBasedPrefix);
    const std::string root = parentBased ? name.substr(std::string_view {parentBasedPrefix}.size()) : name;

    if (root == "always_on") {
        return Sampler {Decision::alwaysOn, parentBased, std::nullopt};
    }
    if (root == "always_off") {
        return Sampler {Decision::alwaysOff, parentBased, std::nullopt};
    }

    std::optional<double> rate = parseRate(lookup(samplerArgumentVariable));
    if (!rate) {
        warnings.push_back(
            std::string {samplerArgumentVariable} + " must be a rate from 0 to 1 for " + name + ", using 1.0");
        rate = fullRate;
    }
    return Sampler {Decision::traceIDRatio, parentBased, boundForRate(*rate)};
}

bool Sampler::shouldSample(std::optional<bool> parentSampled, uint64_t traceIDLow) const noexcept
{
    if (_parentBased && parentSampled) {
        return *parentSampled;
    }

    switch (_decision) {
        case Decision::alwaysOn: return true;
        case Decision::alwaysOff: return false;
        case Decision::traceIDRatio: return !_ratioBound || traceIDLow < *_ratioBound;
    }
    return true;
}

}  // namespace tracing
}  // namespace scaler
