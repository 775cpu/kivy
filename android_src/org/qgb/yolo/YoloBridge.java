package org.qgb.yolo;

import android.content.Context;
import android.os.Build;
import android.util.Log;

import java.io.File;
import java.util.Arrays;

public class YoloBridge {
    private static final String TAG = "YoloBridge";
    private static boolean sLibraryLoaded = false;

    private static void logLibrarySearchState(String phase) {
        String mappedName = System.mapLibraryName("yolo_jni");
        String javaLibPath = System.getProperty("java.library.path", "");
        Log.i(TAG, phase + ": trying to load " + mappedName + "; java.library.path=" + javaLibPath);
        Log.i(TAG, phase + ": ABI=" + Build.CPU_ABI + "; supportedABIs=" + Arrays.toString(Build.SUPPORTED_ABIS));

        if (javaLibPath == null || javaLibPath.isEmpty()) {
            Log.w(TAG, phase + ": java.library.path is empty");
            return;
        }

        String[] entries = javaLibPath.split(File.pathSeparator);
        for (String entry : entries) {
            if (entry == null || entry.isEmpty()) {
                continue;
            }
            File candidate = new File(entry, mappedName);
            Log.i(TAG, phase + ": candidate=" + candidate.getAbsolutePath() + "; exists=" + candidate.exists() + "; isFile=" + candidate.isFile());
        }
    }

    static {
        try {
            logLibrarySearchState("static-init");
            System.loadLibrary("yolo_jni");
            sLibraryLoaded = true;
            Log.i(TAG, "Successfully loaded libyolo_jni.so");
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
            logLibrarySearchState("initializeNativeLibrary");
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
