#include <gtest/gtest.h>

#include <map>
#include <string>

#include "scaler/ymq/internal/websocket_utils.h"

class WebSocketUtilsTest: public ::testing::Test {};

TEST_F(WebSocketUtilsTest, ExtractHeadersBasic)
{
    const std::string headers =
        "GET / HTTP/1.1\r\n"
        "Host: 127.0.0.1\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n"
        "Sec-WebSocket-Version: 13\r\n";

    const auto map = scaler::ymq::internal::extractHeaders(headers);
    EXPECT_EQ(map.at("host"), "127.0.0.1");
    EXPECT_EQ(map.at("upgrade"), "websocket");
    EXPECT_EQ(map.at("connection"), "Upgrade");
    EXPECT_EQ(map.at("sec-websocket-key"), "dGhlIHNhbXBsZSBub25jZQ==");
    EXPECT_EQ(map.at("sec-websocket-version"), "13");
}

TEST_F(WebSocketUtilsTest, ExtractHeadersKeysCaseInsensitive)
{
    const std::string headers =
        "HTTP/1.1 101 Switching Protocols\r\n"
        "UPGRADE: WEBSOCKET\r\n"
        "Sec-WebSocket-Accept: abc123\r\n";

    const auto map = scaler::ymq::internal::extractHeaders(headers);
    EXPECT_TRUE(map.count("upgrade"));
    EXPECT_TRUE(map.count("sec-websocket-accept"));
}

TEST_F(WebSocketUtilsTest, ExtractHeadersValuesPreserveCase)
{
    const std::string headers =
        "GET / HTTP/1.1\r\n"
        "Sec-WebSocket-Accept: AbCdEfGh==\r\n";

    const auto map = scaler::ymq::internal::extractHeaders(headers);
    EXPECT_EQ(map.at("sec-websocket-accept"), "AbCdEfGh==");
}

TEST_F(WebSocketUtilsTest, ExtractHeadersNoSpaceAfterColon)
{
    const std::string headers =
        "GET / HTTP/1.1\r\n"
        "Upgrade:websocket\r\n"
        "Connection:Upgrade\r\n";

    const auto map = scaler::ymq::internal::extractHeaders(headers);
    EXPECT_EQ(map.at("upgrade"), "websocket");
    EXPECT_EQ(map.at("connection"), "Upgrade");
}

TEST_F(WebSocketUtilsTest, ExtractHeadersEmptyOrRequestLineOnly)
{
    EXPECT_TRUE(scaler::ymq::internal::extractHeaders("").empty());
    EXPECT_TRUE(scaler::ymq::internal::extractHeaders("GET / HTTP/1.1").empty());
    EXPECT_TRUE(scaler::ymq::internal::extractHeaders("GET / HTTP/1.1\r\n").empty());
}

TEST_F(WebSocketUtilsTest, ExtractHeadersMissingHeaderReturnsEnd)
{
    const std::string headers =
        "GET / HTTP/1.1\r\n"
        "Upgrade: websocket\r\n";

    const auto map = scaler::ymq::internal::extractHeaders(headers);
    EXPECT_EQ(map.find("sec-websocket-key"), map.end());
}
