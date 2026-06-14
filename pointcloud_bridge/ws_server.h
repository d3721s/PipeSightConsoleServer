// Minimal zero-dependency WebSocket server (broadcast only).
//
// Implements just enough of RFC 6455 to:
//   - accept TCP connections, perform the HTTP Upgrade handshake (SHA-1 + base64
//     of the Sec-WebSocket-Key), and
//   - send binary frames to all connected clients (server->client only; we do
//     not parse inbound application frames except to honor close/ping).
//
// It is intentionally small so the point-cloud bridge can be built with just g++
// and the standard library (plus the Angstrong SDK), no websocket dependency.
#pragma once

#include <arpa/inet.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <unistd.h>
#include <fcntl.h>

#include <cstdint>
#include <cstring>
#include <algorithm>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

namespace ws {

// --- tiny SHA-1 (public-domain style) for the handshake accept key ----------
class Sha1 {
public:
    Sha1() { reset(); }
    void update(const uint8_t *data, size_t len) {
        for (size_t i = 0; i < len; i++) {
            buffer_[bufferLen_++] = data[i];
            if (bufferLen_ == 64) { processBlock(buffer_); bufferLen_ = 0; }
            totalLen_++;
        }
    }
    void final(uint8_t out[20]) {
        uint64_t bits = totalLen_ * 8;
        uint8_t pad = 0x80;
        update(&pad, 1);
        uint8_t zero = 0;
        while (bufferLen_ != 56) update(&zero, 1);
        uint8_t lenBytes[8];
        for (int i = 0; i < 8; i++) lenBytes[7 - i] = (uint8_t)(bits >> (i * 8));
        // update() would recurse into processBlock; write length manually.
        for (int i = 0; i < 8; i++) { buffer_[bufferLen_++] = lenBytes[i]; }
        processBlock(buffer_);
        for (int i = 0; i < 5; i++) {
            out[i * 4 + 0] = (uint8_t)(h_[i] >> 24);
            out[i * 4 + 1] = (uint8_t)(h_[i] >> 16);
            out[i * 4 + 2] = (uint8_t)(h_[i] >> 8);
            out[i * 4 + 3] = (uint8_t)(h_[i]);
        }
    }
private:
    void reset() {
        h_[0] = 0x67452301; h_[1] = 0xEFCDAB89; h_[2] = 0x98BADCFE;
        h_[3] = 0x10325476; h_[4] = 0xC3D2E1F0;
        bufferLen_ = 0; totalLen_ = 0;
    }
    static uint32_t rol(uint32_t v, int b) { return (v << b) | (v >> (32 - b)); }
    void processBlock(const uint8_t *p) {
        uint32_t w[80];
        for (int i = 0; i < 16; i++)
            w[i] = (p[i*4]<<24)|(p[i*4+1]<<16)|(p[i*4+2]<<8)|(p[i*4+3]);
        for (int i = 16; i < 80; i++) w[i] = rol(w[i-3]^w[i-8]^w[i-14]^w[i-16], 1);
        uint32_t a=h_[0],b=h_[1],c=h_[2],d=h_[3],e=h_[4];
        for (int i = 0; i < 80; i++) {
            uint32_t f, k;
            if (i < 20) { f = (b & c) | ((~b) & d); k = 0x5A827999; }
            else if (i < 40) { f = b ^ c ^ d; k = 0x6ED9EBA1; }
            else if (i < 60) { f = (b & c) | (b & d) | (c & d); k = 0x8F1BBCDC; }
            else { f = b ^ c ^ d; k = 0xCA62C1D6; }
            uint32_t tmp = rol(a, 5) + f + e + k + w[i];
            e = d; d = c; c = rol(b, 30); b = a; a = tmp;
        }
        h_[0]+=a; h_[1]+=b; h_[2]+=c; h_[3]+=d; h_[4]+=e;
    }
    uint32_t h_[5];
    uint8_t buffer_[64];
    size_t bufferLen_;
    uint64_t totalLen_;
};

inline std::string base64(const uint8_t *data, size_t len) {
    static const char *tbl = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    std::string out;
    int val = 0, bits = -6;
    for (size_t i = 0; i < len; i++) {
        val = (val << 8) + data[i];
        bits += 8;
        while (bits >= 0) { out.push_back(tbl[(val >> bits) & 0x3F]); bits -= 6; }
    }
    if (bits > -6) out.push_back(tbl[((val << 8) >> (bits + 8)) & 0x3F]);
    while (out.size() % 4) out.push_back('=');
    return out;
}

class Server {
public:
    // Start listening on port; spawns an accept thread. Returns false on error.
    bool start(uint16_t port) {
        listenFd_ = ::socket(AF_INET, SOCK_STREAM, 0);
        if (listenFd_ < 0) return false;
        int yes = 1;
        setsockopt(listenFd_, SOL_SOCKET, SO_REUSEADDR, &yes, sizeof(yes));
        sockaddr_in addr{};
        addr.sin_family = AF_INET;
        addr.sin_addr.s_addr = htonl(INADDR_ANY);
        addr.sin_port = htons(port);
        if (::bind(listenFd_, (sockaddr *)&addr, sizeof(addr)) < 0) return false;
        if (::listen(listenFd_, 8) < 0) return false;
        running_ = true;
        acceptThread_ = std::thread([this] { acceptLoop(); });
        return true;
    }

