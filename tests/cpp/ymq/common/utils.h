#include <cstring>
#include <filesystem>
#include <sstream>

inline void raise_system_error(const char* msg)
{
#ifdef __linux__
    throw std::system_error(errno, std::generic_category(), msg);
#endif  // __linux__
#ifdef _WIN32
    throw std::system_error(GetLastError(), std::generic_category(), msg);
#endif  // _WIN32
}

inline void raise_socket_error(const char* msg)
{
#ifdef __linux__
    throw std::system_error(errno, std::generic_category(), msg);
#endif  // __linux__
#ifdef _WIN32
    throw std::system_error(WSAGetLastError(), std::generic_category(), msg);
#endif  // _WIN32
}

inline const char* check_localhost(const char* host)
{
    return std::strcmp(host, "localhost") == 0 ? "127.0.0.1" : host;
}

inline std::string format_address(std::string host, uint16_t port)
{
    std::ostringstream oss;
    oss << "tcp://" << check_localhost(host.c_str()) << ":" << port;
    return oss.str();
}

// change the current working directory to the project root
// this is important for finding the python mitm script
inline void chdir_to_project_root()
{
    auto cwd = std::filesystem::current_path();

    // if pyproject.toml is in `path`, it's the project root
    for (auto path = cwd; !path.empty(); path = path.parent_path()) {
        if (std::filesystem::exists(path / "pyproject.toml")) {
            // change to the project root
            std::filesystem::current_path(path);
            return;
        }
    }
}
