#pragma once

#include <functional>
#include <optional>
#include <string>
#include <string_view>

namespace scaler {
namespace tracing {

// Looks up one environment variable: processEnvironment in production, a map in tests.
using EnvironmentLookup = std::function<std::optional<std::string>(std::string_view name)>;

std::optional<std::string> processEnvironment(std::string_view name);

}  // namespace tracing
}  // namespace scaler
