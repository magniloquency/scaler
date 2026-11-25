#!/bin/bash -e
# This script builds and installs the required 3rd party C++ libraries.
#
# Usage:
#       ./scripts/library_tool.sh [capnp|libuv|openssl|emsdk|zlib|abseil|protobuf|curl|nlohmann_json|opentelemetry_cpp] [download|compile|install] [--prefix=PREFIX] [--target=native|wasm]
#
# --target=wasm cross-compiles capnp/libuv against the Emscripten toolchain.
# It expects emcc/emcmake on PATH (source thirdparties/emsdk/emsdk_env.sh first)
# and that the host `capnp` tool is already installed (capnp code generation
# can't run inside wasm). Output defaults to ./thirdparties/wasm/install.
#
# OpenSSL is built natively only; --target=wasm is rejected for it. A wasm
# OpenSSL (needed later for wss:// in the browser) is future work.
#
# emsdk is always installed at $THIRD_PARTY_DIR/emsdk; --prefix and --target are ignored for it.
#
# Override the install root with the THIRD_PARTY_DIR env var (default
# ./thirdparties); the devcontainer image bakes things into /opt/scaler so the
# workspace bind mount doesn't shadow them.

# Remember:
#       Update the usage string when you add/remove a dependency or target.
#       Bump versions through variables, not hard coded strings.

CAPNP_VERSION="1.1.0"
UV_VERSION="1.51.0"
OPENSSL_VERSION="4.0.0"
# the native span exporter (opentelemetry-cpp's OTLP/HTTP exporter); these are the versions opentelemetry-cpp's
# third_party_release file pins for OPENTELEMETRY_CPP_VERSION
ZLIB_VERSION="1.3.2"
ABSEIL_VERSION="20250512.1"
PROTOBUF_VERSION="35.1"
CURL_VERSION="8.21.0"
NLOHMANN_JSON_VERSION="3.12.0"
OPENTELEMETRY_PROTO_VERSION="1.11.0"
OPENTELEMETRY_CPP_VERSION="1.30.0"
# emsdk version must match the Pyodide xbuildenv/kernel used for the wasm wheel build
# (currently 5.0.3 -> Pyodide 314.0.0 -> CPython 3.14).
EMSDK_VERSION="5.0.3"

THIRD_PARTY_DIRECTORY="${THIRD_PARTY_DIR:-./thirdparties}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PATCHES_DIRECTORY="${SCRIPT_DIR}/patches"

THIRD_PARTY_DOWNLOADED="${THIRD_PARTY_DIRECTORY}/downloaded"

TARGET="native"
PREFIX=""

# Parse optional flags. Positional args ($1, $2) are the library name and step.
for arg in "$@"; do
    if [[ "$arg" == --prefix=* ]]; then
        PREFIX="${arg#--prefix=}"
    elif [[ "$arg" == --target=* ]]; then
        TARGET="${arg#--target=}"
    fi
done

if [[ "$TARGET" != "native" && "$TARGET" != "wasm" ]]; then
    echo "Unknown --target=${TARGET}; expected 'native' or 'wasm'."
    exit 1
fi

if [[ "$TARGET" == "wasm" ]]; then
    THIRD_PARTY_COMPILED="${THIRD_PARTY_DIRECTORY}/wasm/src"
    DEFAULT_PREFIX="${THIRD_PARTY_DIRECTORY}/wasm/install"
else
    THIRD_PARTY_COMPILED="${THIRD_PARTY_DIRECTORY}/compiled"
    DEFAULT_PREFIX="/usr/local"
fi

if [[ -z "${PREFIX}" ]]; then
    PREFIX="${DEFAULT_PREFIX}"
fi

if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    NUM_CORES=$(nproc)
elif [[ "$OSTYPE" == "darwin"* ]]; then
    NUM_CORES=$(sysctl -n hw.ncpu)
else
    NUM_CORES=1
fi

PREFIX=$(mkdir -p "${PREFIX}" && cd "${PREFIX}" && pwd)

show_help() {
    echo "Usage: ./library_tool.sh [capnp|libuv|openssl|emsdk|zlib|abseil|protobuf|curl|nlohmann_json|opentelemetry_cpp] [download|compile|install] [--prefix=DIR] [--target=native|wasm]"
    exit 1
}

