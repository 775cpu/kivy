# No Chinese characters in UI strings, log messages, or any output. Comments may be in Chinese.
import sys
import threading
import time
from kivy.config import Config
from kivy.utils import platform

# =============================================================================
# 全局实例引用，供 RPC 安全调用 (Global instance reference for safe RPC calls)
# =============================================================================
_global_scanner = None

# =============================================================================
# RPC 安全入口函数 (Safe RPC entry points)
# 所有的 RPC 调用都必须通过这些函数，以确保 JNI 在 Kivy 主线程执行
# =============================================================================
def rpc_start_scan():
    if _global_scanner:
        from kivy.clock import Clock
        Clock.schedule_once(lambda dt: _global_scanner.start_scan(None), 0)
        return "Command accepted: Scan started"
    return "Error: Scanner not initialized"

def rpc_connect_device(mac_addr):
    if _global_scanner:
        from kivy.clock import Clock
        Clock.schedule_once(lambda dt: _global_scanner.on_device_connect(mac_addr), 0)
        return f"Command accepted: Connecting to {mac_addr}"
    return "Error: Scanner not initialized"

def rpc_toggle_power():
    if _global_scanner:
        from kivy.clock import Clock
        Clock.schedule_once(lambda dt: _global_scanner.toggle_power(None), 0)
        return "Command accepted: Power toggled"
    return "Error: Scanner not initialized"

def rpc_set_temp(delta):
    if _global_scanner:
        from kivy.clock import Clock
        Clock.schedule_once(lambda dt: _global_scanner.change_temp(delta), 0)
        return f"Command accepted: Temp delta {delta} applied"
    return "Error: Scanner not initialized"

# =============================================================================
# 初始化 RPC 服务器 (Initialize RPC Server)
# =============================================================================
import rpc
rpc_server, rpc_thread = rpc.start_rpc_server(port=1133, key='', globals=globals(), locals=locals())


# 配置 Windows 调试下的字体 (Config for Windows debugging)
if platform != 'android':
    Config.set('kivy', 'default_font', ['C:/Windows/Fonts/msyh.ttc'] * 4)
    Config.write()

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.clock import Clock, mainthread

# 捕获 jnius 导入，防止非 Android 环境崩溃 (Catch jnius import for non-Android environments)
try:
    from jnius import autoclass, java_method, PythonJavaClass, cast
    HAS_JNI = True
except ImportError:
    HAS_JNI = False

# =============================================================================
# 全局缓存 Android Java 类
# =============================================================================
BluetoothAdapter = None
BluetoothProfile = None
UUID = None
BluetoothGattDescriptor = None
PythonActivity = None
BluetoothDevice = None
BleBridge = None

def cache_android_classes():
    global BluetoothAdapter, BluetoothProfile, UUID, BluetoothGattDescriptor, PythonActivity, BluetoothDevice, BleBridge
    if platform == 'android' and HAS_JNI:
        BluetoothAdapter = autoclass('android.bluetooth.BluetoothAdapter')
        BluetoothProfile = autoclass('android.bluetooth.BluetoothProfile')
        UUID = autoclass('java.util.UUID')
        BluetoothGattDescriptor = autoclass('android.bluetooth.BluetoothGattDescriptor')
        PythonActivity = autoclass('org.kivy.android.PythonActivity')
        BluetoothDevice = autoclass('android.bluetooth.BluetoothDevice')
        BleBridge = autoclass('org.qgb.ble.BleBridge')

# =============================================================================
# BLE 专用扫描回调：在 Binder 线程存活期内瞬间提取数据，完全避开官方广播接收器的死指针缺陷
# =============================================================================
if HAS_JNI:
    class ScanListener(PythonJavaClass):
        __javainterfaces__ = ['org/qgb/ble/ScanListener']
        __javacontext__ = 'app'

        def __init__(self, scanner_widget):
            super().__init__()
            self.scanner_widget = scanner_widget

        @java_method('(Ljava/lang/String;Ljava/lang/String;I)V')
        def onDeviceFound(self, address, name, rssi):
            address = str(address or '')
            name = str(name or 'Unknown Device')
            rssi = int(rssi)
            Clock.schedule_once(lambda dt: self.scanner_widget.handle_discovered_device(address, name), 0)

        @java_method('(I)V')
        def onScanFailed(self, errorCode):
            pass

        @java_method('(Ljava/lang/String;)V')
        def onScanError(self, message):
            pass
