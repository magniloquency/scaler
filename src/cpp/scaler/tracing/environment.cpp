#include "scaler/tracing/environment.h"

#include <cstdlib>

namespace scaler {
namespace tracing {

std::optional<std::string> processEnvironment(std::string_view name)
{
    const char* value = std::getenv(std::string {name}.c_str());
    if (value == nullptr) {
        return std::nullopt;
    }
    return std::string {value};
}

}  // namespace tracing
}  // namespace scaler
