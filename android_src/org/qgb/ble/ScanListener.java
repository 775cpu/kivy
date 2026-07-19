package org.qgb.ble;

public interface ScanListener {
    void onDeviceFound(String address, String name, int rssi);
    void onScanFailed(int errorCode);
    void onScanError(String message);
    // 新增：传递原始广播数据的十六进制字符串
    void onDeviceFoundWithRecord(String address, String name, int rssi, String recordHex);
}