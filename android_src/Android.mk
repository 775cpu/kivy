LOCAL_PATH := $(call my-dir)
include $(CLEAR_VARS)
LOCAL_MODULE := yolo_jni
LOCAL_SRC_FILES := jni/yolo_jni.cpp
LOCAL_LDLIBS := -llog
include $(BUILD_SHARED_LIBRARY)
