package org.qgb.yolo;

import android.content.Context;
import android.util.Log;

public class YoloBridge {
    private static final String TAG = "YoloBridge";

    static {
        try {
            System.loadLibrary("yolo_jni");
        } catch (Throwable t) {
            Log.w(TAG, "loadLibrary(yolo_jni) failed: " + t.getMessage());
        }
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
