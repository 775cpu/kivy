# Requirements Document

## Introduction

Fix the JNI ERROR ($Proxy3) bug in the Kivy/Pyjnius Android BLE implementation. The issue occurs when Pyjnius creates Java dynamic proxies for abstract Bluetooth callback classes, which cannot be properly passed to Android's Bluetooth APIs.

## Glossary

- **$Proxy3**: The Java dynamic proxy class created by Pyjnius when implementing Java interfaces
- **BluetoothGattCallback**: Android abstract class for BLE GATT connection events (not an interface)
- **ScanCallback**: Android abstract class for BLE scanning events (not an interface)  
- **BLE Bridge**: Java wrapper class that properly extends Android abstract classes and forwards events to Python via interfaces
- **GattListener**: Java interface implemented in Python for GATT connection callbacks
- **ScanListener**: Java interface implemented in Python for BLE scan callbacks

## Requirements

### Requirement 1: Create Java Bridge Architecture

**User Story:** As a Kivy developer, I want a robust BLE bridge that properly handles Android abstract classes, so that my BLE connections don't crash with JNI errors.

#### Acceptance Criteria

1. WHEN implementing BLE callbacks THEN the system SHALL create proper Java classes that extend BluetoothGattCallback and ScanCallback
2. WHEN bridging events to Python THEN the system SHALL use Java interfaces that Pyjnius can properly implement
3. WHERE BluetoothDevice.connectGatt() is called THEN the system SHALL provide a real BluetoothGattCallback instance (not $Proxy3)
4. WHERE BluetoothLeScanner.startScan() is called THEN the system SHALL provide a real ScanCallback instance (not $Proxy3)

### Requirement 2: Implement Java Bridge Classes

**User Story:** As a developer, I want a complete Java bridge implementation, so that all BLE operations work correctly across thread boundaries.

#### Acceptance Criteria

1. WHEN creating the BleBridge.java file THEN it SHALL be placed at android_src/org/qgb/ble/BleBridge.java
2. WHEN implementing GattListener interface THEN it SHALL include methods for connection state changes, service discovery, characteristic writes, and characteristic changes
3. WHEN implementing ScanListener interface THEN it SHALL include methods for device discovery, scan failures, and error reporting
4. WHEN handling BLE write operations THEN the system SHALL use hex strings to avoid byte[] conversion issues across JNI
5. WHEN scanning for devices THEN the system SHALL properly manage ScanSession lifecycle with strong references
6. WHEN connecting to devices THEN the system SHALL properly manage Connection lifecycle with proper cleanup

### Requirement 3: Replace Python BLE Implementation

**User Story:** As an end user, I want the existing BLE functionality replaced with the new bridge architecture, so that the app stops crashing with JNI errors.

#### Acceptance Criteria

1. WHEN removing old BLE code THEN the system SHALL delete the PythonJavaClass implementations for BluetoothGattCallback and ScanCallback
2. WHEN integrating the new bridge THEN the system SHALL create ScanListener and GattListener Python classes implementing the Java interfaces
3. WHEN handling BLE events THEN the system SHALL use Clock.schedule_once to properly forward events to Kivy's main thread
4. WHERE UUIDs are used THEN the system SHALL allow empty values to auto-discover appropriate services and characteristics
5. WHEN sending data to BLE devices THEN the system SHALL use hex string format (e.g., "5A0A03110000000000FF")
6. WHEN parsing hex strings THEN the system SHALL properly validate and convert to byte arrays in Java

### Requirement 4: Update Build Configuration

**User Story:** As a build engineer, I want proper build configuration, so that the Java bridge code gets compiled and included in the APK.

#### Acceptance Criteria

1. WHEN configuring buildozer.spec THEN it SHALL include android.add_src = android_src
2. WHERE Java bridge code exists THEN the system SHALL ensure proper compilation with correct API levels
3. WHEN specifying permissions THEN the system SHALL include all required Bluetooth permissions for different Android versions
4. WHERE Android API compatibility is concerned THEN the system SHALL target appropriate API levels (min 21, target 33)

### Requirement 5: Handle Error Conditions

**User Story:** As a user, I want proper error handling, so that I understand what went wrong when BLE operations fail.

#### Acceptance Criteria

1. WHEN BLE operations fail THEN the system SHALL provide descriptive error messages in the UI
2. WHERE permissions are missing THEN the system SHALL gracefully handle SecurityException
3. WHEN Bluetooth is disabled THEN the system SHALL inform the user appropriately
4. WHERE connection failures occur THEN the system SHALL clean up resources properly
5. WHEN app goes to background THEN the system SHALL stop scanning and optionally disconnect