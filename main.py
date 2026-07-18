# -*- coding: utf-8 -*-
import rpc
rpc_server, rpc_thread = rpc.start_rpc_server(port=1133, key='', globals=globals(), locals=locals())

from collections import deque
from functools import partial
import binascii
import os
import traceback
import hashlib
import random

from kivy.app import App
from kivy.clock import Clock
from kivy.lang import Builder
from kivy.metrics import dp
from kivy.properties import StringProperty, BooleanProperty, NumericProperty
from kivy.uix.boxlayout import BoxLayout

from jnius import autoclass, PythonJavaClass, java_method, cast

# ------------------- Java classes --------------------
PythonActivity = autoclass('org.kivy.android.PythonActivity')
Context = autoclass('android.content.Context')
Build_VERSION = autoclass('android.os.Build$VERSION')
Build_VERSION_CODES = autoclass('android.os.Build$VERSION_CODES')
PackageManager = autoclass('android.content.pm.PackageManager')
BluetoothAdapter = autoclass('android.bluetooth.BluetoothAdapter')
BluetoothProfile = autoclass('android.bluetooth.BluetoothProfile')
BluetoothGattDescriptor = autoclass('android.bluetooth.BluetoothGattDescriptor')
UUID = autoclass('java.util.UUID')
String = autoclass('java.lang.String')
BleBridge = autoclass('org.qgb.ble.BleBridge')

KV = r'''
<RootWidget>:
    orientation: 'vertical'
    padding: dp(12)
    spacing: dp(10)

    canvas.before:
        Color:
            rgba: 0.08, 0.09, 0.11, 1
        Rectangle:
            pos: self.pos
            size: self.size

    Label:
        text: app.title_text
        size_hint_y: None
        height: dp(36)
        color: 1, 1, 1, 1
        font_size: '20sp'
        bold: True

    Label:
        text: app.status_text
        text_size: self.width, None
        halign: 'left'
        valign: 'middle'
        color: 0.7, 0.9, 1, 1
        size_hint_y: None
        height: dp(70)

    Label:
        text: app.device_text
        text_size: self.width, None
        halign: 'left'
        valign: 'middle'
        color: 0.9, 0.9, 0.9, 1
        size_hint_y: None
        height: dp(45)

    Label:
        text: app.handshake_text
        text_size: self.width, None
        halign: 'left'
        valign: 'middle'
        color: 1, 0.85, 0.4, 1
        size_hint_y: None
        height: dp(45)

    BoxLayout:
        size_hint_y: None
        height: dp(48)
        spacing: dp(8)

        Button:
            text: '重新扫描'
            on_release: app.manual_rescan()

        Button:
            text: '断开'
            on_release: app.manual_disconnect()

        Button:
            text: '重连'
            on_release: app.manual_reconnect()

    BoxLayout:
        size_hint_y: None
        height: dp(48)
        spacing: dp(8)

        Button:
            text: '开/关机'
            disabled: not app.control_ready
            on_release: app.toggle_power()

        Button:
            text: '握手'
            disabled: not app.gatt_ready
            on_release: app.send_security_handshake()

    BoxLayout:
        orientation: 'vertical'
        size_hint_y: None
        height: dp(170)
        spacing: dp(8)

        Label:
            text: '温度: {}°C'.format(app.target_temp)
            color: 1, 1, 1, 1
            size_hint_y: None
            height: dp(28)

        Slider:
            min: 16
            max: 30
            step: 1
            value: app.target_temp
            disabled: not app.control_ready
            on_value: app.on_temp_slider(self.value)

        BoxLayout:
            size_hint_y: None
            height: dp(44)
            spacing: dp(8)

            Button:
                text: '制冷'
                disabled: not app.control_ready
                on_release: app.set_mode('cool')

            Button:
                text: '制热'
                disabled: not app.control_ready
                on_release: app.set_mode('heat')

            Button:
                text: '送风'
                disabled: not app.control_ready
                on_release: app.set_mode('fan')

            Button:
                text: '除湿'
                disabled: not app.control_ready
                on_release: app.set_mode('dry')

            Button:
                text: '自动'
                disabled: not app.control_ready
                on_release: app.set_mode('auto')

        BoxLayout:
            size_hint_y: None
            height: dp(44)
            spacing: dp(8)

            Button:
                text: '自动风'
                disabled: not app.control_ready
                on_release: app.set_fan('auto')

            Button:
                text: '低风'
                disabled: not app.control_ready
                on_release: app.set_fan('low')

            Button:
                text: '中风'
                disabled: not app.control_ready
                on_release: app.set_fan('medium')

            Button:
                text: '高风'
                disabled: not app.control_ready
                on_release: app.set_fan('high')

    Label:
        text: app.control_text
        text_size: self.width, None
        halign: 'left'
        valign: 'middle'
        color: 0.85, 1, 0.85, 1
        size_hint_y: None
        height: dp(70)

    ScrollView:
        do_scroll_x: False

        Label:
            text: app.log_text
            text_size: self.width, None
            size_hint_y: None
            height: self.texture_size[1]
            halign: 'left'
            valign: 'top'
            color: 0.85, 0.85, 0.85, 1
'''

