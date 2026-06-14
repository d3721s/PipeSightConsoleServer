// PipeSight point-cloud bridge.
//
// Uses the Angstrong camera SDK (CameraSrv / ICameraStatus) to receive depth
// camera frames over USB, extracts the point cloud, and broadcasts it to any
// connected browser over a minimal built-in WebSocket server (ws_server.h).
//
// Wire format (binary WebSocket frame), little-endian:
//   char[4]  magic  = "PCD1"
//   uint32   count  = number of points
//   float32  xyz[count*3]   (x,y,z per point, in the SDK's native units)
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
#include <thread>
#include <vector>

#include "as_camera_sdk_api.h"
#include "as_camera_sdk_def.h"
#include "CameraSrv.h"
#include "ws_server.h"

namespace {

constexpr uint16_t kWsPort = 9090;
// Cap points sent per frame to keep the browser/WebGL smooth. Hardware
// decimation is preferred (configured on the camera), this is a safety net.
constexpr uint32_t kMaxPoints = 60000;
// Floats per point in pointCloud.data. Verified from the first-frame log:
// size / (width*height) should equal this. xyz = 3 is the SDK default.
constexpr int kStride = 3;

ws::Server g_ws;
std::atomic<bool> g_running{true};

void handleSigint(int) { g_running = false; }

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
        const AS_Frame_s &pc = pstData->pointCloud;
        if (pc.size == 0 || pc.data == nullptr) return;

        // Log the layout on the first few frames so the stride can be confirmed.
        if (logCount_ < 3) {
            unsigned long pixels = (unsigned long)pc.width * pc.height;
            printf("[bridge] pointCloud: size=%u bytes, %ux%u (%lu px), floats=%u, floats/px=%.2f\n",
                   pc.size, pc.width, pc.height, pixels, pc.size / (unsigned)sizeof(float),
                   pixels ? (double)(pc.size / sizeof(float)) / pixels : 0.0);
            logCount_++;
        }

        if (g_ws.clientCount() == 0) return; // nobody watching; skip work

        const float *src = static_cast<const float *>(pc.data);
        uint32_t totalFloats = pc.size / sizeof(float);
        uint32_t totalPoints = totalFloats / kStride;
        if (totalPoints == 0) return;

        // Software decimation fallback: keep at most kMaxPoints by striding.
        uint32_t step = (totalPoints + kMaxPoints - 1) / kMaxPoints; // ceil
        if (step < 1) step = 1;
        uint32_t outCount = 0;

        std::vector<uint8_t> msg;
        msg.reserve(8 + (size_t)(totalPoints / step) * 3 * sizeof(float));
        msg.resize(8);
        std::memcpy(msg.data(), "PCD1", 4);

        for (uint32_t i = 0; i < totalPoints; i += step) {
            const float *p = src + (size_t)i * kStride;
            float x = p[0], y = p[1], z = p[2];
            // Skip invalid/zero points (common sentinel for "no return").
            if (x == 0.0f && y == 0.0f && z == 0.0f) continue;
            const uint8_t *xb = reinterpret_cast<const uint8_t *>(&x);
            const uint8_t *yb = reinterpret_cast<const uint8_t *>(&y);
            const uint8_t *zb = reinterpret_cast<const uint8_t *>(&z);
            msg.insert(msg.end(), xb, xb + 4);
            msg.insert(msg.end(), yb, yb + 4);
            msg.insert(msg.end(), zb, zb + 4);
            outCount++;
        }
        std::memcpy(msg.data() + 4, &outCount, 4);
        g_ws.broadcastBinary(msg.data(), msg.size());
    }

    void onCameraNewMergeFrame(AS_CAM_PTR, const AS_SDK_MERGE_s *) override {}

private:
    int logCount_ = 0;
};

} // namespace

int main() {
    std::signal(SIGINT, handleSigint);
    std::signal(SIGTERM, handleSigint);

    if (!g_ws.start(kWsPort)) {
        fprintf(stderr, "[bridge] failed to start WebSocket server on port %u\n", kWsPort);
        return 1;
    }
    printf("[bridge] WebSocket server listening on ws://0.0.0.0:%u\n", kWsPort);

    PointCloudBridge bridge;
    CameraSrv srv(&bridge);
    if (srv.start() != 0) {
        fprintf(stderr, "[bridge] CameraSrv start failed (no camera / permissions?)\n");
        g_ws.stop();
        return 1;
    }
    printf("[bridge] camera service started; waiting for frames. Ctrl-C to quit.\n");

    while (g_running) {
        std::this_thread::sleep_for(std::chrono::milliseconds(200));
    }

    printf("[bridge] shutting down...\n");
    srv.stop();
    g_ws.stop();
    return 0;
}
