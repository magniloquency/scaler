add_test_executable(test_ymq test_ymq.cpp)

target_sources(test_ymq PRIVATE
	common/testing.h
	common/utils.h
	net/socket.h
	net/socket.cpp
	pipe/pipe.h
	pipe/pipe.cpp
)

add_test_executable(test_ymq_logging test_ymq_logging.cpp)
