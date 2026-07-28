#pragma once

#include <string>
#include <cstdint>

struct AAssetManager;

bool init_yolov8_native_model(AAssetManager* mgr, const std::string& model_name);
std::string run_yolov8_style_detection(const uint8_t* frame, int width, int height);