# Usage: download_tar_gz <url> <folder_name>
download_tar_gz() {
    local url="$1"
    local folder_name="$2"

    curl --retry 100 --retry-max-time 3600 \
        -L "${url}" \
        -o "${THIRD_PARTY_DOWNLOADED}/${folder_name}.tar.gz"
    echo "Downloaded ${folder_name} into ${THIRD_PARTY_DOWNLOADED}/${folder_name}.tar.gz"
}

# Usage: extract_tar_gz <folder_name>
extract_tar_gz() {
    local folder_name="$1"

    rm -rf "${THIRD_PARTY_COMPILED}/${folder_name}"
    tar -xzf "${THIRD_PARTY_DOWNLOADED}/${folder_name}.tar.gz" -C "${THIRD_PARTY_COMPILED}"
}

require_emscripten() {
    if command -v emcmake >/dev/null 2>&1; then
        return 0
    fi
    # Auto-source emsdk_env.sh from THIRD_PARTY_DIR/emsdk so callers don't have
    # to remember to do it themselves. emsdk_env.sh uses BASH_SOURCE to find
    # itself, which is why this script has a `#!/bin/bash` shebang (Docker RUN
    # uses /bin/sh, where BASH_SOURCE is empty).
    local emsdk_env="${THIRD_PARTY_DIRECTORY}/emsdk/emsdk_env.sh"
    if [[ -f "${emsdk_env}" ]]; then
        # shellcheck disable=SC1090
        source "${emsdk_env}" >/dev/null 2>&1 || true
    fi
    if ! command -v emcmake >/dev/null 2>&1; then
        echo "emcmake not found; install emsdk first ('./scripts/library_tool.sh emsdk download/compile/install') or source ${emsdk_env}."
        exit 1
    fi
}

# Usage: native_only <library>; the span exporter's libraries have no wasm build, like the module that uses them
native_only() {
    if [[ "$TARGET" == "wasm" ]]; then
        echo "$1 --target=wasm is not supported; it is built natively only."
        exit 1
    fi
}

# Usage: cmake_compile <folder_name> <cmake arguments...>; a static, position-independent Release build
cmake_compile() {
    local folder_name="$1"
    shift
    cd "${THIRD_PARTY_COMPILED}/${folder_name}"
    cmake -B build \
        -DCMAKE_INSTALL_PREFIX="${PREFIX}" \
        -DCMAKE_PREFIX_PATH="${PREFIX}" \
        -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_CXX_STANDARD=17 \
        -DCMAKE_POSITION_INDEPENDENT_CODE=ON \
        -DBUILD_SHARED_LIBS=OFF \
        -DBUILD_TESTING=OFF \
        "$@" >/dev/null
    cmake --build build --config Release -j "${NUM_CORES}" >/dev/null
    echo "Compiled ${folder_name} to ${THIRD_PARTY_COMPILED}/${folder_name}"
}

# Usage: cmake_install <folder_name>
cmake_install() {
    cd "${THIRD_PARTY_COMPILED}/$1"
    cmake --install build --config Release >/dev/null
    echo "Installed $1 into ${PREFIX}"
}

apply_patch_if_present() {
    # apply_patch_if_present <source-dir> <patch-file>
    local src_dir="$1"
    local patch_file="$2"
    if [[ ! -f "${patch_file}" ]]; then
        return 0
    fi
    # Skip if already applied (reverse dry-run succeeds means the patch is
    # already in the source tree).
    if patch -d "${src_dir}" -p1 -R --dry-run --silent < "${patch_file}" >/dev/null 2>&1; then
        echo "Patch already applied: ${patch_file}"
        return 0
    fi
    echo "Applying patch ${patch_file}"
    patch -d "${src_dir}" -p1 < "${patch_file}"
}

if [ "$2" == "download" ]; then
    mkdir -p "${THIRD_PARTY_DOWNLOADED}"
elif [ "$2" == "compile" ]; then
    mkdir -p "${THIRD_PARTY_COMPILED}"
fi

