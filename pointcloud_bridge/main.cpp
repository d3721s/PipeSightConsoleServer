// PipeSight point-cloud bridge.
//
// Uses the Angstrong camera SDK (CameraSrv / ICameraStatus) to receive depth
// camera frames over USB, extracts the point cloud and raw depth image, and
// broadcasts them to connected browsers over minimal built-in WebSocket servers
// (ws_server.h).
//
// Wire format (binary WebSocket frame), little-endian:
//   char[4]  magic  = "PCD1"
//   uint32   count  = number of points
//   float32  xyz[count*3]   (x,y,z per point, in the SDK's native units)
//
// Depth image wire format (binary WebSocket frame), little-endian:
//   char[4]  magic  = "DPT1"
//   uint32   width
//   uint32   height
//   uint32   format = 1 for uint16 depth, 2 for float32 depth
//   uint8    payload[width*height*(format == 1 ? 2 : 4)]
//
// Build:  ./build.sh      (see build.sh in this folder)
// Run:    ./run.sh        (sets LD_LIBRARY_PATH then runs ./pointcloud_bridge)
//
// On the first few frames it logs pointCloud.size/width/height so we can confirm
// the float stride (we assume 3 floats/point = xyz; adjust STRIDE if the log
// shows otherwise).

#include <atomic>
#include <chrono>
#include <csignal>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <cmath>
#include <thread>
#include <vector>

#include "as_camera_sdk_api.h"
#include "as_camera_sdk_def.h"
#include "CameraSrv.h"
#include "ws_server.h"

namespace {

constexpr uint16_t kWsPort = 9090;
constexpr uint16_t kDepthWsPort = 9091;
// Cap points sent per frame to keep the browser/WebGL smooth. Hardware
// decimation is preferred (configured on the camera), this is a safety net.
constexpr uint32_t kMaxPoints = 30000;
constexpr auto kPointcloudInterval = std::chrono::milliseconds(66);
constexpr auto kDepthInterval = std::chrono::milliseconds(66);
// Floats per point in pointCloud.data. Verified from the first-frame log:
// size / (width*height) should equal this. xyz = 3 is the SDK default.
constexpr int kStride = 3;

ws::Server g_pointcloudWs;
ws::Server g_depthWs;
std::atomic<bool> g_running{true};

void handleSigint(int) { g_running = false; }

void appendFloat(std::vector<uint8_t> &msg, float value) {
    const uint8_t *bytes = reinterpret_cast<const uint8_t *>(&value);
    msg.insert(msg.end(), bytes, bytes + sizeof(float));
}

void appendU32(std::vector<uint8_t> &msg, uint32_t value) {
    const uint8_t *bytes = reinterpret_cast<const uint8_t *>(&value);
    msg.insert(msg.end(), bytes, bytes + sizeof(uint32_t));
}

bool appendPoint(std::vector<uint8_t> &msg, float x, float y, float z) {
    if (!std::isfinite(x) || !std::isfinite(y) || !std::isfinite(z)) return false;
    if (x == 0.0f && y == 0.0f && z == 0.0f) return false;
    appendFloat(msg, x);
    appendFloat(msg, y);
    appendFloat(msg, z);
    return true;
}

class PointCloudBridge : public ICameraStatus {
public:
    int onCameraAttached(AS_CAM_PTR, const AS_SDK_CAM_MODEL_E &) override {
        printf("[bridge] camera attached\n");
        return 0;
    }
    int onCameraDetached(AS_CAM_PTR) override {
        printf("[bridge] camera detached\n");
        return 0;
    }
    int onCameraOpen(AS_CAM_PTR) override { printf("[bridge] camera opened\n"); return 0; }
    int onCameraClose(AS_CAM_PTR) override { printf("[bridge] camera closed\n"); return 0; }
    int onCameraStart(AS_CAM_PTR) override { printf("[bridge] streaming started\n"); return 0; }
    int onCameraStop(AS_CAM_PTR) override { printf("[bridge] streaming stopped\n"); return 0; }

