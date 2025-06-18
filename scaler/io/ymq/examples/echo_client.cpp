
// C
#include <arpa/inet.h>
#include <netinet/in.h>
#include <stdio.h>

// First-party
#include <string.h>

#include <cstdint>

#include "scaler/io/ymq/io_context.h"
#include "scaler/io/ymq/io_socket.h"
#include "scaler/io/ymq/typedefs.h"

const char* address = "ServerSocket";
const char* payload = "Hello from the other end!";

int main() {
    IOContext context;
    std::shared_ptr<IOSocket> clientSocket = context.createIOSocket("ClientSocket", IOSocketType::Uninit);

    const char* ip = "127.0.0.1";
    const int port = 8080;

    // Create a non-blocking socket using SOCK_NONBLOCK
    int sockfd = socket(AF_INET, SOCK_STREAM | SOCK_NONBLOCK, 0);
    if (sockfd < 0) {
        perror("socket");
        return 1;
    }

    sockaddr_in server_addr {};
    server_addr.sin_family = AF_INET;
    server_addr.sin_port   = htons(port);
    inet_pton(AF_INET, ip, &server_addr.sin_addr);
    clientSocket->connectTo(*(sockaddr*)&server_addr);
    sleep(2);

    auto sendMessageCallback = [](int n) {
        printf("n = %d\n", n);
        sleep(100);
    };

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
