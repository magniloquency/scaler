add_test_executable(test_ymq test_ymq.cpp)

target_sources(test_ymq PRIVATE
	common/testing.h
	common/utils.h
	common/utils.cpp
	net/socket.h
	pipe/pipe.h
)

if(LINUX OR APPLE)
	target_sources(test_ymq PRIVATE
		pipe/pipe_linux.cpp
		net/socket_linux.cpp)
elseif(WIN32)
	target_sources(test_ymq PRIVATE
		pipe/pipe_windows.cpp
		net/socket_windows.cpp)
endif()
