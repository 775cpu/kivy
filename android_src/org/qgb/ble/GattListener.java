package org.qgb.ble;

public interface GattListener {
    void onConnectionStateChange(int status, int newState);
    void onServicesDiscovered(int status);
    void onCharacteristicWrite(int status);
    void onCharacteristicChanged(byte[] value);
    void onDescriptorWrite(int status);   // 新增
}