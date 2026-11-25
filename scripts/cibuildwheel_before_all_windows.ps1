$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$prefix = Join-Path $env:TEMP "opengris-thirdparties"
$capnpConfigPath = Join-Path $prefix "lib\cmake\CapnProto\CapnProtoConfig.cmake"

Push-Location $repoRoot

try {
    New-Item -ItemType Directory -Force -Path $prefix | Out-Null

    python.exe -m pip install --upgrade pip setuptools wheel scikit-build-core build cmake pybind11

    & (Join-Path $PSScriptRoot "library_tool.ps1") capnp download --prefix=$prefix
    & (Join-Path $PSScriptRoot "library_tool.ps1") capnp compile --prefix=$prefix
    & (Join-Path $PSScriptRoot "library_tool.ps1") capnp install --prefix=$prefix

    & (Join-Path $PSScriptRoot "library_tool.ps1") libuv download --prefix=$prefix
    & (Join-Path $PSScriptRoot "library_tool.ps1") libuv compile --prefix=$prefix
    & (Join-Path $PSScriptRoot "library_tool.ps1") libuv install --prefix=$prefix

    & (Join-Path $PSScriptRoot "library_tool.ps1") openssl download --prefix=$prefix
    & (Join-Path $PSScriptRoot "library_tool.ps1") openssl compile --prefix=$prefix
    & (Join-Path $PSScriptRoot "library_tool.ps1") openssl install --prefix=$prefix

    & (Join-Path $PSScriptRoot "library_tool.ps1") zlib download --prefix=$prefix
    & (Join-Path $PSScriptRoot "library_tool.ps1") zlib compile --prefix=$prefix
    & (Join-Path $PSScriptRoot "library_tool.ps1") zlib install --prefix=$prefix

    & (Join-Path $PSScriptRoot "library_tool.ps1") abseil download --prefix=$prefix
    & (Join-Path $PSScriptRoot "library_tool.ps1") abseil compile --prefix=$prefix
    & (Join-Path $PSScriptRoot "library_tool.ps1") abseil install --prefix=$prefix

    & (Join-Path $PSScriptRoot "library_tool.ps1") protobuf download --prefix=$prefix
    & (Join-Path $PSScriptRoot "library_tool.ps1") protobuf compile --prefix=$prefix
    & (Join-Path $PSScriptRoot "library_tool.ps1") protobuf install --prefix=$prefix

    & (Join-Path $PSScriptRoot "library_tool.ps1") curl download --prefix=$prefix
    & (Join-Path $PSScriptRoot "library_tool.ps1") curl compile --prefix=$prefix
    & (Join-Path $PSScriptRoot "library_tool.ps1") curl install --prefix=$prefix

    & (Join-Path $PSScriptRoot "library_tool.ps1") nlohmann_json download --prefix=$prefix
    & (Join-Path $PSScriptRoot "library_tool.ps1") nlohmann_json compile --prefix=$prefix
    & (Join-Path $PSScriptRoot "library_tool.ps1") nlohmann_json install --prefix=$prefix

    & (Join-Path $PSScriptRoot "library_tool.ps1") opentelemetry_cpp download --prefix=$prefix
    & (Join-Path $PSScriptRoot "library_tool.ps1") opentelemetry_cpp compile --prefix=$prefix
    & (Join-Path $PSScriptRoot "library_tool.ps1") opentelemetry_cpp install --prefix=$prefix

    if (-not (Test-Path $capnpConfigPath)) {
        Get-ChildItem $prefix -Recurse
        throw "CapnProtoConfig.cmake not installed at $capnpConfigPath"
    }

    Write-Host "Verified Cap'n Proto config at $capnpConfigPath"
}
finally {
    Pop-Location
}