Builder.load_string(KV)


class RootWidget(BoxLayout):
    pass


# ---------- Permission callback ----------
class PermissionCallback(PythonJavaClass):
    __javainterfaces__ = ['org/kivy/android/PythonActivity$PermissionsCallback']
    __javacontext__ = 'app'

    def __init__(self, owner):
        super().__init__()
        self.owner = owner

    @java_method('([Ljava/lang/String;[I)V')
    def onRequestPermissionsResult(self, permissions, grantResults):
        Clock.schedule_once(lambda dt: self.owner._on_permissions_result(permissions, grantResults), 0)


# ---------- BLE Scan callback ----------
class PyScanListener(PythonJavaClass):
    __javainterfaces__ = ['org/qgb/ble/ScanListener']
    __javacontext__ = 'app'

    def __init__(self, owner):
        super().__init__()
        self.owner = owner

    @java_method('(Ljava/lang/String;Ljava/lang/String;I)V')
    def onDeviceFound(self, address, name, rssi):
        addr = str(address) if address is not None else ''
        dev_name = str(name) if name is not None else ''
        Clock.schedule_once(lambda dt: self.owner._on_scan_device_found(addr, dev_name, int(rssi)), 0)

    @java_method('(I)V')
    def onScanFailed(self, errorCode):
        Clock.schedule_once(lambda dt: self.owner._on_scan_failed(int(errorCode)), 0)

    @java_method('(Ljava/lang/String;)V')
    def onScanError(self, message):
        msg = str(message) if message is not None else ''
        Clock.schedule_once(lambda dt: self.owner._on_scan_error(msg), 0)


# ---------- GATT callback (using org.qgb.ble.GattListener interface) ----------
class PyGattCallback(PythonJavaClass):
    __javainterfaces__ = ['org/qgb/ble/GattListener']
    __javacontext__ = 'app'

    def __init__(self, owner, generation, device_name):
        super().__init__()
        self.owner = owner
        self.generation = generation
        self.device_name = device_name

    def _valid(self):
        return self.owner is not None and self.generation == self.owner.connection_generation

    @java_method('(II)V')
    def onConnectionStateChange(self, status, newState):
        Clock.schedule_once(
            lambda dt: self.owner._on_gatt_connection_state_change(
                self.generation, int(status), int(newState)
            ), 0
        )

    @java_method('(I)V')
    def onServicesDiscovered(self, status):
        Clock.schedule_once(
            lambda dt: self.owner._on_gatt_services_discovered(
                self.generation, int(status)
            ), 0
        )

    @java_method('(I)V')
    def onCharacteristicWrite(self, status):
        # Write callback signature in GattListener: (I)V, only status
        Clock.schedule_once(
            lambda dt: self.owner._on_gatt_characteristic_write(
                self.generation, int(status)
            ), 0
        )

    @java_method('([B)V')
    def onCharacteristicChanged(self, value):
        if value:
            unsigned_bytes = [b & 0xFF for b in value]
            hex_data = bytes(unsigned_bytes).hex().upper()
        else:
            hex_data = ""
        Clock.schedule_once(
            lambda dt: self.owner._on_gatt_characteristic_changed(
                self.generation, hex_data
            ), 0
        )