if [ "$1" == "capnp" ]; then
    CAPNP_FOLDER_NAME="capnproto-c++-${CAPNP_VERSION}"
    CAPNP_URL="https://capnproto.org/${CAPNP_FOLDER_NAME}.tar.gz"

    if [ "$2" == "download" ]; then
        download_tar_gz "${CAPNP_URL}" "${CAPNP_FOLDER_NAME}"

    elif [ "$2" == "compile" ]; then
        extract_tar_gz "${CAPNP_FOLDER_NAME}"

        if [[ "$TARGET" == "wasm" ]]; then
            require_emscripten
            apply_patch_if_present \
                "${THIRD_PARTY_COMPILED}/${CAPNP_FOLDER_NAME}" \
                "${PATCHES_DIRECTORY}/capnproto-${CAPNP_VERSION}-emscripten.patch"
            cd "${THIRD_PARTY_COMPILED}/${CAPNP_FOLDER_NAME}"
            # The patch above skips building the capnp/capnpc-c++/capnpc-capnp
            # tools under EMSCRIPTEN; we use the host capnp tools (symlinked
            # under <prefix>/bin/<tool>.js by the install step) for codegen.
            emcmake cmake -B build-wasm \
                -DCMAKE_INSTALL_PREFIX="${PREFIX}" \
                -DCMAKE_BUILD_TYPE=Release \
                -DBUILD_TESTING=OFF \
                -DEXTERNAL_CAPNP=ON \
                -DWITH_OPENSSL=OFF \
                -DCMAKE_POSITION_INDEPENDENT_CODE=ON \
                -DCMAKE_C_FLAGS="-fPIC -fwasm-exceptions -sSUPPORT_LONGJMP -fno-merge-all-constants" \
                -DCMAKE_CXX_FLAGS="-fPIC -fwasm-exceptions -sSUPPORT_LONGJMP -fno-merge-all-constants"
            cmake --build build-wasm --config Release -j "${NUM_CORES}"
        else
            cd "${THIRD_PARTY_COMPILED}/${CAPNP_FOLDER_NAME}"
            ./configure --prefix="${PREFIX}" CXXFLAGS="${CXXFLAGS} -I${PREFIX}/include" LDFLAGS="${LDFLAGS} -L${PREFIX}/lib -Wl,-rpath,${PREFIX}/lib" >/dev/null
            make -j "${NUM_CORES}" >/dev/null
        fi
        echo "Compiled capnp to ${THIRD_PARTY_COMPILED}/${CAPNP_FOLDER_NAME}"

    elif [ "$2" == "install" ]; then
        cd "${THIRD_PARTY_COMPILED}/${CAPNP_FOLDER_NAME}"
        if [[ "$TARGET" == "wasm" ]]; then
            cmake --install build-wasm
            # CapnProtoTargets.cmake imports CapnProto::capnp_tool as
            # ${prefix}/bin/<tool>.js (Pyodide convention). The tools can't run
            # in wasm, so symlink the host-installed binaries instead.
            mkdir -p "${PREFIX}/bin"
            for tool in capnp capnpc-c++ capnpc-capnp; do
                host_tool=$(command -v "${tool}" || true)
                if [[ -z "${host_tool}" ]]; then
                    echo "Host capnp tool '${tool}' not found on PATH; install native capnp first."
                    exit 1
                fi
                ln -sf "${host_tool}" "${PREFIX}/bin/${tool}.js"
            done
        else
            make install >/dev/null
        fi
        echo "Installed capnp into ${PREFIX}"

    else
        show_help
    fi
