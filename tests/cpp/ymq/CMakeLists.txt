add_test_executable(test_ymq test_ymq.cpp)

target_sources(test_ymq PRIVATE
	common/testing.h
	common/utils.h
	common/utils.cpp
	net/socket.h
	net/socket.cpp
	pipe/pipe.h
	pipe/pipe_common.cpp
)

if(LINUX OR APPLE)
	target_sources(test_ymq PRIVATE
		pipe/pipe_linux.cpp)
elseif(WIN32)
	target_sources(test_ymq PRIVATE
		pipe/pipe_windows.cpp)
endif()
