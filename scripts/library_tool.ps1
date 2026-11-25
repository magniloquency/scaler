$ErrorActionPreference = "Stop"

# Constants

$CAPNP_VERSION = "1.1.0"
$UV_VERSION = "1.51.0"
$OPENSSL_VERSION = "4.0.0"
# the native span exporter (opentelemetry-cpp's OTLP/HTTP exporter); these are the versions opentelemetry-cpp's
# third_party_release file pins for OPENTELEMETRY_CPP_VERSION
$ZLIB_VERSION = "1.3.2"
$ABSEIL_VERSION = "20250512.1"
$PROTOBUF_VERSION = "35.1"
$CURL_VERSION = "8.21.0"
$NLOHMANN_JSON_VERSION = "3.12.0"
$OPENTELEMETRY_PROTO_VERSION = "1.11.0"
$OPENTELEMETRY_CPP_VERSION = "1.30.0"

$THIRD_PARTY_DIRECTORY = ".\thirdparties"

$THIRD_PARTY_DOWNLOADED = "$THIRD_PARTY_DIRECTORY\downloaded"
$THIRD_PARTY_COMPILED = "$THIRD_PARTY_DIRECTORY\compiled"

$PREFIX = "C:\Program Files"

function showHelp {
    Write-Host "Usage: .\library_tool.ps1 [capnp|libuv|openssl|zlib|abseil|protobuf|curl|nlohmann_json|opentelemetry_cpp] [download|compile|install] [--prefix=DIR]"
    exit 1
}

function exitOnError {
    param([scriptblock]$command)
    & $command
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $command"
    }
}

function getVisualStudioCMakeGenerator {
    $visualStudioVersion = $env:VisualStudioVersion

    if ($visualStudioVersion -match '^18\.') {
        return "Visual Studio 18 2026"
    }

    if ($visualStudioVersion -match '^17\.') {
        return "Visual Studio 17 2022"
    }

    return "Visual Studio 17 2022"
}

function downloadTarGz($url, $folderName) {
    exitOnError { curl.exe --retry 100 --retry-max-time 3600 -L $url -o "$THIRD_PARTY_DOWNLOADED\$folderName.tar.gz" }
    Write-Host "Downloaded $folderName into $THIRD_PARTY_DOWNLOADED\$folderName.tar.gz"
}

function extractTarGz($folderName) {
    Remove-Item -Path "$THIRD_PARTY_COMPILED\$folderName" -Recurse -Force -ErrorAction SilentlyContinue
    exitOnError { tar -xzvf "$THIRD_PARTY_DOWNLOADED\$folderName.tar.gz" -C "$THIRD_PARTY_COMPILED" }
}

# A static Release build against the release DLL runtime, which the Python extensions link
function cmakeCompile($folderName, [string[]]$cmakeArguments) {
    $oldDir = Get-Location
    Set-Location -Path "$THIRD_PARTY_COMPILED\$folderName"
    exitOnError {
        cmake -G "$CMAKE_GENERATOR" -B build `
            -DCMAKE_INSTALL_PREFIX="$PREFIX" `
            -DCMAKE_PREFIX_PATH="$PREFIX" `
            -DCMAKE_CXX_STANDARD=17 `
            -DCMAKE_POLICY_DEFAULT_CMP0091=NEW `
            -DCMAKE_MSVC_RUNTIME_LIBRARY=MultiThreadedDLL `
            -DBUILD_SHARED_LIBS=OFF `
            -DBUILD_TESTING=OFF `
            @cmakeArguments
    }
    exitOnError { cmake --build build --config Release -j $NUM_CORES }
    Write-Host "Compiled $folderName into $THIRD_PARTY_COMPILED\$folderName"
    Set-Location $oldDir
}

function cmakeInstall($folderName) {
    $oldDir = Get-Location
    Set-Location -Path "$THIRD_PARTY_COMPILED\$folderName"
    exitOnError { cmake --install build --config Release --prefix $PREFIX }
    Write-Host "Installed $folderName into $PREFIX"
    Set-Location $oldDir
}

