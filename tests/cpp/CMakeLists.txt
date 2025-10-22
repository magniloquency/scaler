# this fetches Google Test, so it must be included first.
if(LINUX OR APPLE)
	add_subdirectory(object_storage)
else()
	message(WARNING "Not building OSS tests, as it's not supported on this system currently!")
endif()

if (LINUX OR APPLE)
    add_subdirectory(ymq)
else()
    message(WARNING "Not building YMQ tests, as it's not supported on this system currently!")
endif()