elif [ "$1" == "libuv" ]; then
    UV_FOLDER_NAME="libuv-${UV_VERSION}"
    UV_URL="https://github.com/libuv/libuv/archive/refs/tags/v${UV_VERSION}.tar.gz"

    if [ "$2" == "download" ]; then
        download_tar_gz "${UV_URL}" "${UV_FOLDER_NAME}"

    elif [ "$2" == "compile" ]; then
        extract_tar_gz "${UV_FOLDER_NAME}"

        if [[ "$TARGET" == "wasm" ]]; then
            require_emscripten
            apply_patch_if_present \
                "${THIRD_PARTY_COMPILED}/${UV_FOLDER_NAME}" \
                "${PATCHES_DIRECTORY}/libuv-${UV_VERSION}-emscripten.patch"
            cd "${THIRD_PARTY_COMPILED}/${UV_FOLDER_NAME}"
            # LIBUV_BUILD_SHARED=OFF: under Emscripten libuv's "shared" target
            # still emits libuv.a (no real .so on wasm), which races with the
            # static uv_a target writing the same file under parallel builds.
            emcmake cmake -B build \
                -DCMAKE_INSTALL_PREFIX="${PREFIX}" \
                -DCMAKE_BUILD_TYPE=Release \
                -DBUILD_TESTING=OFF \
                -DLIBUV_BUILD_SHARED=OFF \
                -DCMAKE_POSITION_INDEPENDENT_CODE=ON \
                -DCMAKE_C_FLAGS="-fPIC -fwasm-exceptions -sSUPPORT_LONGJMP -fno-merge-all-constants" \
                -DCMAKE_CXX_FLAGS="-fPIC -fwasm-exceptions -sSUPPORT_LONGJMP -fno-merge-all-constants"
        else
            cd "${THIRD_PARTY_COMPILED}/${UV_FOLDER_NAME}"
            cmake -B build -DCMAKE_INSTALL_PREFIX="${PREFIX}" -DBUILD_TESTING=OFF -DCMAKE_POSITION_INDEPENDENT_CODE=ON
        fi
        cmake --build build --config Release -j "${NUM_CORES}"
        echo "Compiled libuv to ${THIRD_PARTY_COMPILED}/${UV_FOLDER_NAME}"

    elif [ "$2" == "install" ]; then
        cd "${THIRD_PARTY_COMPILED}/${UV_FOLDER_NAME}"
        cmake --install build
        echo "Installed libuv into ${PREFIX}"

    else
        show_help
    fi
elif [ "$1" == "openssl" ]; then
    if [[ "$TARGET" == "wasm" ]]; then
        echo "openssl --target=wasm is not supported yet; OpenSSL is built natively only."
        exit 1
    fi

    OPENSSL_FOLDER_NAME="openssl-${OPENSSL_VERSION}"
    OPENSSL_URL="https://github.com/openssl/openssl/releases/download/openssl-${OPENSSL_VERSION}/${OPENSSL_FOLDER_NAME}.tar.gz"

    if [ "$2" == "download" ]; then
        download_tar_gz "${OPENSSL_URL}" "${OPENSSL_FOLDER_NAME}"

    elif [ "$2" == "compile" ]; then
        extract_tar_gz "${OPENSSL_FOLDER_NAME}"

        cd "${THIRD_PARTY_COMPILED}/${OPENSSL_FOLDER_NAME}"
        ./config --prefix="${PREFIX}" --libdir=lib no-tests no-shared >/dev/null
        make -j "${NUM_CORES}" >/dev/null
        echo "Compiled OpenSSL to ${THIRD_PARTY_COMPILED}/${OPENSSL_FOLDER_NAME}"

    elif [ "$2" == "install" ]; then
        cd "${THIRD_PARTY_COMPILED}/${OPENSSL_FOLDER_NAME}"
        make install_sw >/dev/null
        echo "Installed OpenSSL into ${PREFIX}"

    else
        show_help
    fi
elif [ "$1" == "zlib" ]; then
    native_only zlib
    ZLIB_FOLDER_NAME="zlib-${ZLIB_VERSION}"

    if [ "$2" == "download" ]; then
        download_tar_gz "https://github.com/madler/zlib/archive/refs/tags/v${ZLIB_VERSION}.tar.gz" "${ZLIB_FOLDER_NAME}"
    elif [ "$2" == "compile" ]; then
        extract_tar_gz "${ZLIB_FOLDER_NAME}"
        cmake_compile "${ZLIB_FOLDER_NAME}" -DZLIB_BUILD_EXAMPLES=OFF -DZLIB_BUILD_SHARED=OFF
    elif [ "$2" == "install" ]; then
        cmake_install "${ZLIB_FOLDER_NAME}"
    else
        show_help
    fi
