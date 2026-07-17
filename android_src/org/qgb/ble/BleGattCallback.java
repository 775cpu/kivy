package org.qgb.ble;

public interface BleGattCallback {
    void onConnectionStateChange(int status, int newState);
    void onServicesDiscovered(int status);
    void onCharacteristicWrite(int status);
    void onCharacteristicChanged(byte[] value);
}
