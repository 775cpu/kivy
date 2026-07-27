#include <jni.h>
#include <android/log.h>
#include <vector>
#include <string>
#include <sstream>

#define LOG_TAG "YoloJNI"
#define LOGD(...) __android_log_print(ANDROID_LOG_DEBUG, LOG_TAG, __VA_ARGS__)

extern "C" {

static std::string g_last_result = "[]";

JNIEXPORT jstring JNICALL Java_org_qgb_yolo_YoloBridge_runDetection(JNIEnv* env, jobject thiz, jbyteArray frame, jint width, jint height) {
    if (frame == nullptr || width <= 0 || height <= 0) {
        return env->NewStringUTF("[]");
    }

    jsize len = env->GetArrayLength(frame);
    jbyte* data = env->GetByteArrayElements(frame, nullptr);
    if (data == nullptr || len <= 0) {
        return env->NewStringUTF("[]");
    }

    std::ostringstream oss;
    oss << "[{\"x1\":0.0,\"y1\":0.0,\"x2\":0.0,\"y2\":0.0,\"conf\":0.0,\"label\":0}]";
    g_last_result = oss.str();

    env->ReleaseByteArrayElements(frame, data, JNI_ABORT);
    return env->NewStringUTF(g_last_result.c_str());
}

JNIEXPORT jboolean JNICALL Java_org_qgb_yolo_YoloBridge_initModel(JNIEnv* env, jclass klass, jobject context, jstring modelPath) {
    return JNI_TRUE;
}

}
