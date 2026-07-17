package org.qgb.ble;

public interface ScanListener {
    void onDeviceFound(String address, String name, int rssi);
    void onScanFailed(int errorCode);
    void onScanError(String message);
}
