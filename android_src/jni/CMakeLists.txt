cmake_minimum_required(VERSION 3.10)
project(yolo_jni CXX)

add_library(yolo_jni SHARED yolo_jni.cpp)

find_library(log-lib log)

target_include_directories(yolo_jni PRIVATE ${CMAKE_CURRENT_SOURCE_DIR})

target_link_libraries(yolo_jni PRIVATE ${log-lib})