    void onCameraNewFrame(AS_CAM_PTR, const AS_SDK_Data_s *pstData) override {
        if (pstData == nullptr) return;
        logFrame(pstData->depthImg, pstData->pointCloud, "frame");
        if (g_depthWs.clientCount() > 0 && shouldSendDepth()) {
            broadcastDepthFrame(pstData->depthImg);
        }
        if (g_pointcloudWs.clientCount() == 0) return; // nobody watching; skip work
        if (!shouldSendPointcloud()) return;
        if (broadcastSdkPointCloud(pstData->pointCloud)) return;
        broadcastDepthAsPointCloud(pstData->depthImg);
    }

    void onCameraNewMergeFrame(AS_CAM_PTR, const AS_SDK_MERGE_s *pstData) override {
        if (pstData == nullptr) return;
        logFrame(pstData->depthImg, pstData->pointCloud, "merge");
        if (g_depthWs.clientCount() > 0 && shouldSendDepth()) {
            broadcastDepthFrame(pstData->depthImg);
        }
        if (g_pointcloudWs.clientCount() == 0) return;
        if (!shouldSendPointcloud()) return;
        if (broadcastSdkPointCloud(pstData->pointCloud)) return;
        broadcastDepthAsPointCloud(pstData->depthImg);
    }

private:
    bool shouldSendDepth() {
        return shouldSend(lastDepthSend_, kDepthInterval);
    }

    bool shouldSendPointcloud() {
        return shouldSend(lastPointcloudSend_, kPointcloudInterval);
    }

    bool shouldSend(std::chrono::steady_clock::time_point &last, std::chrono::milliseconds interval) {
        const auto now = std::chrono::steady_clock::now();
        if (last.time_since_epoch().count() != 0 && now - last < interval) return false;
        last = now;
        return true;
    }

    void logFrame(const AS_Frame_s &depth, const AS_Frame_s &pc, const char *kind) {
        if (logCount_ >= 10) return;
        unsigned long depthPixels = (unsigned long)depth.width * depth.height;
        unsigned long pcPixels = (unsigned long)pc.width * pc.height;
        printf("[bridge] %s depth: size=%u bytes, %ux%u (%lu px); pointCloud: size=%u bytes, %ux%u (%lu px)\n",
               kind, depth.size, depth.width, depth.height, depthPixels,
               pc.size, pc.width, pc.height, pcPixels);
        logCount_++;
    }

    bool broadcastSdkPointCloud(const AS_Frame_s &pc) {
        if (pc.size == 0 || pc.data == nullptr) return false;
        const float *src = static_cast<const float *>(pc.data);
        uint32_t totalFloats = pc.size / sizeof(float);
        uint32_t totalPoints = totalFloats / kStride;
        if (totalPoints == 0) return false;

        uint32_t step = (totalPoints + kMaxPoints - 1) / kMaxPoints;
        if (step < 1) step = 1;

        std::vector<uint8_t> msg;
        msg.reserve(8 + (size_t)(totalPoints / step) * 3 * sizeof(float));
        msg.resize(8);
        std::memcpy(msg.data(), "PCD1", 4);

        uint32_t outCount = 0;
        for (uint32_t i = 0; i < totalPoints; i += step) {
            const float *p = src + (size_t)i * kStride;
            if (appendPoint(msg, p[0], p[1], p[2])) outCount++;
        }
        if (outCount == 0) return false;
        std::memcpy(msg.data() + 4, &outCount, 4);
        g_pointcloudWs.broadcastBinary(msg.data(), msg.size());
        return true;
    }

