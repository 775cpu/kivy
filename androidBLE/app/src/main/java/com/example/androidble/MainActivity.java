package com.example.androidble;

import android.Manifest;
import android.content.pm.PackageManager;
import android.os.Bundle;
import android.widget.Button;
import android.widget.TextView;
import androidx.annotation.NonNull;
import androidx.appcompat.app.AppCompatActivity;
import androidx.core.app.ActivityCompat;
import androidx.core.content.ContextCompat;
import com.example.androidble.ble.BleManager;

public class MainActivity extends AppCompatActivity implements BleManager.BleListener {
    private TextView logView;
    private BleManager bleManager;
    private String discoveredAddress;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        logView = findViewById(R.id.logView);
        Button btnScan = findViewById(R.id.btnScan);
        Button btnConnect = findViewById(R.id.btnConnect);

        bleManager = new BleManager(this);
        bleManager.addListener(this);

        btnScan.setOnClickListener(v -> {
            appendLog("开始扫描...");
            bleManager.startScan();
        });

        btnConnect.setOnClickListener(v -> {
            if (discoveredAddress == null) {
                appendLog("请先扫描到设备");
                return;
            }
            appendLog("尝试连接: " + discoveredAddress);
            bleManager.connect(discoveredAddress);
        });

        ensurePermissions();
    }

    private void ensurePermissions() {
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.BLUETOOTH_SCAN) != PackageManager.PERMISSION_GRANTED) {
            ActivityCompat.requestPermissions(this, new String[]{
                    Manifest.permission.BLUETOOTH_SCAN,
                    Manifest.permission.BLUETOOTH_CONNECT,
                    Manifest.permission.ACCESS_FINE_LOCATION,
                    Manifest.permission.ACCESS_COARSE_LOCATION
            }, 1001);
            return;
        }
        appendLog("权限已就绪");
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, @NonNull String[] permissions, @NonNull int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (requestCode == 1001) {
            appendLog("权限结果已返回");
        }
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        if (bleManager != null) {
            bleManager.close();
        }
    }

    @Override
    public void onScanResult(String deviceName, String deviceAddress, int rssi) {
        discoveredAddress = deviceAddress;
        appendLog("发现设备: " + (deviceName == null || deviceName.isEmpty() ? "未知设备" : deviceName) + " | " + deviceAddress + " | RSSI=" + rssi);
    }

    @Override
    public void onScanFailed(String message) {
        appendLog("扫描失败: " + message);
    }

    @Override
    public void onConnected(String deviceAddress) {
        appendLog("已连接: " + deviceAddress);
    }

    @Override
    public void onDisconnected(String deviceAddress) {
        appendLog("已断开: " + deviceAddress);
    }

    @Override
    public void onCharacteristicValue(String serviceUuid, String characteristicUuid, byte[] value) {
        appendLog("收到数据: " + serviceUuid + " / " + characteristicUuid + " / " + new String(value));
    }

    @Override
    public void onError(String message) {
        appendLog("错误: " + message);
    }

    private void appendLog(String message) {
        runOnUiThread(() -> {
            String current = logView.getText().toString();
            logView.setText(current + "\n" + message);
        });
    }
}