elif [ "$1" == "abseil" ]; then
    native_only abseil
    ABSEIL_FOLDER_NAME="abseil-cpp-${ABSEIL_VERSION}"

    if [ "$2" == "download" ]; then
        download_tar_gz \
            "https://github.com/abseil/abseil-cpp/archive/refs/tags/${ABSEIL_VERSION}.tar.gz" "${ABSEIL_FOLDER_NAME}"
    elif [ "$2" == "compile" ]; then
        extract_tar_gz "${ABSEIL_FOLDER_NAME}"
        cmake_compile "${ABSEIL_FOLDER_NAME}" -DABSL_PROPAGATE_CXX_STD=ON -DABSL_BUILD_TESTING=OFF
    elif [ "$2" == "install" ]; then
        cmake_install "${ABSEIL_FOLDER_NAME}"
    else
        show_help
    fi
elif [ "$1" == "protobuf" ]; then
    native_only protobuf
    PROTOBUF_FOLDER_NAME="protobuf-${PROTOBUF_VERSION}"

    if [ "$2" == "download" ]; then
        download_tar_gz \
            "https://github.com/protocolbuffers/protobuf/releases/download/v${PROTOBUF_VERSION}/${PROTOBUF_FOLDER_NAME}.tar.gz" \
            "${PROTOBUF_FOLDER_NAME}"
    elif [ "$2" == "compile" ]; then
        extract_tar_gz "${PROTOBUF_FOLDER_NAME}"
        cmake_compile "${PROTOBUF_FOLDER_NAME}" \
            -Dprotobuf_BUILD_TESTS=OFF \
            -Dprotobuf_ABSL_PROVIDER=package \
            -Dprotobuf_ZLIB_PROVIDER=package \
            -Dprotobuf_INSTALL=ON
    elif [ "$2" == "install" ]; then
        cmake_install "${PROTOBUF_FOLDER_NAME}"
    else
        show_help
    fi
elif [ "$1" == "curl" ]; then
    native_only curl
    CURL_FOLDER_NAME="curl-${CURL_VERSION}"

    if [ "$2" == "download" ]; then
        download_tar_gz "https://curl.se/download/${CURL_FOLDER_NAME}.tar.gz" "${CURL_FOLDER_NAME}"
    elif [ "$2" == "compile" ]; then
        extract_tar_gz "${CURL_FOLDER_NAME}"
        # HTTP(S) only, with the OpenSSL and zlib built above: the OTLP/HTTP exporter needs nothing else
        cmake_compile "${CURL_FOLDER_NAME}" \
            -DBUILD_CURL_EXE=OFF \
            -DBUILD_LIBCURL_DOCS=OFF \
            -DBUILD_MISC_DOCS=OFF \
            -DENABLE_CURL_MANUAL=OFF \
            -DHTTP_ONLY=ON \
            -DCURL_USE_OPENSSL=ON \
            -DOPENSSL_ROOT_DIR="${PREFIX}" \
            -DCURL_ZLIB=ON \
            -DCURL_BROTLI=OFF \
            -DCURL_ZSTD=OFF \
            -DCURL_USE_LIBPSL=OFF \
            -DCURL_USE_LIBSSH2=OFF \
            -DUSE_NGHTTP2=OFF \
            -DUSE_LIBIDN2=OFF
    elif [ "$2" == "install" ]; then
        cmake_install "${CURL_FOLDER_NAME}"
    else
        show_help
    fi
elif [ "$1" == "nlohmann_json" ]; then
    native_only nlohmann_json
    NLOHMANN_JSON_FOLDER_NAME="json-${NLOHMANN_JSON_VERSION}"

    if [ "$2" == "download" ]; then
        download_tar_gz \
            "https://github.com/nlohmann/json/archive/refs/tags/v${NLOHMANN_JSON_VERSION}.tar.gz" \
            "${NLOHMANN_JSON_FOLDER_NAME}"
    elif [ "$2" == "compile" ]; then
        extract_tar_gz "${NLOHMANN_JSON_FOLDER_NAME}"
        cmake_compile "${NLOHMANN_JSON_FOLDER_NAME}" -DJSON_BuildTests=OFF -DJSON_Install=ON
    elif [ "$2" == "install" ]; then
        cmake_install "${NLOHMANN_JSON_FOLDER_NAME}"
    else
        show_help
    fi
