package org.qgb.yolo;

import android.content.Context;
import android.os.Build;
import android.util.Log;

public class YoloBridge {
    private static final String TAG = "YoloBridge";
    private static boolean sLibraryLoaded = false;

    static {
        try {
            String mappedName = System.mapLibraryName("yolo_jni");
            String javaLibPath = System.getProperty("java.library.path", "");
            Log.i(TAG, "Attempting to load " + mappedName + "; java.library.path=" + javaLibPath);
            Log.i(TAG, "ABI=" + Build.CPU_ABI + "; supportedABIs=" + java.util.Arrays.toString(Build.SUPPORTED_ABIS));
            System.loadLibrary("yolo_jni");
            sLibraryLoaded = true;
            Log.i(TAG, "Successfully loaded " + mappedName);
        } catch (Throwable t) {
            sLibraryLoaded = false;
            Log.e(TAG, "loadLibrary(yolo_jni) failed: " + t.getClass().getName() + ": " + t.getMessage(), t);
        }
    }

    public static boolean isLibraryLoaded() {
        return sLibraryLoaded;
    }

    public static String getLoadStatus() {
        return sLibraryLoaded ? "loaded" : "not_loaded";
    }

    public static boolean initializeNativeLibrary() {
        if (sLibraryLoaded) {
            return true;
        }
        try {
            String mappedName = System.mapLibraryName("yolo_jni");
            String javaLibPath = System.getProperty("java.library.path", "");
            Log.i(TAG, "Explicitly loading " + mappedName + " from initializeNativeLibrary; java.library.path=" + javaLibPath);
            Log.i(TAG, "ABI=" + Build.CPU_ABI + "; supportedABIs=" + java.util.Arrays.toString(Build.SUPPORTED_ABIS));
            System.loadLibrary("yolo_jni");
            sLibraryLoaded = true;
            Log.i(TAG, "Explicit JNI load succeeded");
            return true;
        } catch (Throwable t) {
            sLibraryLoaded = false;
            Log.e(TAG, "Explicit JNI load failed: " + t.getClass().getName() + ": " + t.getMessage(), t);
            return false;
        }
    }

    public native String runDetection(byte[] frame, int width, int height);

    public static native boolean initModel(Context context, String modelPath);

    public static boolean initModelFromAssets(Context context) {
        boolean loaded = initializeNativeLibrary();
        if (!loaded) {
            Log.e(TAG, "Native library not available; skipping initModelFromAssets");
            return false;
        }
        try {
            return initModel(context, "yolov8n.param");
        } catch (Throwable t) {
            Log.w(TAG, "initModelFromAssets failed: " + t.getMessage(), t);
            return false;
        }
    }
}