# ---------- Helpers ----------
def hexstr(data: bytes) -> str:
    return data.hex().upper()


def from_hex(s: str) -> bytes:
    s = (s or '').replace(' ', '').replace(':', '')
    if len(s) % 2 != 0:
        raise ValueError('hex length must be even')
    return bytes.fromhex(s)


def checksum_1_complement(frame_without_last_checksum: bytes) -> int:
    total = sum(frame_without_last_checksum) & 0xFF
    return (1 + (~total)) & 0xFF


def build_aa55_frame(msg_type: int, payload: bytes, random_byte: int = None) -> bytes:
    if random_byte is None:
        random_byte = random.randint(0, 255)
    body_len = len(payload) + 4
    frame = bytearray(2 + 1 + 1 + 1 + len(payload) + 1)
    frame[0] = 0xAA
    frame[1] = 0x55
    frame[2] = body_len & 0xFF
    frame[3] = random_byte & 0xFF
    frame[4] = msg_type & 0xFF
    frame[5:5 + len(payload)] = payload
    frame[-1] = checksum_1_complement(frame[2:-1])
    return bytes(frame)


def chunked(data: bytes, size: int):
    for i in range(0, len(data), size):
        yield data[i:i + size]


# ---------- Protocol builder ----------
class MideaProtocol:
    APP_FIXED = b'midea_bleapp'

    MSG_C1 = 0x01
    MSG_C2 = 0x02
    MSG_C3 = 0x03
    MSG_C4 = 0x04

    def __init__(self):
        self.last_session_key = None
        self.last_root_key = None

    def create_root_key(self, advertis_data_hex: str) -> bytes:
        ad = from_hex(advertis_data_hex) if advertis_data_hex else b''
        digest = hashlib.sha256(ad + self.APP_FIXED).digest()
        key = digest[:16]
        self.last_root_key = key
        return key

    def build_c1_payload(self, advertis_data_hex: str) -> bytes:
        ad = from_hex(advertis_data_hex) if advertis_data_hex else b''
        digest = hashlib.md5(ad + b'c1').digest()
        return b'\x01' + digest

    def build_c1_frame(self, advertis_data_hex: str) -> bytes:
        payload = self.build_c1_payload(advertis_data_hex)
        return build_aa55_frame(self.MSG_C1, payload)

    def build_control_plain_payload(self, power: bool, temp: int, mode: str, fan: str) -> bytes:
        mode_map = {
            'auto': 0x00,
            'cool': 0x01,
            'dry': 0x02,
            'fan': 0x03,
            'heat': 0x04,
        }
        fan_map = {
            'auto': 0x00,
            'low': 0x01,
            'medium': 0x02,
            'high': 0x03,
        }

        temp = max(16, min(30, int(temp)))
        mode_v = mode_map.get(mode, 0x01)
        fan_v = fan_map.get(fan, 0x00)
        power_v = 0x01 if power else 0x00

        payload = bytes([
            0x5A,
            0x0C,
            0x02,
            power_v,
            temp,
            mode_v,
            fan_v,
            0x00,
            0x00,
            0x00,
            0x00,
        ])
        cs = checksum_1_complement(payload)
        return payload + bytes([cs])

    def encrypt_business_payload(self, plain_payload: bytes) -> bytes:
        return plain_payload

    def build_control_frame(self, power: bool, temp: int, mode: str, fan: str) -> bytes:
        plain = self.build_control_plain_payload(power, temp, mode, fan)
        cipher = self.encrypt_business_payload(plain)
        return build_aa55_frame(self.MSG_C2, cipher)


