cmake_minimum_required(VERSION 3.10)
project(yolo_jni CXX)

set(OpenCV_DIR ${CMAKE_CURRENT_SOURCE_DIR}/opencv-mobile-4.10.0-android/sdk/native/jni)
set(ncnn_DIR ${CMAKE_CURRENT_SOURCE_DIR}/ncnn-20240410-android-vulkan/arm64-v8a/lib/cmake/ncnn)

find_package(OpenCV REQUIRED core imgproc)
find_package(ncnn REQUIRED)

add_library(yolo_jni SHARED
    yolo_jni.cpp
    yolov8ncnn_bridge.cpp
    yolov8ncnn.cpp
    yolo.cpp
    ndkcamera.cpp)

find_library(log-lib log)
find_library(android-lib android)
find_library(camera2ndk-lib camera2ndk)
find_library(mediandk-lib mediandk)

target_include_directories(yolo_jni PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}
    ${CMAKE_CURRENT_SOURCE_DIR}/opencv-mobile-4.10.0-android/sdk/native/jni/include)

target_link_libraries(yolo_jni PRIVATE
    ${log-lib}
    ${android-lib}
    ${camera2ndk-lib}
    ${mediandk-lib}
    ncnn
    ${OpenCV_LIBS})
