
// C
#include <arpa/inet.h>
#include <netinet/in.h>
#include <stdio.h>

// First-party
#include <string.h>

#include "scaler/io/ymq/io_context.h"
#include "scaler/io/ymq/io_socket.h"
#include "scaler/io/ymq/typedefs.h"

const char* address = "ServerSocket";
const char* payload = "Hello from the other end!";

int main() {
    IOContext context;
    std::shared_ptr<IOSocket> clientSocket = context.createIOSocket("ClientSocket", IOSocketType::Uninit);
    printf("Socket created, sleep 2 secs to sync\n");
    sleep(2);

    clientSocket->connectTo("tcp://127.0.0.1:8080", [](int) {});
    printf("Socket connected, sleep 2 secs to sync\n");
    sleep(2);

    auto sendMessageCallback = [](int n) { printf("n = %d\n", n); };

    while (true) {
        // get a line from stdin
        Message message;

        message.address = Bytes {
            (char*)address,
            strlen(address),
            Ownership::Borrowed,
        };

        message.payload = Bytes {
            (char*)payload,
            strlen(payload),
            Ownership::Borrowed,
        };

        clientSocket->sendMessage(std::move(message), std::move(sendMessageCallback));

        printf("I am sleeping...\n");
        sleep(100);
        // clientSocket->recvMessage(std::function<void (Message)> callback);
    }
}