    bool broadcastDepthAsPointCloud(const AS_Frame_s &depth) {
        if (depth.size == 0 || depth.data == nullptr || depth.width == 0 || depth.height == 0) {
            return false;
        }

        const uint32_t totalPixels = depth.width * depth.height;
        if (totalPixels == 0) return false;
        const bool isU16 = depth.size == totalPixels * sizeof(uint16_t);
        const bool isF32 = depth.size == totalPixels * sizeof(float);
        if (!isU16 && !isF32) return false;

        uint32_t step = (totalPixels + kMaxPoints - 1) / kMaxPoints;
        if (step < 1) step = 1;

        std::vector<uint8_t> msg;
        msg.reserve(8 + (size_t)(totalPixels / step) * 3 * sizeof(float));
        msg.resize(8);
        std::memcpy(msg.data(), "PCD1", 4);

        const float cx = (float)(depth.width - 1) * 0.5f;
        const float cy = (float)(depth.height - 1) * 0.5f;
        const float invScale = 1.0f / (float)((depth.width > depth.height) ? depth.width : depth.height);
        uint32_t outCount = 0;

        for (uint32_t i = 0; i < totalPixels; i += step) {
            float z = 0.0f;
            if (isU16) {
                uint16_t raw = static_cast<const uint16_t *>(depth.data)[i];
                if (raw == 0) continue;
                z = (float)raw * 0.001f; // common SDK depth unit: millimetres.
            } else {
                z = static_cast<const float *>(depth.data)[i];
                if (!std::isfinite(z) || z <= 0.0f) continue;
                if (z > 20.0f) z *= 0.001f;
            }

            uint32_t row = i / depth.width;
            uint32_t col = i - row * depth.width;
            float x = ((float)col - cx) * invScale * z;
            float y = -(float)((float)row - cy) * invScale * z;
            if (appendPoint(msg, x, y, z)) outCount++;
        }

        if (outCount == 0) return false;
        std::memcpy(msg.data() + 4, &outCount, 4);
        g_pointcloudWs.broadcastBinary(msg.data(), msg.size());
        return true;
    }

    bool broadcastDepthFrame(const AS_Frame_s &depth) {
        if (depth.size == 0 || depth.data == nullptr || depth.width == 0 || depth.height == 0) {
            return false;
        }

        const uint32_t totalPixels = depth.width * depth.height;
        if (totalPixels == 0) return false;
        const bool isU16 = depth.size == totalPixels * sizeof(uint16_t);
        const bool isF32 = depth.size == totalPixels * sizeof(float);
        if (!isU16 && !isF32) return false;

        const uint32_t format = isU16 ? 1 : 2;
        const size_t payloadBytes = isU16 ? (size_t)totalPixels * sizeof(uint16_t)
                                          : (size_t)totalPixels * sizeof(float);
        std::vector<uint8_t> msg;
        msg.reserve(16 + payloadBytes);
        msg.insert(msg.end(), {'D', 'P', 'T', '1'});
        appendU32(msg, depth.width);
        appendU32(msg, depth.height);
        appendU32(msg, format);
        const uint8_t *payload = static_cast<const uint8_t *>(depth.data);
        msg.insert(msg.end(), payload, payload + payloadBytes);

        g_depthWs.broadcastBinary(msg.data(), msg.size());
        return true;
    }

    int logCount_ = 0;
    std::chrono::steady_clock::time_point lastPointcloudSend_{};
    std::chrono::steady_clock::time_point lastDepthSend_{};
};

} // namespace

int main() {
    std::signal(SIGINT, handleSigint);
    std::signal(SIGTERM, handleSigint);

    if (!g_pointcloudWs.start(kWsPort)) {
        fprintf(stderr, "[bridge] failed to start WebSocket server on port %u\n", kWsPort);
        return 1;
    }
    if (!g_depthWs.start(kDepthWsPort)) {
        fprintf(stderr, "[bridge] failed to start depth WebSocket server on port %u\n", kDepthWsPort);
        g_pointcloudWs.stop();
        return 1;
    }
    printf("[bridge] point-cloud WebSocket listening on ws://0.0.0.0:%u\n", kWsPort);
    printf("[bridge] depth WebSocket listening on ws://0.0.0.0:%u\n", kDepthWsPort);

    PointCloudBridge bridge;
    CameraSrv srv(&bridge);
    if (srv.start() != 0) {
        fprintf(stderr, "[bridge] CameraSrv start failed (no camera / permissions?)\n");
        g_pointcloudWs.stop();
        g_depthWs.stop();
        return 1;
    }
    printf("[bridge] camera service started; waiting for frames. Ctrl-C to quit.\n");

    while (g_running) {
        std::this_thread::sleep_for(std::chrono::milliseconds(200));
    }

    printf("[bridge] shutting down...\n");
    srv.stop();
    g_pointcloudWs.stop();
    g_depthWs.stop();
    return 0;
}
