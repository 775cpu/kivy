LOCAL_PATH := $(call my-dir)
include $(CLEAR_VARS)
LOCAL_MODULE := yolo_jni
LOCAL_SRC_FILES := \
    jni/yolo_jni.cpp \
    jni/yolov8ncnn_bridge.cpp \
    jni/yolov8ncnn.cpp \
    jni/yolo.cpp \
    jni/ndkcamera.cpp
LOCAL_C_INCLUDES := \
    $(LOCAL_PATH)/jni \
    $(LOCAL_PATH)/jni/opencv-mobile-4.10.0-android/sdk/native/jni/include \
    $(LOCAL_PATH)/jni/ncnn-20240410-android-vulkan/arm64-v8a/include
LOCAL_LDLIBS := -llog -landroid -lmediandk -lcamera2ndk
LOCAL_SHARED_LIBRARIES := libopencv_core libopencv_imgproc libncnn
LOCAL_CFLAGS += -DANDROID -O2
include $(BUILD_SHARED_LIBRARY)
