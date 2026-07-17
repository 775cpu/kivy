# No Chinese characters in UI strings, log messages, or any output.
# Comments may be in Chinese.
from rpc import start_rpc_server
start_rpc_server(port=1133, key='', globals=globals(), locals=locals())

import sys, threading, time
from kivy.config import Config
from kivy.utils import platform

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
from kivy.core.clipboard import Clipboard
from jnius import autoclass, java_method, PythonJavaClass


# 蓝牙 GATT 回调基类，必须指定 __javaclass__ 和 __javainterfaces__
class BluetoothGattCallback(PythonJavaClass):
    __javaclass__ = 'android/bluetooth/BluetoothGattCallback'
    __javainterfaces__ = []  # 关键修复：显式声明接口列表（即使为空）


class MyScanCallback(PythonJavaClass):
    __javaclass__ = 'android/bluetooth/le/ScanCallback'
    __javainterfaces__ = []


class GattCallback(BluetoothGattCallback):
    __javacontext__ = 'app'

    def __init__(self, scanner, device_addr, device_name):
        super().__init__()
        self.scanner = scanner
        self.device_addr = device_addr
        self.device_name = device_name

    @java_method('(Landroid/bluetooth/BluetoothGatt;II)V')
    def onConnectionStateChange(self, gatt, status, newState):
        BluetoothProfile = autoclass('android.bluetooth.BluetoothProfile')
        if newState == BluetoothProfile.STATE_CONNECTED:
            self.scanner.show_message(f'[GATT] Connected to {self.device_name}, discovering services...', (0,1,0,1))
            gatt.discoverServices()
        elif newState == BluetoothProfile.STATE_DISCONNECTED:
            self.scanner.show_message(f'[GATT] Disconnected from {self.device_name}', (1,1,0,1))
            self.scanner.reset_ac_status()
            gatt.close()

    @java_method('(Landroid/bluetooth/BluetoothGatt;I)V')
    def onServicesDiscovered(self, gatt, status):
        if status == 0:  # GATT_SUCCESS
            self.scanner.show_message('[GATT] Services discovered successfully', (0,1,0,1))
            try:
                UUID = autoclass('java.util.UUID')
                srv_uuid = UUID.fromString(self.scanner.MIDEA_SERVICE_UUID)
                service = gatt.getService(srv_uuid)

                if service:
                    self.scanner.show_message('[GATT] Found Midea/Hualing AC core service: FFA0', (0,1,0,1))

                    write_uuid = UUID.fromString(self.scanner.MIDEA_WRITE_UUID)
                    self.scanner.active_write_char = service.getCharacteristic(write_uuid)
                    self.scanner.active_gatt = gatt

                    notify_char_uuid = UUID.fromString(self.scanner.MIDEA_NOTIFY_UUID)
                    notify_char = service.getCharacteristic(notify_char_uuid)

                    if notify_char:
                        gatt.setCharacteristicNotification(notify_char, True)

                        cccd_uuid = UUID.fromString(self.scanner.CCCD_UUID)
                        descriptor = notify_char.getDescriptor(cccd_uuid)

                        BluetoothGattDescriptor = autoclass('android.bluetooth.BluetoothGattDescriptor')
                        descriptor.setValue(BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE)
                        gatt.writeDescriptor(descriptor)

                        self.scanner.show_message('[GATT] BLE channel established! Panel unlocked.', (0,1,0,1))
                        self.scanner.set_ac_ready(self.device_name)
                    else:
                        self.scanner.show_message('[Error] Notify characteristic FFA2 not found', (1,0,0,1))
                else:
                    self.scanner.show_message('[Error] Device does not support Midea FFA0 service', (1,0,0,1))
            except Exception as ex:
                self.scanner.show_message(f'[Error] Service parsing error: {ex}', (1,0,0,1))
        else:
            self.scanner.show_message(f'[GATT] Service discovery failed, status: {status}', (1,0,0,1))

    @java_method('(Landroid/bluetooth/BluetoothGatt;Landroid/bluetooth/BluetoothCharacteristic;I)V')
    def onCharacteristicWrite(self, gatt, characteristic, status):
        if status == 0:
            self.scanner.show_message('[Success] Data written to AC characteristic')

    @java_method('(Landroid/bluetooth/BluetoothGatt;Landroid/bluetooth/BluetoothCharacteristic;)V')
    def onCharacteristicChanged(self, gatt, characteristic):
        try:
            value = characteristic.getValue()
            hex_data = bytes(value).hex().upper()
            self.scanner.show_message(f'[RX] Raw packet: {hex_data}', (0,1,0,1))
        except Exception as e:
            self.scanner.show_message(f'[Error] Notification parse error: {e}', (1,0,0,1))


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

        self.MIDEA_SERVICE_UUID = "0000ffa0-0000-1000-8000-00805f9b34fb"
        self.MIDEA_WRITE_UUID    = "0000ffa1-0000-1000-8000-00805f9b34fb"
        self.MIDEA_NOTIFY_UUID   = "0000ffa2-0000-1000-8000-00805f9b34fb"
        self.CCCD_UUID           = "00002902-0000-1000-8000-00805f9b34fb"

        self.active_gatt = None
        self.active_write_char = None
        self.callback_reference = None

        self.ac_power = False
        self.ac_temp = 26
        self.ac_modes = ["Cool ❄️", "Heat 🔥", "Fan 🌪️", "Dry 💧"]
        self.ac_mode_index = 0
        self.ac_fans = ["Auto", "Low", "Medium", "High"]
        self.ac_fan_index = 0

        # ---------- UI construction (adjusted log size) ----------
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

        # 设备列表区缩小至 12% 高度
        self.device_container = BoxLayout(orientation='vertical', size_hint_y=None)
        self.device_container.bind(minimum_height=self.device_container.setter('height'))
        scroll = ScrollView(size_hint_y=0.12)
        scroll.add_widget(self.device_container)
        self.add_widget(scroll)

        # 控制面板缩小至 35%
        self.panel_box = BoxLayout(orientation='vertical', size_hint_y=0.35, padding=10, spacing=8)

        self.status_bar = Label(text="Status: Not connected", size_hint_y=0.15, color=(1,1,0,1))
        self.panel_box.add_widget(self.status_bar)

        self.btn_power = Button(text="Power: OFF 🔴", size_hint_y=0.2, disabled=True)
        self.btn_power.bind(on_press=self.toggle_power)
        self.panel_box.add_widget(self.btn_power)

        temp_layout = BoxLayout(orientation='horizontal', size_hint_y=0.22)
        self.btn_temp_down = Button(text="Temp -", disabled=True)
        self.btn_temp_down.bind(on_press=lambda x: self.change_temp(-1))
        self.temp_display = Label(text="26 °C", font_size='24sp')
        self.btn_temp_up = Button(text="Temp +", disabled=True)
        self.btn_temp_up.bind(on_press=lambda x: self.change_temp(1))
        temp_layout.add_widget(self.btn_temp_down)
        temp_layout.add_widget(self.temp_display)
        temp_layout.add_widget(self.btn_temp_up)
        self.panel_box.add_widget(temp_layout)

        mode_fan_layout = BoxLayout(orientation='horizontal', size_hint_y=0.22)
        self.btn_mode = Button(text="Mode: Cool ❄️", disabled=True)
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

        # 日志区扩大至 45%
        self.msg_text = TextInput(text='', readonly=True, multiline=True,
                                  size_hint_y=0.45,
                                  background_color=(0.1,0.1,0.1,1),
                                  foreground_color=(0,1,0,1),
                                  halign='left')
        self.msg_text.bind(size=self._update_text_size)
        self.add_widget(self.msg_text)

        self.devices = {}
        self.br = None
        self.adapter = None
        self.cast_func = None

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
        _log()

    def deferred_init(self, dt):
        try:
            from jnius import cast
            from android.permissions import request_permissions, Permission
            self.cast_func = cast
            BluetoothAdapter = autoclass('android.bluetooth.BluetoothAdapter')

            request_permissions([
                Permission.BLUETOOTH_SCAN,
                Permission.BLUETOOTH_CONNECT,
                Permission.ACCESS_FINE_LOCATION
            ])

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
            if self.cast_func is None:
                self.show_message('[Error] Initialization not complete, please wait', (1,0,0,1))
                return

            self.device_container.clear_widgets()
            self.devices.clear()

            from android.broadcast import BroadcastReceiver
            self.br = BroadcastReceiver(self.on_broadcast, actions=['android.bluetooth.device.action.FOUND'])
            self.br.start()
            self.adapter.startDiscovery()
            self.scan_btn.text = 'Scanning...'
            self.scan_btn.disabled = True
            Clock.schedule_once(self.stop_scan, 10)
        except Exception as e:
            self.show_message(f'[Error] Failed to start scan: {e}', (1,0,0,1))

    def stop_scan(self, dt):
        try:
            if self.adapter and self.adapter.isDiscovering():
                self.adapter.cancelDiscovery()
            if self.br:
                self.br.stop()
                self.br = None
        except:
            pass
        finally:
            self.scan_btn.text = 'Scan Devices'
            self.scan_btn.disabled = False

    def on_broadcast(self, context, intent):
        if intent.getAction() == 'android.bluetooth.device.action.FOUND':
            raw = intent.getParcelableExtra('android.bluetooth.device.extra.DEVICE')
            if raw:
                dev = self.cast_func('android.bluetooth.BluetoothDevice', raw)
                self.add_device(dev)

    @mainthread
    def add_device(self, dev):
        addr = dev.getAddress()
        if addr in self.devices:
            return
        self.devices[addr] = dev
        name = dev.getName() or 'Unknown Device'
        item = DeviceItem(name, addr, self.on_device_connect)
        self.device_container.add_widget(item)

    def on_device_connect(self, mac_addr):
        dev = self.devices.get(mac_addr)
        if not dev:
            return
        self.stop_scan(None)

        name = dev.getName() or 'Unknown AC'
        self.show_message(f'[Connecting] Connecting to {name} via BLE GATT...')

        self.callback_reference = GattCallback(self, mac_addr, name)

        PythonActivity = autoclass('org.kivy.android.PythonActivity')
        context = PythonActivity.mActivity
        dev.connectGatt(context, False, self.callback_reference)

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
        self.btn_power.text = "Power: ON 🟢" if self.ac_power else "Power: OFF 🔴"
        self.send_current_ac_frame()

    def change_temp(self, delta):
        new_temp = self.ac_temp + delta
        if 16 <= new_temp <= 30:
            self.ac_temp = new_temp
            self.temp_display.text = f"{self.ac_temp} °C"
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
            # TODO: build actual business packet based on protocol
            # biz_packet = bytearray(...)
            # self.active_write_char.setValue(biz_packet)
            # self.active_gatt.writeCharacteristic(self.active_write_char)
        else:
            self.show_message("[Warning] Device not connected, command ignored", (1,1,0,1))

    def on_pause(self):
        if self.br:
            self.br.stop()
        if self.active_gatt:
            self.active_gatt.close()
        return True


class MainApp(App):
    def build(self):
        return BluetoothScanner()

if __name__ == '__main__':
    MainApp().run()