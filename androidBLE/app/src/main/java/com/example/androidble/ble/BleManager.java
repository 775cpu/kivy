package com.example.androidble.ble;

import android.bluetooth.BluetoothAdapter;
import android.bluetooth.BluetoothDevice;
import android.bluetooth.BluetoothGatt;
import android.bluetooth.BluetoothGattCallback;
import android.bluetooth.BluetoothGattCharacteristic;
import android.bluetooth.BluetoothGattService;
import android.bluetooth.BluetoothManager;
import android.bluetooth.le.BluetoothLeScanner;
import android.bluetooth.le.ScanCallback;
import android.bluetooth.le.ScanFilter;
import android.bluetooth.le.ScanResult;
import android.bluetooth.le.ScanSettings;
import android.content.Context;
import android.os.Handler;
import android.os.Looper;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

public class BleManager {
    private final Context context;
    private final Handler handler = new Handler(Looper.getMainLooper());
    private final List<BleListener> listeners = new ArrayList<>();
    private BluetoothLeScanner scanner;
    private BluetoothGatt gatt;
    private BluetoothDevice connectedDevice;

    public interface BleListener {
        void onScanResult(String deviceName, String deviceAddress, int rssi);
        void onScanFailed(String message);
        void onConnected(String deviceAddress);
        void onDisconnected(String deviceAddress);
        void onCharacteristicValue(String serviceUuid, String characteristicUuid, byte[] value);
        void onError(String message);
    }

    public BleManager(Context context) {
        this.context = context.getApplicationContext();
    }

    public void addListener(BleListener listener) {
        if (listener != null && !listeners.contains(listener)) {
            listeners.add(listener);
        }
    }

    public void removeListener(BleListener listener) {
        listeners.remove(listener);
    }

    public boolean startScan() {
        BluetoothManager manager = (BluetoothManager) context.getSystemService(Context.BLUETOOTH_SERVICE);
        if (manager == null) {
            notifyError("BluetoothManager not available");
            return false;
        }
        BluetoothAdapter adapter = manager.getAdapter();
        if (adapter == null || !adapter.isEnabled()) {
            notifyError("Bluetooth is disabled");
            return false;
        }

        scanner = adapter.getBluetoothLeScanner();
        if (scanner == null) {
            notifyError("BLE scanner not available");
            return false;
        }

        ScanSettings settings = new ScanSettings.Builder()
                .setScanMode(ScanSettings.SCAN_MODE_LOW_LATENCY)
                .build();
        List<ScanFilter> filters = new ArrayList<>();

        scanner.startScan(filters, settings, new ScanCallback() {
            @Override
            public void onScanResult(int callbackType, ScanResult result) {
                BluetoothDevice device = result.getDevice();
                if (device != null) {
                    notifyScanResult(device.getName(), device.getAddress(), result.getRssi());
                }
            }

            @Override
            public void onBatchScanResults(List<ScanResult> results) {
                for (ScanResult result : results) {
                    BluetoothDevice device = result.getDevice();
                    if (device != null) {
                        notifyScanResult(device.getName(), device.getAddress(), result.getRssi());
                    }
                }
            }

            @Override
            public void onScanFailed(int errorCode) {
                notifyScanFailed("Scan failed: " + errorCode);
            }
        });
        return true;
    }

    public void stopScan() {
        if (scanner != null) {
            scanner.stopScan(new ScanCallback() {
            });
            scanner = null;
        }
    }

    public boolean connect(String address) {
        BluetoothManager manager = (BluetoothManager) context.getSystemService(Context.BLUETOOTH_SERVICE);
        if (manager == null) {
            notifyError("BluetoothManager not available");
            return false;
        }
        BluetoothAdapter adapter = manager.getAdapter();
        if (adapter == null || !adapter.isEnabled()) {
            notifyError("Bluetooth is disabled");
            return false;
        }

        BluetoothDevice device = adapter.getRemoteDevice(address);
        if (device == null) {
            notifyError("Device not found: " + address);
            return false;
        }

        stopScan();
        gatt = device.connectGatt(context, false, new BluetoothGattCallback() {
            @Override
            public void onConnectionStateChange(BluetoothGatt gatt, int status, int newState) {
                if (newState == android.bluetooth.BluetoothProfile.STATE_CONNECTED) {
                    connectedDevice = device;
                    notifyConnected(device.getAddress());
                    gatt.discoverServices();
                } else if (newState == android.bluetooth.BluetoothProfile.STATE_DISCONNECTED) {
                    notifyDisconnected(device.getAddress());
                }
            }

            @Override
            public void onServicesDiscovered(BluetoothGatt gatt, int status) {
                if (status == BluetoothGatt.GATT_SUCCESS) {
                    for (BluetoothGattService service : gatt.getServices()) {
                        for (BluetoothGattCharacteristic characteristic : service.getCharacteristics()) {
                            if ((characteristic.getProperties() & BluetoothGattCharacteristic.PROPERTY_NOTIFY) != 0) {
                                gatt.setCharacteristicNotification(characteristic, true);
                            }
                        }
                    }
                }
            }

            @Override
            public void onCharacteristicChanged(BluetoothGatt gatt, BluetoothGattCharacteristic characteristic) {
                notifyCharacteristicValue(
                        characteristic.getService().getUuid().toString(),
                        characteristic.getUuid().toString(),
                        characteristic.getValue()
                );
            }
        });
        return gatt != null;
    }

    public boolean writeCharacteristic(String serviceUuid, String characteristicUuid, byte[] value) {
        if (gatt == null || connectedDevice == null) {
            notifyError("No active connection");
            return false;
        }
        try {
            UUID service = UUID.fromString(serviceUuid);
            UUID characteristic = UUID.fromString(characteristicUuid);
            BluetoothGattService serviceObj = gatt.getService(service);
            if (serviceObj == null) {
                notifyError("Service not found: " + serviceUuid);
                return false;
            }
            BluetoothGattCharacteristic characteristicObj = serviceObj.getCharacteristic(characteristic);
            if (characteristicObj == null) {
                notifyError("Characteristic not found: " + characteristicUuid);
                return false;
            }
            characteristicObj.setValue(value);
            return gatt.writeCharacteristic(characteristicObj);
        } catch (IllegalArgumentException e) {
            notifyError("UUID format error: " + e.getMessage());
            return false;
        }
    }

    public void close() {
        if (gatt != null) {
            gatt.disconnect();
            gatt.close();
            gatt = null;
        }
        connectedDevice = null;
    }

    private void notifyScanResult(String deviceName, String deviceAddress, int rssi) {
        for (BleListener listener : listeners) {
            listener.onScanResult(deviceName, deviceAddress, rssi);
        }
    }

    private void notifyScanFailed(String message) {
        for (BleListener listener : listeners) {
            listener.onScanFailed(message);
        }
    }

    private void notifyConnected(String address) {
        for (BleListener listener : listeners) {
            listener.onConnected(address);
        }
    }

    private void notifyDisconnected(String address) {
        for (BleListener listener : listeners) {
            listener.onDisconnected(address);
        }
    }

    private void notifyCharacteristicValue(String serviceUuid, String characteristicUuid, byte[] value) {
        for (BleListener listener : listeners) {
            listener.onCharacteristicValue(serviceUuid, characteristicUuid, value);
        }
    }

    private void notifyError(String message) {
        for (BleListener listener : listeners) {
            listener.onError(message);
        }
    }
}
