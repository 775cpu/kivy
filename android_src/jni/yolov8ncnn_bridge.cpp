#include "yolov8ncnn_bridge.h"

#include <android/asset_manager.h>
#include <android/log.h>

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

#define LOG_TAG "YoloJNIBridge"

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
    __android_log_print(ANDROID_LOG_INFO, LOG_TAG, "init_yolov8_native_model: model=%s mgr=%p", model_name.c_str(), mgr);
    if (!mgr) {
        __android_log_print(ANDROID_LOG_ERROR, LOG_TAG, "init_yolov8_native_model: asset manager is null");
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
    __android_log_print(ANDROID_LOG_INFO, LOG_TAG, "init_yolov8_native_model: load ret=%d", ret);
    if (ret != 0) {
        delete g_yolo;
        g_yolo = nullptr;
        return false;
    }

    return true;
}

std::string run_yolov8_style_detection(const uint8_t* frame, int width, int height) {
    __android_log_print(ANDROID_LOG_INFO, LOG_TAG, "run_yolov8_style_detection: start w=%d h=%d frame=%p", width, height, frame);
    if (!frame || width <= 0 || height <= 0 || !g_yolo) {
        __android_log_print(ANDROID_LOG_WARN, LOG_TAG, "run_yolov8_style_detection: skip due to invalid input or model not loaded");
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

    std::string result = build_json(boxes);
    __android_log_print(ANDROID_LOG_INFO, LOG_TAG, "run_yolov8_style_detection: result=%s", result.c_str());
    return result;
}
