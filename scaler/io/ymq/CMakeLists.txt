add_library(ymq_objs OBJECT
    bytes.h
    common.h
    configuration.h

    epoll_context.h
    epoll_context.cpp

    iocp_context.h
    iocp_context.cpp

    event_loop.h

    event_loop_thread.h
    event_loop_thread.cpp

    event_manager.h
    # file_descriptor.h

    message_connection.h
    message_connection_tcp.h
    message_connection_tcp.cpp

    third_party/concurrentqueue.h
    interruptive_concurrent_queue.h

    typedefs.h

    io_context.h
    io_context.cpp

    io_socket.h
    io_socket.cpp

    tcp_server.h
    tcp_server.cpp

    tcp_client.h
    tcp_client.cpp

    tcp_operations.h

    timestamp.h

    timed_queue.h

    network_utils.h

    error.h

    logging.h

    simple_interface.h
    simple_interface.cpp
)

set(CMAKE_LIBRARY_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/scaler/io/ymq)

if(LINUX)
    # ymq python =======================================================================================================
    find_package(Python3 REQUIRED COMPONENTS Development.Module)

    message(STATUS "Python3_FOUND: ${Python3_FOUND}")
    message(STATUS "Python3_Interpreter_FOUND: ${Python3_Interpreter_FOUND}")
    message(STATUS "Python3_EXECUTABLE: ${Python3_EXECUTABLE}")
    message(STATUS "Python3_INTERPRETER_ID: ${Python3_INTERPRETER_ID}")
    message(STATUS "Python3_STDLIB: ${Python3_STDLIB}")
    message(STATUS "Python3_STDARCH: ${Python3_STDARCH}")
    message(STATUS "Python3_SITELIB: ${Python3_SITELIB}")
    message(STATUS "Python3_SITEARCH: ${Python3_SITEARCH}")
    message(STATUS "Python3_SOABI: ${Python3_SOABI}")
    message(STATUS "Python3_INCLUDE_DIRS: ${Python3_INCLUDE_DIRS}")
    message(STATUS "Python3_Development.Module_FOUND: ${Python3_Development.Module_FOUND}")
    message(STATUS "Python3_LINK_OPTIONS: ${Python3_LINK_OPTIONS}")
    message(STATUS "Python3_VERSION: ${Python3_VERSION}")

    add_library(py_ymq SHARED
        pymod_ymq/async.h
        pymod_ymq/bytes.h
        pymod_ymq/exception.h
        pymod_ymq/message.h
        pymod_ymq/io_context.h
        pymod_ymq/io_socket.h
        pymod_ymq/utils.h
        pymod_ymq/ymq.h
        pymod_ymq/ymq.cpp
    )

    # target_include_directories(py_ymq PRIVATE ${Python3_INCLUDE_DIRS})
    target_link_libraries(py_ymq PRIVATE
        $<$<CXX_COMPILER_ID:GNU,Clang>:-Wl,-Bstatic> ymq_objs
        $<$<CXX_COMPILER_ID:GNU,Clang>:-Wl,-Bdynamic>
        Python3::Module
    )

    set_target_properties(py_ymq PROPERTIES
        PREFIX ""
        OUTPUT_NAME "ymq"
        LINKER_LANGUAGE CXX
    )

    install(
        TARGETS py_ymq
        LIBRARY DESTINATION scaler/io/ymq
    )
endif()

if(WIN32)
    # ymq python =======================================================================================================

    target_link_libraries(ymq_objs PRIVATE "ws2_32")
    target_compile_definitions(ymq_objs PRIVATE _WINSOCKAPI_=) # Yes, trailing equal to guarantee empty def
endif()
