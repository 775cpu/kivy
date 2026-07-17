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
from kivy.uix.textinput import TextInput          # ← 补充导入 TextInput
from kivy.clock import Clock, mainthread
from kivy.core.clipboard import Clipboard
from jnius import autoclass, java_method, PythonJavaClass


# ===== 核心修复：定义蓝牙 GATT 回调基类 =====
class BluetoothGattCallback(PythonJavaClass):
    """
    必须通过 __javaclass__ 映射到 Android 原生类，
    才能被 Java 虚拟机正确识别为 BluetoothGattCallback 实例。
    """
    __javaclass__ = 'android/bluetooth/BluetoothGattCallback'
    # 无需在此实现任何方法，GattCallback 会通过 @java_method 覆盖


class MyScanCallback(PythonJavaClass):
    """扫描回调（虽未使用但保留，以防后期 BLE 扫描需求）"""
    __javaclass__ = 'android/bluetooth/le/ScanCallback'


class GattCallback(BluetoothGattCallback):  # ← 继承自刚才定义的 Python 基类
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
            self.scanner.show_message(f'[GATT] 成功连接到 {self.device_name}，正在拉取服务列表...', (0,1,0,1))
            gatt.discoverServices()
        elif newState == BluetoothProfile.STATE_DISCONNECTED:
            self.scanner.show_message(f'[GATT] 与 {self.device_name} 断开连接', (1,1,0,1))
            self.scanner.reset_ac_status()
            gatt.close()

    @java_method('(Landroid/bluetooth/BluetoothGatt;I)V')
    def onServicesDiscovered(self, gatt, status):
        if status == 0:  # GATT_SUCCESS
            self.scanner.show_message(f'[GATT] 服务发现成功', (0,1,0,1))
            try:
                UUID = autoclass('java.util.UUID')
                srv_uuid = UUID.fromString(self.scanner.MIDEA_SERVICE_UUID)
                service = gatt.getService(srv_uuid)

                if service:
                    self.scanner.show_message('[GATT] 找到美的/华凌空调核心服务：FFA0', (0,1,0,1))

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

                        self.scanner.show_message('[GATT] 蓝牙通道建立完毕！面板已解锁，可发送握手或控制指令。', (0,1,0,1))
                        self.scanner.set_ac_ready(self.device_name)
                    else:
                        self.scanner.show_message('[错误] 未找到通知特征值 FFA2', (1,0,0,1))
                else:
                    self.scanner.show_message('[错误] 该设备不支持美的 FFA0 协议服务', (1,0,0,1))
            except Exception as ex:
                self.scanner.show_message(f'[错误] 解析蓝牙服务异常: {ex}', (1,0,0,1))
        else:
            self.scanner.show_message(f'[GATT] 服务拉取失败，状态码: {status}', (1,0,0,1))

    @java_method('(Landroid/bluetooth/BluetoothGatt;Landroid/bluetooth/BluetoothCharacteristic;I)V')
    def onCharacteristicWrite(self, gatt, characteristic, status):
        if status == 0:
            self.scanner.show_message(f'[发送成功] 数据已写入空调特征值')

    @java_method('(Landroid/bluetooth/BluetoothGatt;Landroid/bluetooth/BluetoothCharacteristic;)V')
    def onCharacteristicChanged(self, gatt, characteristic):
        try:
            value = characteristic.getValue()
            hex_data = bytes(value).hex().upper()
            self.scanner.show_message(f'[收到硬件返回] 原始包: {hex_data}', (0,1,0,1))
        except Exception as e:
            self.scanner.show_message(f'[错误] 接收通知解析失败: {e}', (1,0,0,1))