    void stop() {
        running_ = false;
        if (listenFd_ >= 0) { ::shutdown(listenFd_, SHUT_RDWR); ::close(listenFd_); listenFd_ = -1; }
        if (acceptThread_.joinable()) acceptThread_.join();
        std::lock_guard<std::mutex> lk(clientsMtx_);
        for (int fd : clients_) ::close(fd);
        clients_.clear();
    }

    int clientCount() {
        std::lock_guard<std::mutex> lk(clientsMtx_);
        return (int)clients_.size();
    }

    // Broadcast a binary message to all clients. Drops clients that error out.
    void broadcastBinary(const uint8_t *data, size_t len) {
        std::vector<uint8_t> frame;
        encodeFrame(0x2 /*binary*/, data, len, frame);
        std::vector<int> dead;
        std::lock_guard<std::mutex> lk(clientsMtx_);
        for (int fd : clients_) {
            if (!sendAll(fd, frame.data(), frame.size())) dead.push_back(fd);
        }
        for (int fd : dead) {
            ::close(fd);
            clients_.erase(std::remove(clients_.begin(), clients_.end(), fd), clients_.end());
        }
    }

private:
    void acceptLoop() {
        while (running_) {
            sockaddr_in cli{};
            socklen_t cl = sizeof(cli);
            int fd = ::accept(listenFd_, (sockaddr *)&cli, &cl);
            if (fd < 0) { if (!running_) break; continue; }
            if (handshake(fd)) {
                std::lock_guard<std::mutex> lk(clientsMtx_);
                clients_.push_back(fd);
            } else {
                ::close(fd);
            }
        }
    }

    bool handshake(int fd) {
        char buf[4096];
        ssize_t n = ::recv(fd, buf, sizeof(buf) - 1, 0);
        if (n <= 0) return false;
        buf[n] = 0;
        std::string req(buf);
        std::string key = headerValue(req, "Sec-WebSocket-Key:");
        if (key.empty()) return false;
        std::string accept = key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11";
        Sha1 sha;
        sha.update((const uint8_t *)accept.data(), accept.size());
        uint8_t digest[20];
        sha.final(digest);
        std::string acceptKey = base64(digest, 20);
        std::string resp =
            "HTTP/1.1 101 Switching Protocols\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            "Sec-WebSocket-Accept: " + acceptKey + "\r\n\r\n";
        return sendAll(fd, (const uint8_t *)resp.data(), resp.size());
    }

    static std::string headerValue(const std::string &req, const char *name) {
        size_t p = req.find(name);
        if (p == std::string::npos) return "";
        p += strlen(name);
        while (p < req.size() && (req[p] == ' ' || req[p] == '\t')) p++;
        size_t e = req.find("\r\n", p);
        if (e == std::string::npos) return "";
        return req.substr(p, e - p);
    }

    static void encodeFrame(uint8_t opcode, const uint8_t *data, size_t len, std::vector<uint8_t> &out) {
        out.push_back(0x80 | opcode); // FIN + opcode
        if (len < 126) {
            out.push_back((uint8_t)len);
        } else if (len <= 0xFFFF) {
            out.push_back(126);
            out.push_back((uint8_t)(len >> 8));
            out.push_back((uint8_t)(len));
        } else {
            out.push_back(127);
            for (int i = 7; i >= 0; i--) out.push_back((uint8_t)(len >> (i * 8)));
        }
        out.insert(out.end(), data, data + len);
    }

    static bool sendAll(int fd, const uint8_t *data, size_t len) {
        size_t sent = 0;
        while (sent < len) {
            ssize_t n = ::send(fd, data + sent, len - sent, MSG_NOSIGNAL);
            if (n <= 0) return false;
            sent += (size_t)n;
        }
        return true;
    }

    int listenFd_ = -1;
    bool running_ = false;
    std::thread acceptThread_;
    std::mutex clientsMtx_;
    std::vector<int> clients_;
};

} // namespace ws
