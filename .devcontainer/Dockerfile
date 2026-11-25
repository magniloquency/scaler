FROM mcr.microsoft.com/devcontainers/base:noble
COPY scripts/install_system_packages.sh /tmp/install_system_packages.sh
RUN /tmp/install_system_packages.sh \
    && export DEBIAN_FRONTEND=noninteractive \
    && apt-get -y install libgraphblas-dev pandoc python3-pip python3-venv pipx tmux \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/install_system_packages.sh \
    && sudo -u vscode pipx install uv

# Absolute path so the bake (CWD=/) and dev-shell invocations (CWD=/workspaces/scaler) agree on the same staging tree.
ENV THIRD_PARTY_DIR=/opt/scaler
COPY scripts /tmp/scaler-scripts
RUN /tmp/scaler-scripts/library_tool.sh capnp download \
    && /tmp/scaler-scripts/library_tool.sh capnp compile \
    && /tmp/scaler-scripts/library_tool.sh capnp install \
    && /tmp/scaler-scripts/library_tool.sh libuv download \
    && /tmp/scaler-scripts/library_tool.sh libuv compile \
    && /tmp/scaler-scripts/library_tool.sh libuv install \
    && /tmp/scaler-scripts/library_tool.sh openssl download \
    && /tmp/scaler-scripts/library_tool.sh openssl compile \
    && /tmp/scaler-scripts/library_tool.sh openssl install \
    && /tmp/scaler-scripts/library_tool.sh zlib download \
    && /tmp/scaler-scripts/library_tool.sh zlib compile \
    && /tmp/scaler-scripts/library_tool.sh zlib install \
    && /tmp/scaler-scripts/library_tool.sh abseil download \
    && /tmp/scaler-scripts/library_tool.sh abseil compile \
    && /tmp/scaler-scripts/library_tool.sh abseil install \
    && /tmp/scaler-scripts/library_tool.sh protobuf download \
    && /tmp/scaler-scripts/library_tool.sh protobuf compile \
    && /tmp/scaler-scripts/library_tool.sh protobuf install \
    && /tmp/scaler-scripts/library_tool.sh curl download \
    && /tmp/scaler-scripts/library_tool.sh curl compile \
    && /tmp/scaler-scripts/library_tool.sh curl install \
    && /tmp/scaler-scripts/library_tool.sh nlohmann_json download \
    && /tmp/scaler-scripts/library_tool.sh nlohmann_json compile \
    && /tmp/scaler-scripts/library_tool.sh nlohmann_json install \
    && /tmp/scaler-scripts/library_tool.sh opentelemetry_cpp download \
    && /tmp/scaler-scripts/library_tool.sh opentelemetry_cpp compile \
    && /tmp/scaler-scripts/library_tool.sh opentelemetry_cpp install \
    && /tmp/scaler-scripts/library_tool.sh emsdk download \
    && /tmp/scaler-scripts/library_tool.sh emsdk compile \
    && /tmp/scaler-scripts/library_tool.sh emsdk install \
    && /tmp/scaler-scripts/library_tool.sh capnp compile --target=wasm \
    && /tmp/scaler-scripts/library_tool.sh capnp install --target=wasm \
    && /tmp/scaler-scripts/library_tool.sh libuv compile --target=wasm \
    && /tmp/scaler-scripts/library_tool.sh libuv install --target=wasm \
    && rm -rf /tmp/scaler-scripts /opt/scaler/downloaded /opt/scaler/compiled /opt/scaler/wasm/src

# Make `emcc` / `emcmake` / the bundled node available in every interactive
# shell. emsdk_env.sh derives EMSDK from BASH_SOURCE, so a single sourced
# snippet picks up wherever /opt/scaler/emsdk lives.
RUN printf '. /opt/scaler/emsdk/emsdk_env.sh > /dev/null 2>&1 || true\n' \
    > /etc/profile.d/emsdk.sh