class DeviceItem(BoxLayout):
    def __init__(self, name, address, callback, **kwargs):
        super().__init__(orientation='horizontal', size_hint_y=None, height=50, **kwargs)
        self.callback = callback
        self.device_address = address

        self.name_label = Label(text=name, size_hint_x=0.4, halign='left', valign='middle')
        self.name_label.bind(size=self.name_label.setter('text_size'))
        self.addr_label = Label(text=address, size_hint_x=0.4, halign='center', valign='middle')
        self.addr_label.bind(size=self.addr_label.setter('text_size'))

        self.connect_btn = Button(text='连接空调', size_hint_x=0.2)
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
        self.ac_modes = ["制冷 ❄️", "制热 🔥", "送风 🌪️", "除湿 💧"]
        self.ac_mode_index = 0
        self.ac_fans = ["自动", "低风", "中风", "高风"]
        self.ac_fan_index = 0

        # ---------- 界面构建 ----------
        top_bar = BoxLayout(orientation='horizontal', size_hint_y=0.08)
        self.scan_btn = Button(text='搜索设备', size_hint_x=0.3)
        self.scan_btn.bind(on_press=self.start_scan)
        self.exit_btn = Button(text='退出', size_hint_x=0.2)
        self.exit_btn.bind(on_press=lambda x: sys.exit(0))
        self.title_label = Label(text='华凌空调 BLE 控制端', size_hint_x=0.5)
        top_bar.add_widget(self.scan_btn)
        top_bar.add_widget(self.exit_btn)
        top_bar.add_widget(self.title_label)
        self.add_widget(top_bar)

        self.device_container = BoxLayout(orientation='vertical', size_hint_y=None)
        self.device_container.bind(minimum_height=self.device_container.setter('height'))
        scroll = ScrollView(size_hint_y=0.22)
        scroll.add_widget(self.device_container)
        self.add_widget(scroll)

        self.panel_box = BoxLayout(orientation='vertical', size_hint_y=0.5, padding=10, spacing=8)

        self.status_bar = Label(text="当前状态: 未连接设备", size_hint_y=0.15, color=(1,1,0,1))
        self.panel_box.add_widget(self.status_bar)

        self.btn_power = Button(text="开关：关 🔴", size_hint_y=0.2, disabled=True)
        self.btn_power.bind(on_press=self.toggle_power)
        self.panel_box.add_widget(self.btn_power)

        temp_layout = BoxLayout(orientation='horizontal', size_hint_y=0.22)
        self.btn_temp_down = Button(text="温度 －", disabled=True)
        self.btn_temp_down.bind(on_press=lambda x: self.change_temp(-1))
        self.temp_display = Label(text="26 °C", font_size='24sp')
        self.btn_temp_up = Button(text="温度 ＋", disabled=True)
        self.btn_temp_up.bind(on_press=lambda x: self.change_temp(1))
        temp_layout.add_widget(self.btn_temp_down)
        temp_layout.add_widget(self.temp_display)
        temp_layout.add_widget(self.btn_temp_up)
        self.panel_box.add_widget(temp_layout)

        mode_fan_layout = BoxLayout(orientation='horizontal', size_hint_y=0.22)
        self.btn_mode = Button(text="模式: 制冷 ❄️", disabled=True)
        self.btn_mode.bind(on_press=self.cycle_mode)
        self.btn_fan = Button(text="风速: 自动", disabled=True)
        self.btn_fan.bind(on_press=self.cycle_fan)
        mode_fan_layout.add_widget(self.btn_mode)
        mode_fan_layout.add_widget(self.btn_fan)
        self.panel_box.add_widget(mode_fan_layout)

        self.btn_handshake = Button(text="同步并握手 (发送安全秘钥协商)", size_hint_y=0.21, disabled=True)
        self.btn_handshake.bind(on_press=self.send_security_handshake)
        self.panel_box.add_widget(self.btn_handshake)

        self.add_widget(self.panel_box)

        # 日志区（使用 TextInput 而非 Label，方便滚动复制）
        self.msg_text = TextInput(text='', readonly=True, multiline=True,
                                  size_hint_y=0.2,
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
                self.show_message('[系统提示] 蓝牙底层就绪')
        except Exception as e:
            self.show_message(f'[错误] 初始化失败: {e}', (1,0,0,1))

    def start_scan(self, instance):
        try:
            if not self.adapter or not self.adapter.isEnabled():
                self.show_message('[错误] 请先开启手机蓝牙功能', (1,0,0,1))
                return
            # 防止 cast_func 未就绪
            if self.cast_func is None:
                self.show_message('[错误] 初始化尚未完成，请稍后重试', (1,0,0,1))
                return

            self.device_container.clear_widgets()
            self.devices.clear()

            from android.broadcast import BroadcastReceiver
            self.br = BroadcastReceiver(self.on_broadcast, actions=['android.bluetooth.device.action.FOUND'])
            self.br.start()
            self.adapter.startDiscovery()
            self.scan_btn.text = '正在搜索...'
            self.scan_btn.disabled = True
            Clock.schedule_once(self.stop_scan, 10)
        except Exception as e:
            self.show_message(f'[错误] 启动扫描失败: {e}', (1,0,0,1))

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
            self.scan_btn.text = '搜索设备'
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
        name = dev.getName() or '未知设备'
        item = DeviceItem(name, addr, self.on_device_connect)
        self.device_container.add_widget(item)

    def on_device_connect(self, mac_addr):
        dev = self.devices.get(mac_addr)
        if not dev:
            return
        self.stop_scan(None)

        name = dev.getName() or '未知空调'
        self.show_message(f'[连接中] 正在直连 {name} 的 BLE GATT 服务...')

        self.callback_reference = GattCallback(self, mac_addr, name)

        PythonActivity = autoclass('org.kivy.android.PythonActivity')
        context = PythonActivity.mActivity
        dev.connectGatt(context, False, self.callback_reference)

    @mainthread
    def set_ac_ready(self, name):
        self.status_bar.text = f"已连接设备: {name} (就绪)"
        self.status_bar.color = (0,1,0,1)
        self.btn_power.disabled = False
        self.btn_temp_down.disabled = False
        self.btn_temp_up.disabled = False
        self.btn_mode.disabled = False
        self.btn_fan.disabled = False
        self.btn_handshake.disabled = False

    @mainthread
    def reset_ac_status(self):
        self.status_bar.text = "当前状态: 未连接设备 (断开)"
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
        self.btn_power.text = "开关：开 🟢" if self.ac_power else "开关：关 🔴"
        self.send_current_ac_frame()

    def change_temp(self, delta):
        new_temp = self.ac_temp + delta
        if 16 <= new_temp <= 30:
            self.ac_temp = new_temp
            self.temp_display.text = f"{self.ac_temp} °C"
            self.send_current_ac_frame()

    def cycle_mode(self, instance):
        self.ac_mode_index = (self.ac_mode_index + 1) % len(self.ac_modes)
        self.btn_mode.text = f"模式: {self.ac_modes[self.ac_mode_index]}"
        self.send_current_ac_frame()

    def cycle_fan(self, instance):
        self.ac_fan_index = (self.ac_fan_index + 1) % len(self.ac_fans)
        self.btn_fan.text = f"风速: {self.ac_fans[self.ac_fan_index]}"
        self.send_current_ac_frame()

    def send_security_handshake(self, instance):
        if self.active_gatt and self.active_write_char:
            self.show_message("[BIZ] 正在向 FFA1 接口下发安全层验证数据包...")
            # 模拟 c1 包，请根据实际协议修改
            mock_c1_packet = bytearray([0x5A, 0x0A, 0x03, 0x11, 0x00, 0x00, 0x00, 0x00, 0x00, 0xFF])
            self.active_write_char.setValue(mock_c1_packet)
            self.active_gatt.writeCharacteristic(self.active_write_char)
        else:
            self.show_message("[警告] 空调蓝牙未就绪，无法发送指令", (1,1,0,1))

    def send_current_ac_frame(self):
        if self.active_gatt and self.active_write_char:
            mode_str = self.ac_modes[self.ac_mode_index]
            fan_str = self.ac_fans[self.ac_fan_index]
            self.show_message(f"[指令组合] 下发控制状态 -> 开关:{self.ac_power}, 温度:{self.ac_temp}, 模式:{mode_str}, 风速:{fan_str}")

            # TODO: 根据实际协议拼接业务数据包
            # biz_packet = bytearray(20)
            # ... 填充数据
            # self.active_write_char.setValue(biz_packet)
            # self.active_gatt.writeCharacteristic(self.active_write_char)
        else:
            self.show_message("[警告] 设备未处于连接就绪状态，控制指令未发送", (1,1,0,1))

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