# =============================================================================
# GATT 连接及状态回调
# =============================================================================
if HAS_JNI:
    class GattCallback(PythonJavaClass):
        __javainterfaces__ = ['org/qgb/ble/GattListener']

        def __init__(self, scanner, device_addr, device_name):
            super().__init__()
            self.scanner = scanner
            self.device_addr = device_addr
            self.device_name = device_name

        @java_method('(II)V')
        def onConnectionStateChange(self, status, newState):
            # 将基础数据类型传回主线程
            Clock.schedule_once(lambda dt: self.scanner.handle_connection_state(status, newState, self.device_name), 0)

        @java_method('(I)V')
        def onServicesDiscovered(self, status):
            Clock.schedule_once(lambda dt: self.scanner.handle_services_discovered(status, self.device_name), 0)

        @java_method('(I)V')
        def onCharacteristicWrite(self, status):
            Clock.schedule_once(lambda dt: self.scanner.handle_characteristic_write(status), 0)

        @java_method('([B)V')
        def onCharacteristicChanged(self, value):
            try:
                hex_data = bytes(value).hex().upper() if value else ""
                Clock.schedule_once(lambda dt: self.scanner.handle_characteristic_changed(hex_data), 0)
            except Exception:
                pass


class DeviceItem(BoxLayout):
    def __init__(self, name, address, callback, **kwargs):
        super().__init__(orientation='horizontal', size_hint_y=None, height=50, **kwargs)
        self.callback = callback
        self.device_address = address

        self.name_label = Label(text=name, size_hint_x=0.4, halign='left', valign='middle')
        self.name_label.bind(size=self.name_label.setter('text_size'))
        self.addr_label = Label(text=address, size_hint_x=0.4, halign='center', valign='middle')
        self.addr_label.bind(size=self.addr_label.setter('text_size'))

        self.connect_btn = Button(text='Connect AC', size_hint_x=0.2)
        self.connect_btn.bind(on_press=lambda x: self.callback(self.device_address))

        self.add_widget(self.name_label)
        self.add_widget(self.addr_label)
        self.add_widget(self.connect_btn)


