package org.qgb.ble;

public interface GattListener {
    void onConnectionStateChange(int status, int newState);
    void onMtuChanged(int mtu, int status); // NEW: MTU Negotiation callback
    void onServicesDiscovered(int status);
    void onCharacteristicWrite(int status);
    void onCharacteristicChanged(byte[] value);
    void onDescriptorWrite(int status);
}