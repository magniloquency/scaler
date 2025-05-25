#pragma once

// C
#include <execinfo.h>

// C++
#include <string>
#include <iostream>
#include <source_location>
#include <cstring>
#include <cstdlib>

using Errno = int;

void print_trace(void) {
    void* array[10];
    char** strings;
    int size, i;

    size    = backtrace(array, 10);
    strings = backtrace_symbols(array, size);
    if (strings != NULL) {
        printf("Obtained %d stack frames.\n", size);
        for (i = 0; i < size; i++)
            printf("%s\n", strings[i]);
    }

    free(strings);
}

// this is an unrecoverable error that exits the program
// prints a message plus the source location
[[noreturn]] void panic(std::string message, const std::source_location& location = std::source_location::current()) {
    auto file_name = std::string(location.file_name());
    file_name      = file_name.substr(file_name.find_last_of("/") + 1);

    std::cout << "panic at " << file_name << ":" << location.line() << ":" << location.column() << " in function ["
              << location.function_name() << "]: " << message << std::endl;

    print_trace();

    std::abort();
}

uint8_t* datadup(const uint8_t* data, size_t len) {
    uint8_t* dup = new uint8_t[len];
    std::memcpy(dup, data, len);
    return dup;
}
