# opentelemetry-cpp's SDK and OTLP/HTTP exporter, with protobuf, abseil, and curl, all static; the dependency lookups
# its package runs must find the static OpenSSL and zlib too, or the module would need their shared libraries at run time
set(OPENSSL_USE_STATIC_LIBS ON)
set(ZLIB_USE_STATIC_LIBS ON)
find_package(opentelemetry-cpp CONFIG REQUIRED COMPONENTS api sdk exporters_otlp_http)

add_library(scaler_tracing STATIC
    environment.h
    environment.cpp
    handover_queue.h
    limits.h
    limits.cpp
    log_exporter.h
    log_exporter.cpp
    log_record.h
    sampler.h
    sampler.cpp
    sdk_conversion.h
    sdk_conversion.cpp
    sdk_log_handler.h
    sdk_log_handler.cpp
    span_exporter.h
    span_exporter.cpp
    span_ids.h
    span_ids.cpp
    span_record.h
)
target_link_libraries(scaler_tracing
    PRIVATE
        opentelemetry-cpp::logs
        opentelemetry-cpp::otlp_http_exporter
        opentelemetry-cpp::otlp_http_log_record_exporter
        opentelemetry-cpp::resources
        opentelemetry-cpp::trace
)

scaler_add_python_module(
    TARGET py_native_export
    MODULE_NAME native_export
    INSTALL_DEST scaler/utility
    SOURCES
        pymod/conversion.h
        pymod/conversion.cpp
        pymod/log.h
        pymod/log.cpp
        pymod/module_state.h
        pymod/module_state.cpp
        pymod/native_export.cpp
        pymod/span_export.h
        pymod/span_export.cpp
    LINK_LIBRARIES scaler_tracing
)
