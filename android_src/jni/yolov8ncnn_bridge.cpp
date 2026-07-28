#include "yolov8ncnn_bridge.h"

#include <android/asset_manager.h>

#include <algorithm>
#include <array>
#include <cmath>
#include <sstream>
#include <string>
#include <vector>

#include <opencv2/core/core.hpp>
#include <opencv2/imgproc/imgproc.hpp>

#include "yolo.h"

namespace {

struct DetectionBox {
    float x1;
    float y1;
    float x2;
    float y2;
    float conf;
    float label;
};

Yolo* g_yolo = nullptr;

std::string build_json(const std::vector<DetectionBox>& boxes) {
    std::ostringstream oss;
    oss << "[";
    for (size_t i = 0; i < boxes.size(); ++i) {
        const auto& box = boxes[i];
        if (i) oss << ",";
        oss << "{\"x1\":" << box.x1
            << ",\"y1\":" << box.y1
            << ",\"x2\":" << box.x2
            << ",\"y2\":" << box.y2
            << ",\"conf\":" << box.conf
            << ",\"label\":" << box.label << "}";
    }
    oss << "]";
    return oss.str();
}

}  // namespace

bool init_yolov8_native_model(AAssetManager* mgr, const std::string& model_name) {
    if (!mgr) {
        return false;
    }

    delete g_yolo;
    g_yolo = new Yolo();

    const char* modeltype = "n";
    if (model_name.find("yolov8s") != std::string::npos || model_name.find("s.param") != std::string::npos) {
        modeltype = "s";
    }

    const float mean_vals[3] = {103.53f, 116.28f, 123.675f};
    const float norm_vals[3] = {1.0f / 255.0f, 1.0f / 255.0f, 1.0f / 255.0f};

    const int ret = g_yolo->load(mgr, modeltype, 320, mean_vals, norm_vals, false);
    if (ret != 0) {
        delete g_yolo;
        g_yolo = nullptr;
        return false;
    }

    return true;
}

std::string run_yolov8_style_detection(const uint8_t* frame, int width, int height) {
    if (!frame || width <= 0 || height <= 0 || !g_yolo) {
        return "[]";
    }

    cv::Mat yuv(height + height / 2, width, CV_8UC1, const_cast<uint8_t*>(frame));
    cv::Mat rgb;
    cv::cvtColor(yuv, rgb, cv::COLOR_YUV2RGB_NV21);

    std::vector<Object> objects;
    g_yolo->detect(rgb, objects);

    std::vector<DetectionBox> boxes;
    boxes.reserve(objects.size());
    for (const Object& obj : objects) {
        boxes.push_back({obj.rect.x, obj.rect.y, obj.rect.x + obj.rect.width, obj.rect.y + obj.rect.height, obj.prob, static_cast<float>(obj.label)});
    }

    return build_json(boxes);
}
