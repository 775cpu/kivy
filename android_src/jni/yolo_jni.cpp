#include <jni.h>
#include <android/asset_manager_jni.h>
#include <android/log.h>
#include <array>
#include <vector>
#include <string>
#include <sstream>
#include <algorithm>
#include <cmath>

#include "yolov8ncnn_bridge.h"

#define LOG_TAG "YoloJNI"
#define LOGD(...) __android_log_print(ANDROID_LOG_DEBUG, LOG_TAG, __VA_ARGS__)

extern "C" {

static std::string g_last_result = "[]";

JNIEXPORT jint JNICALL JNI_OnLoad(JavaVM* vm, void* reserved) {
    JNIEnv* env = nullptr;
    __android_log_print(ANDROID_LOG_INFO, LOG_TAG, "JNI_OnLoad: starting, vm=%p reserved=%p", vm, reserved);
    if (vm->GetEnv(reinterpret_cast<void**>(&env), JNI_VERSION_1_6) != JNI_OK || env == nullptr) {
        __android_log_print(ANDROID_LOG_ERROR, LOG_TAG, "JNI_OnLoad failed: cannot obtain JNIEnv from JavaVM");
        return JNI_ERR;
    }
    __android_log_print(ANDROID_LOG_INFO, LOG_TAG, "JNI_OnLoad: native library loaded successfully, env=%p", env);
    return JNI_VERSION_1_6;
}

JNIEXPORT void JNICALL JNI_OnUnload(JavaVM* vm, void* reserved) {
    __android_log_print(ANDROID_LOG_INFO, LOG_TAG, "JNI_OnUnload: native library unloaded");
}

static std::vector<std::string> split(const std::string& s, char delim) {
    std::vector<std::string> out;
    std::stringstream ss(s);
    std::string item;
    while (std::getline(ss, item, delim)) {
        out.push_back(item);
    }
    return out;
}

static std::string build_result_json(const std::vector<std::array<float, 6>>& boxes) {
    std::ostringstream oss;
    oss << "[";
    for (size_t i = 0; i < boxes.size(); ++i) {
        const auto& b = boxes[i];
        if (i) oss << ",";
        oss << "{\"x1\":" << b[0]
            << ",\"y1\":" << b[1]
            << ",\"x2\":" << b[2]
            << ",\"y2\":" << b[3]
            << ",\"conf\":" << b[4]
            << ",\"label\":" << static_cast<int>(b[5]) << "}";
    }
    oss << "]";
    return oss.str();
}

namespace {

jstring run_detection_impl(JNIEnv* env, jobject thiz, jbyteArray frame, jint width, jint height) {
    if (frame == nullptr || width <= 0 || height <= 0) {
        return env->NewStringUTF("[]");
    }

    jsize len = env->GetArrayLength(frame);
    jbyte* data = env->GetByteArrayElements(frame, nullptr);
    if (data == nullptr || len <= 0) {
        return env->NewStringUTF("[]");
    }

    const int y_size = width * height;
    if (len < y_size) {
        env->ReleaseByteArrayElements(frame, data, JNI_ABORT);
        return env->NewStringUTF("[]");
    }

    const uint8_t* y_plane = reinterpret_cast<const uint8_t*>(data);
    g_last_result = run_yolov8_style_detection(y_plane, width, height);
    env->ReleaseByteArrayElements(frame, data, JNI_ABORT);
    return env->NewStringUTF(g_last_result.c_str());
}

jboolean init_model_impl(JNIEnv* env, jclass klass, jobject context, jstring modelPath) {
    __android_log_print(ANDROID_LOG_INFO, LOG_TAG, "init_model_impl: starting model init, context=%p", context);
    const char* path = env->GetStringUTFChars(modelPath, nullptr);
    if (!path) {
        __android_log_print(ANDROID_LOG_ERROR, LOG_TAG, "init_model_impl: GetStringUTFChars returned null");
        return JNI_FALSE;
    }

    const std::string model_name(path);
    env->ReleaseStringUTFChars(modelPath, path);
    __android_log_print(ANDROID_LOG_INFO, LOG_TAG, "init_model_impl: model name=%s", model_name.c_str());

    if (model_name.empty()) {
        __android_log_print(ANDROID_LOG_ERROR, LOG_TAG, "init_model_impl: model name is empty");
        return JNI_FALSE;
    }

    jclass context_class = env->FindClass("android/content/Context");
    if (context_class == nullptr) {
        __android_log_print(ANDROID_LOG_ERROR, LOG_TAG, "init_model_impl: cannot find android/content/Context");
        return JNI_FALSE;
    }

    jmethodID get_assets = env->GetMethodID(context_class, "getAssets", "()Landroid/content/res/AssetManager;");
    if (get_assets == nullptr) {
        __android_log_print(ANDROID_LOG_ERROR, LOG_TAG, "init_model_impl: cannot find Context.getAssets");
        env->DeleteLocalRef(context_class);
        return JNI_FALSE;
    }

    jobject asset_manager = env->CallObjectMethod(context, get_assets);
    env->DeleteLocalRef(context_class);
    if (asset_manager == nullptr) {
        __android_log_print(ANDROID_LOG_ERROR, LOG_TAG, "init_model_impl: asset manager is null");
        return JNI_FALSE;
    }

    AAssetManager* mgr = AAssetManager_fromJava(env, asset_manager);
    env->DeleteLocalRef(asset_manager);
    if (mgr == nullptr) {
        __android_log_print(ANDROID_LOG_ERROR, LOG_TAG, "init_model_impl: AAssetManager_fromJava returned null");
        return JNI_FALSE;
    }

    bool ok = init_yolov8_native_model(mgr, model_name);
    __android_log_print(ANDROID_LOG_INFO, LOG_TAG, "init_model_impl: init_yolov8_native_model result=%s for model=%s", ok ? "true" : "false", model_name.c_str());
    return ok ? JNI_TRUE : JNI_FALSE;
}

}  // namespace

JNIEXPORT jstring JNICALL Java_org_qgb_yolo_YoloBridge_runDetection___3BII(JNIEnv* env, jobject thiz, jbyteArray frame, jint width, jint height) {
    return run_detection_impl(env, thiz, frame, width, height);
}

JNIEXPORT jstring JNICALL Java_org_qgb_yolo_YoloBridge_runDetection(JNIEnv* env, jobject thiz, jbyteArray frame, jint width, jint height) {
    return run_detection_impl(env, thiz, frame, width, height);
}

JNIEXPORT jboolean JNICALL Java_org_qgb_yolo_YoloBridge_initModel__Landroid_content_Context_2Ljava_lang_String_2(JNIEnv* env, jclass klass, jobject context, jstring modelPath) {
    return init_model_impl(env, klass, context, modelPath);
}

JNIEXPORT jboolean JNICALL Java_org_qgb_yolo_YoloBridge_initModel(JNIEnv* env, jclass klass, jobject context, jstring modelPath) {
    return init_model_impl(env, klass, context, modelPath);
}

}