class BluetoothScanner(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(orientation='vertical', **kwargs)
        
        # 绑定到全局以便 RPC 访问 (Bind to global scope for RPC access)
        global _global_scanner
        _global_scanner = self

        self.MIDEA_SERVICE_UUID = "0000ffa0-0000-1000-8000-00805f9b34fb"
        self.MIDEA_WRITE_UUID    = "0000ffa1-0000-1000-8000-00805f9b34fb"
        self.MIDEA_NOTIFY_UUID   = "0000ffa2-0000-1000-8000-00805f9b34fb"
        self.CCCD_UUID           = "00002902-0000-1000-8000-00805f9b34fb"

        self.active_gatt = None
        self.active_write_char = None
        self.callback_reference = None
        self.scan_listener = None
        self.scan_session = None

        self.ac_power = False
        self.ac_temp = 26
        self.ac_modes = ["Cool", "Heat", "Fan", "Dry"]
        self.ac_mode_index = 0
        self.ac_fans = ["Auto", "Low", "Medium", "High"]
        self.ac_fan_index = 0

        # ---------- UI Layout ----------
        top_bar = BoxLayout(orientation='horizontal', size_hint_y=0.08)
        self.scan_btn = Button(text='Scan Devices', size_hint_x=0.3)
        self.scan_btn.bind(on_press=self.start_scan)
        self.exit_btn = Button(text='Exit', size_hint_x=0.2)
        self.exit_btn.bind(on_press=lambda x: sys.exit(0))
        self.title_label = Label(text='Hualing AC BLE Control', size_hint_x=0.5)
        top_bar.add_widget(self.scan_btn)
        top_bar.add_widget(self.exit_btn)
        top_bar.add_widget(self.title_label)
        self.add_widget(top_bar)

        self.device_container = BoxLayout(orientation='vertical', size_hint_y=None)
        self.device_container.bind(minimum_height=self.device_container.setter('height'))
        scroll = ScrollView(size_hint_y=0.12)
        scroll.add_widget(self.device_container)
        self.add_widget(scroll)

        self.panel_box = BoxLayout(orientation='vertical', size_hint_y=0.35, padding=10, spacing=8)
        self.status_bar = Label(text="Status: Not connected", size_hint_y=0.15, color=(1,1,0,1))
        self.panel_box.add_widget(self.status_bar)

        self.btn_power = Button(text="Power: OFF", size_hint_y=0.2, disabled=True)
        self.btn_power.bind(on_press=self.toggle_power)
        self.panel_box.add_widget(self.btn_power)

        temp_layout = BoxLayout(orientation='horizontal', size_hint_y=0.22)
        self.btn_temp_down = Button(text="Temp -", disabled=True)
        self.btn_temp_down.bind(on_press=lambda x: self.change_temp(-1))
        self.temp_display = Label(text="26 C", font_size='24sp')
        self.btn_temp_up = Button(text="Temp +", disabled=True)
        self.btn_temp_up.bind(on_press=lambda x: self.change_temp(1))
        temp_layout.add_widget(self.btn_temp_down)
        temp_layout.add_widget(self.temp_display)
        temp_layout.add_widget(self.btn_temp_up)
        self.panel_box.add_widget(temp_layout)

        mode_fan_layout = BoxLayout(orientation='horizontal', size_hint_y=0.22)
        self.btn_mode = Button(text="Mode: Cool", disabled=True)
        self.btn_mode.bind(on_press=self.cycle_mode)
        self.btn_fan = Button(text="Fan: Auto", disabled=True)
        self.btn_fan.bind(on_press=self.cycle_fan)
        mode_fan_layout.add_widget(self.btn_mode)
        mode_fan_layout.add_widget(self.btn_fan)
        self.panel_box.add_widget(mode_fan_layout)

        self.btn_handshake = Button(text="Handshake (Security)", size_hint_y=0.21, disabled=True)
        self.btn_handshake.bind(on_press=self.send_security_handshake)
        self.panel_box.add_widget(self.btn_handshake)
        self.add_widget(self.panel_box)

        self.msg_text = TextInput(text='', readonly=True, multiline=True,
                                  size_hint_y=0.45,
                                  background_color=(0.1,0.1,0.1,1),
                                  foreground_color=(0,1,0,1),
                                  halign='left')
        self.msg_text.bind(size=self._update_text_size)
        self.add_widget(self.msg_text)

        self.devices = {}  
        self.adapter = None

        if platform == 'android':
            Clock.schedule_once(self.deferred_init, 1)

    def _update_text_size(self, instance, size):
        instance.text_size = (size[0], None)

    def show_message(self, msg, color=(0,1,0,1)):
        @mainthread
        def _log():
            if self.msg_text.text:
                self.msg_text.text += '\n' + msg
            else:
                self.msg_text.text = msg
            self.msg_text.foreground_color = color
            self.msg_text.scroll_y = 0
            print(msg) # Log to console as well
        _log()

    def deferred_init(self, dt):
        try:
            cache_android_classes()
            from android.permissions import request_permissions, Permission

            request_permissions([
                Permission.BLUETOOTH_SCAN,
                Permission.BLUETOOTH_CONNECT,
                Permission.ACCESS_FINE_LOCATION
            ])

            self.scan_listener = ScanListener(self)
            self.adapter = BluetoothAdapter.getDefaultAdapter()
            if self.adapter and self.adapter.isEnabled():
                self.show_message('[System] Bluetooth ready')
        except Exception as e:
            self.show_message(f'[Error] Init failed: {e}', (1,0,0,1))

    def start_scan(self, instance):
        try:
            if not self.adapter or not self.adapter.isEnabled():
                self.show_message('[Error] Please enable Bluetooth first', (1,0,0,1))
                return

            self.device_container.clear_widgets()
            self.devices.clear()

            context = PythonActivity.mActivity
            if context is None:
                self.show_message('[Error] Activity context is null', (1,0,0,1))
                return

            self.scan_session = BleBridge.startScan(context, self.scan_listener)
            if self.scan_session is None:
                self.show_message('[Error] BLE scan session init failed', (1,0,0,1))
                return

            self.scan_btn.text = 'Scanning...'
            self.scan_btn.disabled = True
            Clock.schedule_once(self.stop_scan, 10)
        except Exception as e:
            self.show_message(f'[Error] Failed to start BLE scan: {e}', (1,0,0,1))

    def stop_scan(self, dt):
        try:
            if self.scan_session:
                self.scan_session.stop()
        except Exception:
            pass
        finally:
            self.scan_btn.text = 'Scan Devices'
            self.scan_btn.disabled = False
            self.scan_session = None

    def handle_discovered_device(self, addr, name):
        if addr in self.devices:
            return
        self.devices[addr] = name
        item = DeviceItem(name, addr, self.on_device_connect)
        self.device_container.add_widget(item)

    def on_device_connect(self, mac_addr):
        if not self.adapter:
            return
        self.stop_scan(None)

        name = self.devices.get(mac_addr) or 'Unknown AC'
        self.show_message(f'[Connecting] Connecting to {name} via BLE GATT...')
        
        try:
            # 跨时段传递严禁携带 Java 引用，延迟中只传递纯文本的 mac_addr
            Clock.schedule_once(lambda dt: self._do_connect(mac_addr, name), 0.1)
        except Exception as e:
            self.show_message(f'[Error] Connection pre-check failed: {e}', (1,0,0,1))

    def _do_connect(self, mac_addr, name):
        try:
            self.callback_reference = GattCallback(self, mac_addr, name)
            context = PythonActivity.mActivity
            
            # 添加安全检查，防止 Activity 被销毁后崩溃 (Null check for activity)
            if context is None:
                self.show_message('[Fatal] Activity Context is null. App in background?', (1,0,0,1))
                return

            self.active_gatt = BleBridge.connectGatt(context, mac_addr, False, self.callback_reference)
            if not self.active_gatt:
                self.show_message(f'[Fatal] connectGatt returned null for {mac_addr}', (1,0,0,1))
        except Exception as e:
            self.show_message(f'[Fatal] ConnectGatt invocation failed: {e}', (1,0,0,1))

    # =============================================================================
    # 主线程 GATT 状态处理器
    # =============================================================================
    def handle_connection_state(self, status, newState, device_name):
        try:
            if newState == BluetoothProfile.STATE_CONNECTED:
                self.show_message(f'[GATT] Connected to {device_name}, discovering services...', (0,1,0,1))
                if self.active_gatt:
                    self.active_gatt.discoverServices()
            elif newState == BluetoothProfile.STATE_DISCONNECTED:
                self.show_message(f'[GATT] Disconnected from {device_name}', (1,1,0,1))
                self.reset_ac_status()
                if self.active_gatt:
                    self.active_gatt.close()
                    self.active_gatt = None
        except Exception as e:
            self.show_message(f'[Error] Connection state process error: {e}', (1,0,0,1))

    def handle_services_discovered(self, status, device_name):
        if status != 0:
            self.show_message(f'[GATT] Service discovery failed, status: {status}', (1,0,0,1))
            return
        if not self.active_gatt:
            return

        self.show_message('[GATT] Services discovered successfully', (0,1,0,1))
        try:
            srv_uuid = UUID.fromString(self.MIDEA_SERVICE_UUID)
            service = self.active_gatt.getService(srv_uuid)

            if service:
                self.show_message('[GATT] Found AC core service: FFA0', (0,1,0,1))

                write_uuid = UUID.fromString(self.MIDEA_WRITE_UUID)
                self.active_write_char = service.getCharacteristic(write_uuid)

                notify_char_uuid = UUID.fromString(self.MIDEA_NOTIFY_UUID)
                notify_char = service.getCharacteristic(notify_char_uuid)

                if notify_char:
                    self.active_gatt.setCharacteristicNotification(notify_char, True)

                    cccd_uuid = UUID.fromString(self.CCCD_UUID)
                    descriptor = notify_char.getDescriptor(cccd_uuid)

                    if descriptor:
                        descriptor.setValue(BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE)
                        self.active_gatt.writeDescriptor(descriptor)

                    self.show_message('[GATT] BLE channel established! Panel unlocked.', (0,1,0,1))
                    self.set_ac_ready(device_name)
                else:
                    self.show_message('[Error] Notify characteristic FFA2 not found', (1,0,0,1))
            else:
                self.show_message('[Error] Device does not support target FFA0 service', (1,0,0,1))
        except Exception as ex:
            self.show_message(f'[Error] Service parsing error: {ex}', (1,0,0,1))

    def handle_characteristic_write(self, status):
        if status == 0:
            self.show_message('[Success] Data written to AC characteristic')
        else:
            self.show_message(f'[Warning] Data write status code: {status}', (1,1,0,1))

    def handle_characteristic_changed(self, hex_data):
        if hex_data:
            self.show_message(f'[RX] Raw packet: {hex_data}', (0,1,0,1))

    # =============================================================================
    # AC 控制面板逻辑
    # =============================================================================
    @mainthread
    def set_ac_ready(self, name):
        self.status_bar.text = f"Connected: {name} (Ready)"
        self.status_bar.color = (0,1,0,1)
        self.btn_power.disabled = False
        self.btn_temp_down.disabled = False
        self.btn_temp_up.disabled = False
        self.btn_mode.disabled = False
        self.btn_fan.disabled = False
        self.btn_handshake.disabled = False

    @mainthread
    def reset_ac_status(self):
        self.status_bar.text = "Status: Not connected (Disconnected)"
        self.status_bar.color = (1,0,0,1)
        self.btn_power.disabled = True
        self.btn_temp_down.disabled = True
        self.btn_temp_up.disabled = True
        self.btn_mode.disabled = True
        self.btn_fan.disabled = True
        self.btn_handshake.disabled = True
        self.active_gatt = None
        self.active_write_char = None

    def toggle_power(self, instance):
        self.ac_power = not self.ac_power
        self.btn_power.text = "Power: ON" if self.ac_power else "Power: OFF"
        self.send_current_ac_frame()

    def change_temp(self, delta):
        new_temp = self.ac_temp + delta
        if 16 <= new_temp <= 30:
            self.ac_temp = new_temp
            self.temp_display.text = f"{self.ac_temp} C"
            self.send_current_ac_frame()

    def cycle_mode(self, instance):
        self.ac_mode_index = (self.ac_mode_index + 1) % len(self.ac_modes)
        self.btn_mode.text = f"Mode: {self.ac_modes[self.ac_mode_index]}"
        self.send_current_ac_frame()

    def cycle_fan(self, instance):
        self.ac_fan_index = (self.ac_fan_index + 1) % len(self.ac_fans)
        self.btn_fan.text = f"Fan: {self.ac_fans[self.ac_fan_index]}"
        self.send_current_ac_frame()

    def send_security_handshake(self, instance):
        if self.active_gatt and self.active_write_char:
            self.show_message("[BIZ] Sending security layer handshake packet...")
            mock_c1_packet = bytearray([0x5A, 0x0A, 0x03, 0x11, 0x00, 0x00, 0x00, 0x00, 0x00, 0xFF])
            self.active_write_char.setValue(mock_c1_packet)
            self.active_gatt.writeCharacteristic(self.active_write_char)
        else:
            self.show_message("[Warning] AC BLE not ready, command ignored", (1,1,0,1))

    def send_current_ac_frame(self):
        if self.active_gatt and self.active_write_char:
            mode_str = self.ac_modes[self.ac_mode_index]
            fan_str = self.ac_fans[self.ac_fan_index]
            self.show_message(f"[Command] Sending: Power:{self.ac_power}, Temp:{self.ac_temp}, Mode:{mode_str}, Fan:{fan_str}")
        else:
            self.show_message("[Warning] Device not connected, command ignored", (1,1,0,1))

    def on_pause(self):
        if self.scan_session:
            try:
                self.scan_session.stop()
            except: pass
            self.scan_session = None
        if self.active_gatt:
            self.active_gatt.close()
            self.active_gatt = None
        return True


class MainApp(App):
    def build(self):
        return BluetoothScanner()

if __name__ == '__main__':
    MainApp().run()