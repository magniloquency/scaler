// C
#include <stdio.h>

// First-party
#include "scaler/io/ymq/io_context.h"
#include "scaler/io/ymq/io_socket.h"
#include "scaler/io/ymq/typedefs.h"

// Goal:
// Make sure we can write an echo server with ymq in C++, pretend there is a language barrier, to mimic
// the behavior as if we are running with Python
// We should of course provide an echo client.

int main() {
    IOContext context;
    std::shared_ptr<IOSocket> socket = context.createIOSocket("ServerSocket", IOSocketType::Dealer);

    printf("Successfully created socket, sleep for 2 secs to sync.\n");
    sleep(2);

    auto callback = [socket](Message msg) {
        printf("user provided callback invoked\n");
        printf("Prepare sending messages back\n");
        socket->sendMessage(msg, [](int) {});
    };

    while (true) {
        printf("Try to recv a message\n");
        sleep(10);
        socket->recvMessage(callback);
        printf("I am sleeping...\n");
        // here we should somehow wait until callback is executed
        sleep(100);
    }
}