# Download, extract and build, or install, one CMake library
function cmakeLibrary($folderName, $url, [string[]]$cmakeArguments) {
    if ($action -eq "download") {
        downloadTarGz $url $folderName
    }
    elseif ($action -eq "compile") {
        extractTarGz $folderName
        cmakeCompile $folderName $cmakeArguments
    }
    elseif ($action -eq "install") {
        cmakeInstall $folderName
    }
    else {
        Write-Host "Argument needs to be download or compile or install"
        showHelp
    }
}

# Parse optional --prefix argument from $args
foreach ($arg in $args)
{
    if ($arg -match "^--prefix=(.+)$")
    {
        $PREFIX = $matches[1]
    }
}

# Get the number of cores
$NUM_CORES = [Environment]::ProcessorCount

[Environment]::SetEnvironmentVariable("Path",
        [Environment]::GetEnvironmentVariable("Path",
                [EnvironmentVariableTarget]::Machine) + ";$PREFIX",
        [EnvironmentVariableTarget]::Machine)

# Main logic
if ($args.Count -lt 2)
{
    showHelp
}

$dependency = $args[0]
$action = $args[1]

if ($action -eq "download")
{
    mkdir "$THIRD_PARTY_DOWNLOADED" -Force
}
elseif ($action -eq "compile")
{
    mkdir "$THIRD_PARTY_COMPILED" -Force
}

$CMAKE_GENERATOR = getVisualStudioCMakeGenerator
Write-Host "Using CMake generator: $CMAKE_GENERATOR"