elif [ "$1" == "opentelemetry_cpp" ]; then
    native_only opentelemetry_cpp
    OPENTELEMETRY_CPP_FOLDER_NAME="opentelemetry-cpp-${OPENTELEMETRY_CPP_VERSION}"
    OPENTELEMETRY_PROTO_FOLDER_NAME="opentelemetry-proto-${OPENTELEMETRY_PROTO_VERSION}"

    if [ "$2" == "download" ]; then
        download_tar_gz \
            "https://github.com/open-telemetry/opentelemetry-cpp/archive/refs/tags/v${OPENTELEMETRY_CPP_VERSION}.tar.gz" \
            "${OPENTELEMETRY_CPP_FOLDER_NAME}"
        download_tar_gz \
            "https://github.com/open-telemetry/opentelemetry-proto/archive/refs/tags/v${OPENTELEMETRY_PROTO_VERSION}.tar.gz" \
            "${OPENTELEMETRY_PROTO_FOLDER_NAME}"
    elif [ "$2" == "compile" ]; then
        extract_tar_gz "${OPENTELEMETRY_CPP_FOLDER_NAME}"
        extract_tar_gz "${OPENTELEMETRY_PROTO_FOLDER_NAME}"
        # only the SDK and the OTLP/HTTP exporter; the proto sources come from the tarball, not a git clone
        cmake_compile "${OPENTELEMETRY_CPP_FOLDER_NAME}" \
            -DOTELCPP_PROTO_PATH="$(cd "${THIRD_PARTY_COMPILED}/${OPENTELEMETRY_PROTO_FOLDER_NAME}" && pwd)" \
            -DWITH_OTLP_HTTP=ON \
            -DWITH_OTLP_GRPC=OFF \
            -DWITH_OTLP_FILE=OFF \
            -DWITH_OTLP_HTTP_COMPRESSION=ON \
            -DWITH_EXAMPLES=OFF \
            -DWITH_BENCHMARK=OFF \
            -DWITH_FUNC_TESTS=OFF \
            -DOPENTELEMETRY_INSTALL=ON
    elif [ "$2" == "install" ]; then
        cmake_install "${OPENTELEMETRY_CPP_FOLDER_NAME}"
    else
        show_help
    fi
elif [ "$1" == "emsdk" ]; then
    # emsdk is a binary toolchain distribution; it lives at a fixed path so its
    # internal `emsdk_env.sh` (and the cached compiler/sysroot under
    # upstream/emscripten/) can be sourced consistently. --prefix / --target are
    # ignored for this library.
    EMSDK_DIRECTORY="${THIRD_PARTY_DIRECTORY}/emsdk"

    if [ "$2" == "download" ]; then
        if [[ -d "${EMSDK_DIRECTORY}/.git" ]]; then
            echo "emsdk repo already present at ${EMSDK_DIRECTORY}; skipping clone."
        else
            mkdir -p "${THIRD_PARTY_DIRECTORY}"
            # Pinning by tag is sufficient: the emsdk repo's tags match
            # emscripten release versions (e.g. tag 4.0.9 == Emscripten 4.0.9).
            git clone --branch "${EMSDK_VERSION}" --depth 1 \
                https://github.com/emscripten-core/emsdk.git "${EMSDK_DIRECTORY}"
        fi
        echo "Downloaded emsdk into ${EMSDK_DIRECTORY}"

    elif [ "$2" == "compile" ]; then
        # `emsdk install` downloads the pinned compiler / node / sysroot bundle.
        # No source compilation actually happens, but the step is heavy enough
        # to justify the same lifecycle slot as the other libraries.
        if [[ ! -x "${EMSDK_DIRECTORY}/emsdk" ]]; then
            echo "emsdk not downloaded; run './scripts/library_tool.sh emsdk download' first."
            exit 1
        fi
        "${EMSDK_DIRECTORY}/emsdk" install "${EMSDK_VERSION}"
        echo "Compiled (downloaded toolchain for) emsdk ${EMSDK_VERSION}"

    elif [ "$2" == "install" ]; then
        if [[ ! -x "${EMSDK_DIRECTORY}/emsdk" ]]; then
            echo "emsdk not downloaded; run './scripts/library_tool.sh emsdk download' first."
            exit 1
        fi
        "${EMSDK_DIRECTORY}/emsdk" activate "${EMSDK_VERSION}"
        echo "Installed (activated) emsdk ${EMSDK_VERSION}; source ${EMSDK_DIRECTORY}/emsdk_env.sh to use it."

    else
        show_help
    fi
else
    show_help
fi