# ---------- Main App ----------
class HualingACApp(App):
    title_text = StringProperty('华凌空调 BLE 控制')
    status_text = StringProperty('初始化中...')
    device_text = StringProperty('设备: 未连接')
    handshake_text = StringProperty('握手: 未开始')
    control_text = StringProperty('状态: Power=False Temp=25 Mode=cool Fan=auto')
    log_text = StringProperty('')

    gatt_ready = BooleanProperty(False)
    control_ready = BooleanProperty(False)

    target_temp = NumericProperty(25)

    # Midea service UUIDs
    MIDEA_SERVICE_UUID = "0000ffa0-0000-1000-8000-00805f9b34fb"
    MIDEA_WRITE_UUID    = "0000ffa1-0000-1000-8000-00805f9b34fb"
    MIDEA_NOTIFY_UUID   = "0000ffa2-0000-1000-8000-00805f9b34fb"
    CCCD_UUID           = "00002902-0000-1000-8000-00805f9b34fb"

    def build(self):
        self.root_widget = RootWidget()

        self.activity = PythonActivity.mActivity
        self.context = self.activity.getApplicationContext()

        self.protocol = MideaProtocol()

        self.permission_callback = PermissionCallback(self)

        self.scan_listener = None
        self.scan_session = None

        self.gatt_callback = None
        self.gatt = None
        self.write_char = None

        self.is_paused = False
        self.permissions_ok = False

        self.is_scanning = False
        self.is_connecting = False
        self.is_connected = False
        self.notification_ready = False
        self.handshake_done = False

        self.connection_generation = 0

        self.current_device = None
        self.current_device_name = ''
        self.current_device_addr = ''
        self.current_advertis_data = ''

        self.seen_devices = {}
        self.auto_target_locked = False

        self.write_queue = deque()
        self.write_in_progress = False
        self.last_write_tag = ''

        self.auto_reconnect_event = None
        self.scan_timeout_event = None
        self.handshake_timeout_event = None
        self.auto_send_event = None

        self.desired_power = False
        self.desired_mode = 'cool'
        self.desired_fan = 'auto'
        self.target_temp = 25

        self._log('App started')
        Clock.schedule_once(lambda dt: self.startup(), 0.2)
        return self.root_widget

    # ------------------------------------------------------------------
    # Logging / UI
    # ------------------------------------------------------------------
    def _log(self, msg):
        print(msg)
        lines = self.log_text.split('\n') if self.log_text else []
        lines.append(msg)
        if len(lines) > 120:
            lines = lines[-120:]
        self.log_text = '\n'.join(lines)

    def _set_status(self, msg):
        self.status_text = msg
        self._log(msg)

    def _refresh_control_text(self):
        self.control_text = (
            f'状态: Power={self.desired_power} '
            f'Temp={int(self.target_temp)} '
            f'Mode={self.desired_mode} '
            f'Fan={self.desired_fan}'
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def on_start(self):
        self._refresh_control_text()

    def on_pause(self):
        self.is_paused = True
        self._set_status('[LIFE] on_pause')
        self.stop_scan()
        return True

    def on_resume(self):
        self.is_paused = False
        self._set_status('[LIFE] on_resume')
        Clock.schedule_once(lambda dt: self.ensure_scan_or_connect(), 0.8)

    def on_stop(self):
        self._set_status('[LIFE] on_stop')
        self.cleanup_all()

    def cleanup_all(self):
        self.cancel_timers()
        self.stop_scan()
        self.disconnect_gatt(clear_target=False)

    def cancel_timers(self):
        for ev_name in ('auto_reconnect_event', 'scan_timeout_event', 'handshake_timeout_event', 'auto_send_event'):
            ev = getattr(self, ev_name, None)
            if ev is not None:
                try:
                    ev.cancel()
                except Exception:
                    pass
                setattr(self, ev_name, None)

    # ------------------------------------------------------------------
    # Permissions
    # ------------------------------------------------------------------
    def startup(self):
        self.request_permissions()

    def _required_permissions(self):
        perms = []
        sdk = int(Build_VERSION.SDK_INT)
        if sdk >= 31:
            perms.extend([
                "android.permission.BLUETOOTH_SCAN",
                "android.permission.BLUETOOTH_CONNECT",
            ])
        else:
            perms.extend([
                "android.permission.ACCESS_FINE_LOCATION",
                "android.permission.ACCESS_COARSE_LOCATION",
                "android.permission.BLUETOOTH",
                "android.permission.BLUETOOTH_ADMIN",
            ])
        return perms

    def request_permissions(self):
        perms = self._required_permissions()
        missing = []
        for p in perms:
            if self.activity.checkSelfPermission(p) != PackageManager.PERMISSION_GRANTED:
                missing.append(p)

        if not missing:
            self.permissions_ok = True
            self._set_status('[PERM] Permissions already granted')
            Clock.schedule_once(lambda dt: self.ensure_scan_or_connect(), 0.2)
            return

        self._set_status('[PERM] Requesting Bluetooth permissions...')
        self.activity.addPermissionsCallback(self.permission_callback)
        self.activity.requestPermissions(missing, 1001)

    def _on_permissions_result(self, permissions, grantResults):
        ok = True
        if grantResults is None:
            ok = False
        else:
            for i in range(len(grantResults)):
                if int(grantResults[i]) != PackageManager.PERMISSION_GRANTED:
                    ok = False
                    break

        self.permissions_ok = ok
        if ok:
            self._set_status('[PERM] Permissions granted')
            Clock.schedule_once(lambda dt: self.ensure_scan_or_connect(), 0.2)
        else:
            self._set_status('[PERM] Permission denied')

    # ------------------------------------------------------------------
    # Scan / Connect orchestration
    # ------------------------------------------------------------------
    def ensure_scan_or_connect(self):
        if self.is_paused or not self.permissions_ok:
            return

        if self.is_connected or self.is_connecting:
            return

        if self.current_device_addr:
            self._set_status(f'[AUTO] Try reconnect {self.current_device_name or self.current_device_addr}')
            self.connect_to_device(self.current_device_addr, self.current_device_name, self.current_advertis_data)
        else:
            self.start_scan()

    def manual_rescan(self):
        self._set_status('[UI] manual rescan')
        self.auto_target_locked = False
        self.current_device = None
        self.current_device_name = ''
        self.current_device_addr = ''
        self.current_advertis_data = ''
        self.stop_scan()
        self.disconnect_gatt(clear_target=True)
        Clock.schedule_once(lambda dt: self.start_scan(), 0.2)

    def manual_disconnect(self):
        self._set_status('[UI] manual disconnect')
        self.disconnect_gatt(clear_target=False)

    def manual_reconnect(self):
        self._set_status('[UI] manual reconnect')
        self.disconnect_gatt(clear_target=False)
        Clock.schedule_once(lambda dt: self.ensure_scan_or_connect(), 0.8)

    def start_scan(self):
        if self.is_paused or not self.permissions_ok:
            return
        if self.is_scanning:
            return

        self.stop_scan()
        self.scan_listener = PyScanListener(self)
        self.scan_session = BleBridge.createScanSession(self.context, self.scan_listener)

        ok = False
        try:
            ok = bool(self.scan_session.start())
        except Exception as e:
            self._set_status(f'[SCAN] start exception: {e}')
            traceback.print_exc()

        if ok:
            self.is_scanning = True
            self._set_status('[SCAN] Started BLE scan')
            self.scan_timeout_event = Clock.schedule_once(lambda dt: self._on_scan_timeout(), 12)
        else:
            self._set_status('[SCAN] Failed to start')
            self.schedule_reconnect()

    def stop_scan(self):
        self.is_scanning = False
        if self.scan_timeout_event is not None:
            try:
                self.scan_timeout_event.cancel()
            except Exception:
                pass
            self.scan_timeout_event = None

        if self.scan_session is not None:
            try:
                self.scan_session.stop()
            except Exception as e:
                self._log(f'[SCAN] stop exception: {e}')
        self.scan_session = None
        self.scan_listener = None

    def _on_scan_timeout(self):
        self.scan_timeout_event = None
        if self.is_connected or self.is_connecting:
            return
        self._set_status('[SCAN] Timeout, restarting...')
        self.stop_scan()
        Clock.schedule_once(lambda dt: self.start_scan(), 1.0)

    def _on_scan_failed(self, errorCode):
        self._set_status(f'[SCAN] Failed code={errorCode}')
        self.stop_scan()
        self.schedule_reconnect()

    def _on_scan_error(self, message):
        self._set_status(f'[SCAN] Error: {message}')
        self.stop_scan()
        self.schedule_reconnect()

    def _normalize_name(self, name):
        return (name or '').strip().lower()

    def _device_score(self, name, rssi):
        n = self._normalize_name(name)
        score = 0
        if 'midea' in n:
            score += 100
        if 'hualing' in n:
            score += 100
        if 'air' in n or 'ac' in n:
            score += 20
        score += max(-100, min(0, int(rssi))) + 100
        return score

    def _on_scan_device_found(self, address, name, rssi):
        if not address:
            return

        score = self._device_score(name, rssi)
        self.seen_devices[address] = {
            'address': address,
            'name': name,
            'rssi': rssi,
            'score': score,
            'advertisData': ''
        }

        self._log(f'[SCAN] Found {name} {address} RSSI={rssi} score={score}')

        target = None
        best_score = -10**9
        for item in self.seen_devices.values():
            if item['score'] > best_score:
                best_score = item['score']
                target = item

        if target and best_score >= 80 and not self.is_connecting and not self.is_connected:
            self.auto_target_locked = True
            self.stop_scan()
            self.connect_to_device(
                target['address'],
                target['name'],
                target.get('advertisData', '')
            )

    # ------------------------------------------------------------------
    # GATT (using BleBridge.connectGatt & native BluetoothGatt)
    # ------------------------------------------------------------------
    def _next_generation(self):
        self.connection_generation += 1
        return self.connection_generation

    def connect_to_device(self, address, name='', advertis_data_hex=''):
        if not address:
            self._set_status('[GATT] No device address to connect')
            return

        self.disconnect_gatt(clear_target=False)
        self.stop_scan()

        generation = self._next_generation()
        self.is_connecting = True
        self.is_connected = False
        self.gatt_ready = False
        self.control_ready = False
        self.notification_ready = False
        self.handshake_done = False
        self.write_queue.clear()
        self.write_in_progress = False

        self.current_device_addr = address
        self.current_device_name = name or 'Unknown'
        self.current_advertis_data = advertis_data_hex or ''
        self.device_text = f'设备: {self.current_device_name} [{self.current_device_addr}]'
        self.handshake_text = '握手: 连接中'

        self.gatt_callback = PyGattCallback(self, generation, self.current_device_name)

        self._set_status(f'[GATT] Connecting to {self.current_device_name} {self.current_device_addr} ...')

        try:
            self.gatt = BleBridge.connectGatt(
                self.context,
                String(address),
                False,
                self.gatt_callback
            )
            if not self.gatt:
                self._set_status(f'[GATT] connectGatt returned null')
                self.is_connecting = False
                self.schedule_reconnect()
        except Exception as e:
            self._set_status(f'[GATT] connect exception: {e}')
            traceback.print_exc()
            self.is_connecting = False
            self.schedule_reconnect()

    def disconnect_gatt(self, clear_target=False):
        self.is_connecting = False
        self.is_connected = False
        self.gatt_ready = False
        self.control_ready = False
        self.notification_ready = False
        self.handshake_done = False
        self.write_queue.clear()
        self.write_in_progress = False
        self.last_write_tag = ''

        self.connection_generation += 1

        if self.handshake_timeout_event is not None:
            try:
                self.handshake_timeout_event.cancel()
            except Exception:
                pass
            self.handshake_timeout_event = None

        if self.gatt is not None:
            try:
                self.gatt.disconnect()
                self.gatt.close()
            except Exception as e:
                self._log(f'[GATT] disconnect exception: {e}')
        self.gatt = None
        self.gatt_callback = None
        self.write_char = None

        if clear_target:
            self.current_device = None
            self.current_device_name = ''
            self.current_device_addr = ''
            self.current_advertis_data = ''
            self.device_text = '设备: 未连接'
        self.handshake_text = '握手: 未开始'

    def schedule_reconnect(self, delay=2.5):
        if self.is_paused:
            return
        if self.auto_reconnect_event is not None:
            try:
                self.auto_reconnect_event.cancel()
            except Exception:
                pass
        self.auto_reconnect_event = Clock.schedule_once(lambda dt: self.ensure_scan_or_connect(), delay)

    # --- GATT event handlers ---
    def _on_gatt_connection_state_change(self, generation, status, newState):
        if generation != self.connection_generation:
            return

        if newState == BluetoothProfile.STATE_CONNECTED and status == 0:
            self.is_connecting = False
            self.is_connected = True
            self._set_status('[GATT] Connected, waiting services...')
            self.handshake_text = '握手: 等待服务发现'
            if self.gatt:
                self.gatt.discoverServices()
        elif newState == BluetoothProfile.STATE_DISCONNECTED:
            self._set_status(f'[GATT] Disconnected status={status}')
            self.is_connecting = False
            self.is_connected = False
            self.gatt_ready = False
            self.control_ready = False
            self.notification_ready = False
            self.handshake_done = False
            self.handshake_text = '握手: 已断开'
            if self.gatt:
                try:
                    self.gatt.close()
                except Exception:
                    pass
            self.gatt = None
            self.gatt_callback = None
            self.write_char = None
            self.schedule_reconnect()
        else:
            self._set_status(f'[GATT] state changed status={status} newState={newState}')

    def _on_gatt_services_discovered(self, generation, status):
        if generation != self.connection_generation:
            return

        if status != 0:
            self._set_status(f'[GATT] Services discover failed status={status}')
            self.disconnect_gatt(clear_target=False)
            self.schedule_reconnect()
            return

        if not self.gatt:
            return

        try:
            srv_uuid = UUID.fromString(self.MIDEA_SERVICE_UUID)
            service = self.gatt.getService(srv_uuid)
            if not service:
                self._set_status('[GATT] Service FFA0 not found')
                self.disconnect_gatt(clear_target=False)
                return

            write_uuid = UUID.fromString(self.MIDEA_WRITE_UUID)
            self.write_char = service.getCharacteristic(write_uuid)

            notify_uuid = UUID.fromString(self.MIDEA_NOTIFY_UUID)
            notify_char = service.getCharacteristic(notify_uuid)

            if notify_char:
                self.gatt.setCharacteristicNotification(notify_char, True)
                cccd = notify_char.getDescriptor(UUID.fromString(self.CCCD_UUID))
                if cccd:
                    cccd.setValue(BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE)
                    self.gatt.writeDescriptor(cccd)
                self.notification_ready = True

            self.gatt_ready = True
            self._set_status('[GATT] Services discovered, notifications enabled')
            self.device_text = f'设备: {self.current_device_name} [{self.current_device_addr}]  FFA0 ready'
            self.handshake_text = '握手: 通知已开启，准备发送 c1'

            if self.handshake_timeout_event is not None:
                try:
                    self.handshake_timeout_event.cancel()
                except Exception:
                    pass
            self.handshake_timeout_event = Clock.schedule_once(lambda dt: self._on_handshake_timeout(), 10)

            Clock.schedule_once(lambda dt: self.send_security_handshake(), 0.4)
        except Exception as e:
            self._set_status(f'[GATT] Service setup error: {e}')

    def _on_handshake_timeout(self):
        self.handshake_timeout_event = None
        if not self.handshake_done and self.is_connected:
            self._set_status('[SEC] Handshake timeout, reconnecting...')
            self.disconnect_gatt(clear_target=False)
            self.schedule_reconnect(1.5)

    def _on_gatt_characteristic_write(self, generation, status):
        if generation != self.connection_generation:
            return

        self.write_in_progress = False
        self._log(f'[WRITE] write completed status={status} tag={self.last_write_tag}')

        if status != 0:
            self._set_status(f'[WRITE] Failed status={status} tag={self.last_write_tag}')

        Clock.schedule_once(lambda dt: self._write_next(), 0)

    def _on_gatt_characteristic_changed(self, generation, hex_value):
        if generation != self.connection_generation:
            return

        self._log(f'[NOTIFY] <= {hex_value}')

        # 握手完成标记（收到任意通知即认为链路有效）
        if not self.handshake_done:
            self.handshake_done = True
            self.control_ready = True
            self.handshake_text = '握手: 已完成'
            self._set_status('[SEC] Handshake marked as done by device notification')
            if self.handshake_timeout_event is not None:
                try:
                    self.handshake_timeout_event.cancel()
                except Exception:
                    pass
                self.handshake_timeout_event = None
            Clock.schedule_once(lambda dt: self.send_current_ac_frame(), 0.3)
            return

        # TODO: 解析真实状态上报

    # ------------------------------------------------------------------
    # Write queue (using native BluetoothGatt)
    # ------------------------------------------------------------------
    def queue_frame(self, frame: bytes, tag=''):
        if not self.gatt or not self.is_connected or not self.write_char:
            self._set_status(f'[WRITE] Skip, not connected tag={tag}')
            return
        self.write_queue.append((bytes(frame), tag))
        self._write_next()

    def _write_next(self):
        if self.write_in_progress:
            return
        if not self.write_queue:
            return
        if not self.gatt or not self.is_connected or not self.write_char:
            self.write_queue.clear()
            return

        frame, tag = self.write_queue.popleft()
        self.last_write_tag = tag or ''

        # 原生 writeCharacteristic 会自动处理 MTU，但我们仍可手动分片以保证兼容
        mtu_payload = 20
        pieces = list(chunked(frame, mtu_payload))

        if len(pieces) > 1:
            # 将剩余分片重新插回队列头部（按倒序插入保持顺序）
            for piece in reversed(pieces[1:]):
                self.write_queue.appendleft((piece, f'{tag} part'))
            frame = pieces[0]

        try:
            self.write_in_progress = True
            self.write_char.setValue(frame)
            ok = self.gatt.writeCharacteristic(self.write_char)
            self._log(f'[WRITE] => {hexstr(frame)} tag={tag} ok={ok}')
            if not ok:
                self.write_in_progress = False
                self._set_status(f'[WRITE] writeCharacteristic returned false tag={tag}')
                Clock.schedule_once(lambda dt: self._write_next(), 0)
        except Exception as e:
            self.write_in_progress = False
            self._set_status(f'[WRITE] exception: {e}')
            traceback.print_exc()

    # ------------------------------------------------------------------
    # Security / control
    # ------------------------------------------------------------------
    def send_security_handshake(self, *args):
        if not self.gatt_ready or not self.is_connected or not self.write_char:
            self._set_status('[SEC] GATT not ready for handshake')
            return

        frame = self.protocol.build_c1_frame(self.current_advertis_data)
        self.handshake_text = '握手: c1 已发送'
        self._set_status('[SEC] Sending C1 handshake frame')
        self.queue_frame(frame, 'handshake_c1')

    def send_current_ac_frame(self):
        if not self.is_connected or not self.write_char:
            self._set_status('[CMD] Not connected')
            return

        frame = self.protocol.build_control_frame(
            self.desired_power,
            int(self.target_temp),
            self.desired_mode,
            self.desired_fan
        )
        self._set_status(
            f'[Command] Sending: Power:{self.desired_power}, Temp:{int(self.target_temp)}, '
            f'Mode:{self.desired_mode}, Fan:{self.desired_fan}'
        )
        self.queue_frame(frame, 'control')

    # ------------------------------------------------------------------
    # UI actions
    # ------------------------------------------------------------------
    def toggle_power(self):
        self.desired_power = not self.desired_power
        self._refresh_control_text()
        self.send_current_ac_frame()

    def on_temp_slider(self, value):
        new_temp = int(round(value))
        if new_temp != int(self.target_temp):
            self.target_temp = new_temp
            self._refresh_control_text()
            if self.control_ready:
                if self.auto_send_event is not None:
                    try:
                        self.auto_send_event.cancel()
                    except Exception:
                        pass
                self.auto_send_event = Clock.schedule_once(lambda dt: self.send_current_ac_frame(), 0.25)

    def set_mode(self, mode):
        self.desired_mode = mode
        self._refresh_control_text()
        self.send_current_ac_frame()

    def set_fan(self, fan):
        self.desired_fan = fan
        self._refresh_control_text()
        self.send_current_ac_frame()


if __name__ == '__main__':
    HualingACApp().run()