# Download, compile, or install Cap'n Proto
if ($dependency -eq "capnp")
{
    $CAPNP_FOLDER_NAME = "capnproto-c++-$CAPNP_VERSION"
    $CAPNP_URL = "https://capnproto.org/$CAPNP_FOLDER_NAME.tar.gz"

    if ($action -eq "download")
    {
        downloadTarGz $CAPNP_URL $CAPNP_FOLDER_NAME
    }
    elseif ($action -eq "compile")
    {
        extractTarGz $CAPNP_FOLDER_NAME

        # Configure and build with Visual Studio using CMake
        $oldDir = Get-Location
        Set-Location -Path "$THIRD_PARTY_COMPILED\$CAPNP_FOLDER_NAME"
        exitOnError {
            cmake -G "$CMAKE_GENERATOR" -B build `
                -DCMAKE_INSTALL_PREFIX="$PREFIX" `
                -DCMAKE_INSTALL_LIBDIR=lib `
                -DBUILD_TESTING=OFF
        }
        exitOnError { cmake --build build --config Release }
        Write-Host "Compiled capnp into $THIRD_PARTY_COMPILED\$CAPNP_FOLDER_NAME"
        Set-Location $oldDir
    }
    elseif ($action -eq "install")
    {
        $oldDir = Get-Location
        Set-Location -Path "$THIRD_PARTY_COMPILED\$CAPNP_FOLDER_NAME"
        exitOnError { cmake --install build --config Release --prefix $PREFIX }

        $capnpConfigDirectory = Join-Path $PREFIX "lib\cmake\CapnProto"
        $capnpBuildConfigDirectory = Join-Path (Get-Location) "build\cmake"

        if (-not (Test-Path (Join-Path $capnpConfigDirectory "CapnProtoConfig.cmake")))
        {
            mkdir $capnpConfigDirectory -Force | Out-Null
            Copy-Item "$capnpBuildConfigDirectory\CapnProto*.cmake" -Destination $capnpConfigDirectory -Force
            Write-Host "Copied Cap'n Proto CMake package files into $capnpConfigDirectory"
        }

        Write-Host "Installed capnp into $PREFIX"
        Set-Location $oldDir
    }
    else
    {
        Write-Host "Argument needs to be download or compile or install"
        showHelp
    }
}

# Download, compile, or install libuv
elseif ($dependency -eq "libuv")
{
    $UV_FOLDER_NAME = "libuv-$UV_VERSION"
    $UV_URL = "https://github.com/libuv/libuv/archive/refs/tags/v$UV_VERSION.tar.gz"

    if ($action -eq "download")
    {
        downloadTarGz $UV_URL $UV_FOLDER_NAME
    }
    elseif ($action -eq "compile")
    {
        extractTarGz $UV_FOLDER_NAME

        # Configure and build with Visual Studio using CMake
        $oldDir = Get-Location
        Set-Location -Path "$THIRD_PARTY_COMPILED\$UV_FOLDER_NAME"
        exitOnError {
            cmake -G "$CMAKE_GENERATOR" -B build `
                -DCMAKE_INSTALL_PREFIX="$PREFIX" `
                -DBUILD_TESTING=OFF
        }
        exitOnError { cmake --build build --config Release }
        Write-Host "Compiled libuv into $THIRD_PARTY_COMPILED\$UV_FOLDER_NAME"
        Set-Location $oldDir
    }
    elseif ($action -eq "install")
    {
        $oldDir = Get-Location
        Set-Location -Path "$THIRD_PARTY_COMPILED\$UV_FOLDER_NAME"
        exitOnError { cmake --install build --config Release }
        Write-Host "Installed libuv into $PREFIX"
        Set-Location $oldDir
    }
    else
    {
        Write-Host "Argument needs to be download or compile or install"
        showHelp
    }
}

# Download, compile, or install OpenSSL
elseif ($dependency -eq "openssl")
{
    $OPENSSL_FOLDER_NAME = "openssl-$OPENSSL_VERSION"
    $OPENSSL_URL = "https://github.com/openssl/openssl/releases/download/openssl-$OPENSSL_VERSION/$OPENSSL_FOLDER_NAME.tar.gz"

    if ($action -eq "download")
    {
        downloadTarGz $OPENSSL_URL $OPENSSL_FOLDER_NAME
    }
    elseif ($action -eq "compile")
    {
        extractTarGz $OPENSSL_FOLDER_NAME

        $oldDir = Get-Location
        Set-Location -Path "$THIRD_PARTY_COMPILED\$OPENSSL_FOLDER_NAME"
        exitOnError {
            perl Configure VC-WIN64A --prefix="$PREFIX" --libdir=lib no-tests no-shared
        }
        exitOnError { nmake }
        Write-Host "Compiled OpenSSL into $THIRD_PARTY_COMPILED\$OPENSSL_FOLDER_NAME"
        Set-Location $oldDir
    }
    elseif ($action -eq "install")
    {
        $oldDir = Get-Location
        Set-Location -Path "$THIRD_PARTY_COMPILED\$OPENSSL_FOLDER_NAME"
        exitOnError { nmake install_sw }
        Write-Host "Installed OpenSSL into $PREFIX"
        Set-Location $oldDir
    }
    else
    {
        Write-Host "Argument needs to be download or compile or install"
        showHelp
    }
}

elseif ($dependency -eq "zlib")
{
    cmakeLibrary "zlib-$ZLIB_VERSION" "https://github.com/madler/zlib/archive/refs/tags/v$ZLIB_VERSION.tar.gz" `
        @("-DZLIB_BUILD_EXAMPLES=OFF", "-DZLIB_BUILD_SHARED=OFF")
}

elseif ($dependency -eq "abseil")
{
    cmakeLibrary "abseil-cpp-$ABSEIL_VERSION" "https://github.com/abseil/abseil-cpp/archive/refs/tags/$ABSEIL_VERSION.tar.gz" `
        @("-DABSL_PROPAGATE_CXX_STD=ON", "-DABSL_BUILD_TESTING=OFF", "-DABSL_MSVC_STATIC_RUNTIME=OFF")
}

elseif ($dependency -eq "protobuf")
{
    cmakeLibrary "protobuf-$PROTOBUF_VERSION" `
        "https://github.com/protocolbuffers/protobuf/releases/download/v$PROTOBUF_VERSION/protobuf-$PROTOBUF_VERSION.tar.gz" `
        @("-Dprotobuf_BUILD_TESTS=OFF", "-Dprotobuf_ABSL_PROVIDER=package", "-Dprotobuf_ZLIB_PROVIDER=package",
          "-Dprotobuf_MSVC_STATIC_RUNTIME=OFF", "-Dprotobuf_INSTALL=ON")
}

elseif ($dependency -eq "curl")
{
    # HTTP(S) only, with the OpenSSL and zlib built above: the OTLP/HTTP exporter needs nothing else
    cmakeLibrary "curl-$CURL_VERSION" "https://curl.se/download/curl-$CURL_VERSION.tar.gz" `
        @("-DBUILD_CURL_EXE=OFF", "-DBUILD_LIBCURL_DOCS=OFF", "-DBUILD_MISC_DOCS=OFF", "-DENABLE_CURL_MANUAL=OFF",
          "-DHTTP_ONLY=ON", "-DCURL_USE_OPENSSL=ON", "-DOPENSSL_ROOT_DIR=$PREFIX", "-DCURL_ZLIB=ON",
          "-DCURL_BROTLI=OFF", "-DCURL_ZSTD=OFF", "-DCURL_USE_LIBPSL=OFF", "-DCURL_USE_LIBSSH2=OFF",
          "-DUSE_NGHTTP2=OFF", "-DUSE_LIBIDN2=OFF")
}

elseif ($dependency -eq "nlohmann_json")
{
    cmakeLibrary "json-$NLOHMANN_JSON_VERSION" "https://github.com/nlohmann/json/archive/refs/tags/v$NLOHMANN_JSON_VERSION.tar.gz" `
        @("-DJSON_BuildTests=OFF", "-DJSON_Install=ON")
}

elseif ($dependency -eq "opentelemetry_cpp")
{
    $OPENTELEMETRY_CPP_FOLDER_NAME = "opentelemetry-cpp-$OPENTELEMETRY_CPP_VERSION"
    $OPENTELEMETRY_PROTO_FOLDER_NAME = "opentelemetry-proto-$OPENTELEMETRY_PROTO_VERSION"

    if ($action -eq "download")
    {
        downloadTarGz "https://github.com/open-telemetry/opentelemetry-cpp/archive/refs/tags/v$OPENTELEMETRY_CPP_VERSION.tar.gz" `
            $OPENTELEMETRY_CPP_FOLDER_NAME
        downloadTarGz "https://github.com/open-telemetry/opentelemetry-proto/archive/refs/tags/v$OPENTELEMETRY_PROTO_VERSION.tar.gz" `
            $OPENTELEMETRY_PROTO_FOLDER_NAME
    }
    elseif ($action -eq "compile")
    {
        extractTarGz $OPENTELEMETRY_CPP_FOLDER_NAME
        extractTarGz $OPENTELEMETRY_PROTO_FOLDER_NAME
        $protoPath = (Resolve-Path "$THIRD_PARTY_COMPILED\$OPENTELEMETRY_PROTO_FOLDER_NAME").Path
        # only the SDK and the OTLP/HTTP exporter; the proto sources come from the tarball, not a git clone
        cmakeCompile $OPENTELEMETRY_CPP_FOLDER_NAME `
            @("-DOTELCPP_PROTO_PATH=$protoPath", "-DWITH_OTLP_HTTP=ON", "-DWITH_OTLP_GRPC=OFF", "-DWITH_OTLP_FILE=OFF",
              "-DWITH_OTLP_HTTP_COMPRESSION=ON", "-DWITH_EXAMPLES=OFF", "-DWITH_BENCHMARK=OFF", "-DWITH_FUNC_TESTS=OFF",
              "-DOPENTELEMETRY_INSTALL=ON")
    }
    elseif ($action -eq "install")
    {
        cmakeInstall $OPENTELEMETRY_CPP_FOLDER_NAME
    }
    else
    {
        Write-Host "Argument needs to be download or compile or install"
        showHelp
    }
}

else {
    showHelp
}
