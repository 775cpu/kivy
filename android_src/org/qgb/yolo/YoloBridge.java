package org.qgb.yolo;

import android.content.Context;
import android.util.Log;

public class YoloBridge {
    private static final String TAG = "YoloBridge";
    private static boolean sLibraryLoaded = false;

    static {
        try {
            Log.i(TAG, "Attempting to load libyolo_jni.so");
            System.loadLibrary("yolo_jni");
            sLibraryLoaded = true;
            Log.i(TAG, "Successfully loaded libyolo_jni.so");
        } catch (Throwable t) {
            sLibraryLoaded = false;
            Log.e(TAG, "loadLibrary(yolo_jni) failed", t);
        }
    }

    public static boolean isLibraryLoaded() {
        return sLibraryLoaded;
    }

    public static String getLoadStatus() {
        return sLibraryLoaded ? "loaded" : "not_loaded";
    }

    public native String runDetection(byte[] frame, int width, int height);

    public static native boolean initModel(Context context, String modelPath);

    public static boolean initModelFromAssets(Context context) {
        try {
            return initModel(context, "yolov8n.param");
        } catch (Throwable t) {
            Log.w(TAG, "initModelFromAssets failed: " + t.getMessage());
            return false;
        }
    }
}
