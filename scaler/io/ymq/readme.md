
# YMQ

Welcome. This file contains schedule for each day, for each person.

Each person maintains a todo and done list.

## gxu

### DONE

- CMake integration, generate C++ stuff in build dir
- Basic coroutine API
- develop the so-called coro_context and their utility DEAD
- write up interfaces(not impl) that uses coroutine DEAD

## DONE:
 - Remember (or remove) the IOSocketIdentity of closed connection
 - Basic coroutine API
 - develop the so-called coro_context and their utility DEAD
 - write up interfaces(not impl) that uses coroutine DEAD
 - Use unified file path (only include dir is project dir)
 - Start organize files that they can be compiled in one go
 - Write delayed execution utility
 - Write timed execution utility
 - IOSocket exchange identity on connected
 - General message passing assuming user passed in Message with header
 - Guaranteed message delivery
 - Retry on disconnect 
 - Delete fd from eventloop on disconnect
 - Put Recv on iosocket level because user don't know which connection it should recv from
 - LEAVE A FEW BLANKS HERE TO AVOID CONFLICT

## TODO:
 - Provide a vector-like data structure that can release memory to achieve zc
 - test the project
 - cleanup: IOSocket destructor should release resources bound to it
 - cleanup: Change InterruptiveConcurrentQueue behavior (use FileDescriptor class)
 - cleanup: Clarify Bytes ownership of send/recv messages
 - cleanup: report error when no connection with desired identity presents
 - cleanup: Error handling
 - cleanup: Do not constraint thee size of identity (current maximum being 128 bytes)
 - cleanup: Provide actual remote sockaddr in the connection class
 - cleanup: Give user more control about port/addr
 - LEAVE A FEW BLANKS HERE TO AVOID CONFLICT


## magniloquency
=======
 - support for cancel of execution
 -
 -
 -
 -
 - LEAVE A FEW BLANKS HERE TO AVOID CONFLICT


### DONE

- CPython module stub

### TODO

- ?
