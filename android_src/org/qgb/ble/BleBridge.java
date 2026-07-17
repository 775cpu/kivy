package org.qgb.ble;

import android.bluetooth.BluetoothAdapter;
import android.bluetooth.BluetoothDevice;
import android.bluetooth.BluetoothGatt;
import android.bluetooth.BluetoothGattCallback;
import android.bluetooth.BluetoothGattCharacteristic;
import android.bluetooth.BluetoothManager;
import android.bluetooth.le.BluetoothLeScanner;
import android.bluetooth.le.ScanCallback;
import android.bluetooth.le.ScanResult;
import android.content.Context;
import java.util.List;

public final class BleBridge {
    private BleBridge() {
    }
    public static final class ScanSession {
        private final BluetoothLeScanner scanner;
        private final ScanCallback callback;

        private ScanSession(BluetoothLeScanner scanner, ScanCallback callback) {
            this.scanner = scanner;
            this.callback = callback;
        }

        public void stop() {
            if (scanner != null && callback != null) {
                try {
                    scanner.stopScan(callback);
                } catch (Throwable ignored) {
                }
            }
        }
    }

    public static ScanSession startScan(Context context, ScanListener listener) {
        if (context == null || listener == null) {
            return null;
        }
        try {
            BluetoothManager manager = (BluetoothManager) context.getSystemService(Context.BLUETOOTH_SERVICE);
            if (manager == null) {
                listener.onScanError("BluetoothManager is null");
                return null;
            }
            BluetoothAdapter adapter = manager.getAdapter();
            if (adapter == null) {
                listener.onScanError("BluetoothAdapter is null");
                return null;
            }
            if (!adapter.isEnabled()) {
                listener.onScanError("Bluetooth is disabled");
                return null;
            }
            BluetoothLeScanner scanner = adapter.getBluetoothLeScanner();
            if (scanner == null) {
                listener.onScanError("BluetoothLeScanner is null");
                return null;
            }
            ScanCallback callback = new ScanCallback() {
                @Override
                public void onScanResult(int callbackType, ScanResult result) {
                    if (result == null) {
                        return;
                    }
                    emitResult(result, listener);
                }

                @Override
                public void onBatchScanResults(List<ScanResult> results) {
                    if (results == null) {
                        return;
                    }
                    for (ScanResult result : results) {
                        if (result != null) {
                            emitResult(result, listener);
                        }
                    }
                }

                @Override
                public void onScanFailed(int errorCode) {
                    listener.onScanFailed(errorCode);
                }

                private void emitResult(ScanResult result, ScanListener listener) {
                    if (listener == null) {
                        return;
                    }
                    BluetoothDevice device = result.getDevice();
                    if (device == null) {
                        return;
                    }
                    String address = device.getAddress();
                    String name = device.getName();
                    if (address == null) {
                        address = "";
                    }
                    if (name == null || name.isEmpty()) {
                        name = "Unknown Device";
                    }
                    try {
                        listener.onDeviceFound(address, name, result.getRssi());
                    } catch (Throwable ignored) {
                    }
                }
            };
            scanner.startScan(callback);
            return new ScanSession(scanner, callback);
        } catch (SecurityException exception) {
            listener.onScanError("Missing Bluetooth permission: " + exception.toString());
            return null;
        } catch (Throwable exception) {
            listener.onScanError(exception.toString());
            return null;
        }
    }

    public static BluetoothGatt connectGatt(Context context, String macAddress, boolean autoConnect, GattListener listener) {
        if (context == null || listener == null || macAddress == null) {
            return null;
        }
        try {
            BluetoothManager manager = (BluetoothManager) context.getSystemService(Context.BLUETOOTH_SERVICE);
            if (manager == null) {
                return null;
            }
            BluetoothAdapter adapter = manager.getAdapter();
            if (adapter == null || !adapter.isEnabled()) {
                return null;
            }
            BluetoothDevice device = adapter.getRemoteDevice(macAddress);
            if (device == null) {
                return null;
            }
            return device.connectGatt(context, autoConnect, new DelegateGattCallback(listener));
        } catch (IllegalArgumentException exception) {
            return null;
        } catch (SecurityException exception) {
            return null;
        } catch (Throwable exception) {
            return null;
        }
    }

    private static class DelegateGattCallback extends BluetoothGattCallback {
        private final GattListener listener;

        DelegateGattCallback(GattListener listener) {
            this.listener = listener;
        }

        @Override
        public void onConnectionStateChange(BluetoothGatt gatt, int status, int newState) {
            if (listener != null) {
                listener.onConnectionStateChange(status, newState);
            }
        }

        @Override
        public void onServicesDiscovered(BluetoothGatt gatt, int status) {
            if (listener != null) {
                listener.onServicesDiscovered(status);
            }
        }

        @Override
        public void onCharacteristicWrite(BluetoothGatt gatt, BluetoothGattCharacteristic characteristic, int status) {
            if (listener != null) {
                listener.onCharacteristicWrite(status);
            }
        }

        @Override
        public void onCharacteristicChanged(BluetoothGatt gatt, BluetoothGattCharacteristic characteristic) {
            if (listener != null && characteristic != null) {
                listener.onCharacteristicChanged(characteristic.getValue());
            }
        }
    }
}
