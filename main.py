from rpc import start_rpc_server
start_rpc_server(port=1133, key='', globals=globals(), locals=locals())

import sys, threading, time, traceback
from kivy.config import Config
from kivy.utils import platform

if platform != 'android':
    Config.set('kivy', 'default_font', ['C:/Windows/Fonts/msyh.ttc'] * 4)
    Config.write()

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.scrollview import ScrollView
from kivy.clock import Clock, mainthread
from kivy.core.clipboard import Clipboard

class DeviceItem(BoxLayout):
    def __init__(self, name, address, callback, **kwargs):
        super().__init__(orientation='vertical', size_hint_y=None, height=90, **kwargs)
        self.callback = callback
        self.device_address = address
        row1 = BoxLayout(orientation='horizontal', size_hint_y=0.5)
        self.name_label = Label(text=name, size_hint_x=0.6, halign='left', valign='middle')
        self.name_label.bind(size=self.name_label.setter('text_size'))
        self.addr_label = Label(text=address, size_hint_x=0.4, halign='right', valign='middle')
        self.addr_label.bind(size=self.addr_label.setter('text_size'))
        row1.add_widget(self.name_label)
        row1.add_widget(self.addr_label)
        row2 = BoxLayout(orientation='horizontal', size_hint_y=0.5)
        self.pin_input = TextInput(text='0000', hint_text='PIN', size_hint_x=0.6, multiline=False)
        self.connect_btn = Button(text='Connect', size_hint_x=0.4)
        self.connect_btn.bind(on_press=self._on_connect)
        row2.add_widget(self.pin_input)
        row2.add_widget(self.connect_btn)
        self.add_widget(row1)
        self.add_widget(row2)

    def _on_connect(self, instance):
        pin = self.pin_input.text.strip()
        if not pin:
            pin = '0000'
        self.callback(self.device_address, pin)

class BluetoothScanner(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(orientation='vertical', **kwargs)
        top_bar = BoxLayout(orientation='horizontal', size_hint_y=0.1)
        self.scan_btn = Button(text='SCAN', size_hint_x=0.3)
        self.scan_btn.bind(on_press=self.start_scan)
        self.exit_btn = Button(text='EXIT', size_hint_x=0.2)
        self.exit_btn.bind(on_press=lambda x: sys.exit(0))
        top_bar.add_widget(self.scan_btn)
        top_bar.add_widget(self.exit_btn)
        top_bar.add_widget(Label(text='BLUETOOTH LIST', size_hint_x=0.5))
        self.add_widget(top_bar)

        self.msg_text = TextInput(text='', readonly=True, multiline=True,
                                  size_hint_y=0.5,
                                  background_color=(0.1,0.1,0.1,1),
                                  foreground_color=(0,1,0,1),
                                  halign='left')
        self.msg_text.bind(size=self._update_text_size)
        self.msg_text.bind(on_touch_up=self._on_msg_touch)
        self.add_widget(self.msg_text)

        self.device_container = BoxLayout(orientation='vertical', size_hint_y=None)
        self.device_container.bind(minimum_height=self.device_container.setter('height'))
        scroll = ScrollView(size_hint_y=0.4)
        scroll.add_widget(self.device_container)
        self.add_widget(scroll)

        self.devices = {}
        self.pending_pin = {}
        self.pending_connect = {}
        self.br = None
        self.adapter = None
        self.cast_func = None
        self.bond_receiver = None
        self.pairing_receiver = None
        self.gatt_connections = {}
        if platform == 'android':
            Clock.schedule_once(self.deferred_init, 1)

    def _update_text_size(self, instance, size):
        instance.text_size = (size[0], None)

    def _on_msg_touch(self, instance, touch):
        if not instance.collide_point(*touch.pos):
            return False
        if touch.is_double_tap or (touch.time_end - touch.time_start > 0.5):
            if instance.text:
                Clipboard.copy(instance.text)
            return True
        return False

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
            from jnius import autoclass, cast
            from android.permissions import request_permissions, Permission
            from android.broadcast import BroadcastReceiver
            self.cast_func = cast
            Intent = autoclass('android.content.Intent')
            BluetoothAdapter = autoclass('android.bluetooth.BluetoothAdapter')
            BluetoothDevice = autoclass('android.bluetooth.BluetoothDevice')
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            request_permissions([
                Permission.BLUETOOTH_SCAN,
                Permission.BLUETOOTH_CONNECT,
                Permission.ACCESS_FINE_LOCATION
            ])
            self.adapter = BluetoothAdapter.getDefaultAdapter()
            if self.adapter is None:
                self.show_message('[ERROR] No Bluetooth adapter', (1,0,0,1))
                return
            if not self.adapter.isEnabled():
                self.show_message('[INFO] Requesting BT enable...', (1,1,0,1))
                intent = Intent(BluetoothAdapter.ACTION_REQUEST_ENABLE)
                PythonActivity.mActivity.startActivityForResult(intent, 1)
            else:
                self.show_message('[INFO] Bluetooth ready', (0,1,0,1))
            self._register_receivers()
        except Exception as e:
            self.show_message(f'[ERROR] Init: {e}', (1,0,0,1))

    def _register_receivers(self):
        try:
            from android.broadcast import BroadcastReceiver
            self.bond_receiver = BroadcastReceiver(
                self.on_bond_state_changed,
                actions=['android.bluetooth.device.action.BOND_STATE_CHANGED']
            )
            self.bond_receiver.start()
            self.pairing_receiver = BroadcastReceiver(
                self.on_pairing_request,
                actions=['android.bluetooth.device.action.PAIRING_REQUEST']
            )
            self.pairing_receiver.start()
        except Exception as e:
            self.show_message(f'[ERROR] Register receivers: {e}', (1,0,0,1))

    def on_bond_state_changed(self, context, intent):
        try:
            if intent.getAction() != 'android.bluetooth.device.action.BOND_STATE_CHANGED':
                return
            device = intent.getParcelableExtra('android.bluetooth.device.extra.DEVICE')
            if not device:
                return
            dev = self.cast_func('android.bluetooth.BluetoothDevice', device)
            addr = dev.getAddress()
            bond_state = intent.getIntExtra('android.bluetooth.device.extra.BOND_STATE', -1)
            prev_state = intent.getIntExtra('android.bluetooth.device.extra.PREVIOUS_BOND_STATE', -1)
            self.show_message(f'[BOND] {dev.getName()} [{addr}] {prev_state} -> {bond_state}', (1,1,0,1))
            if bond_state == 12:
                self.show_message(f'[BOND] Pairing completed for {dev.getName()}', (0,1,0,1))
                if addr in self.pending_connect and self.pending_connect[addr]:
                    self.show_message(f'[INFO] Auto-connecting to {dev.getName()}...', (1,1,0,1))
                    self._do_connect(dev)
                    self.pending_connect.pop(addr, None)
        except Exception as e:
            self.show_message(f'[ERROR] Bond callback: {e}', (1,0,0,1))

    def on_pairing_request(self, context, intent):
        """拦截配对请求，使用应用内输入的PIN，避免系统对话框"""
        try:
            if intent.getAction() != 'android.bluetooth.device.action.PAIRING_REQUEST':
                return
            device = intent.getParcelableExtra('android.bluetooth.device.extra.DEVICE')
            if not device:
                return
            dev = self.cast_func('android.bluetooth.BluetoothDevice', device)
            addr = dev.getAddress()
            pin = self.pending_pin.get(addr, '0000')
            self.show_message(f'[PAIRING] Using PIN: {pin}', (1,1,0,1))

            from jnius import autoclass
            device_class = dev.getClass()
            # byte[] 类型
            byte_array_class = autoclass('[B')
            set_pin_method = device_class.getMethod("setPin", byte_array_class)
            pin_bytes = pin.encode('utf-8')
            set_pin_method.invoke(dev, pin_bytes)

            # boolean 基本类型
            bool_class = autoclass('java.lang.Boolean').TYPE
            confirm_method = device_class.getMethod("setPairingConfirmation", bool_class)
            confirm_method.invoke(dev, True)

            # 取消系统对话框
            try:
                cancel_method = device_class.getMethod("cancelPairingUserInput")
                cancel_method.invoke(dev)
            except:
                pass
            self.show_message('[PAIRING] PIN accepted, pairing in progress...', (0,1,0,1))
        except Exception as e:
            self.show_message(f'[PAIRING] Failed to set PIN: {e}, system dialog will appear', (1,1,0,1))
            # 不拦截，让系统弹出对话框

    def start_scan(self, instance):
        try:
            if not self.adapter:
                self.show_message('[ERROR] Adapter not ready', (1,0,0,1))
                return
            if not self.adapter.isEnabled():
                self.show_message('[ERROR] BT disabled', (1,0,0,1))
                return
            self.device_container.clear_widgets()
            self.devices.clear()
            from android.broadcast import BroadcastReceiver
            self.br = BroadcastReceiver(
                self.on_broadcast,
                actions=['android.bluetooth.device.action.FOUND']
            )
            self.br.start()
            self.adapter.startDiscovery()
            self.scan_btn.text = 'SCANNING...'
            self.scan_btn.disabled = True
            self.show_message('[INFO] Scanning...', (1,1,0,1))
            Clock.schedule_once(self.stop_scan, 12)
        except Exception as e:
            self.show_message(f'[ERROR] Scan start: {e}', (1,0,0,1))

    def stop_scan(self, dt):
        try:
            if self.adapter and self.adapter.isDiscovering():
                self.adapter.cancelDiscovery()
            if self.br:
                self.br.stop()
                self.br = None
            self.show_message('[INFO] Scan stopped', (1,1,0,1))
        except Exception as e:
            self.show_message(f'[ERROR] Stop scan: {e}', (1,0,0,1))
        finally:
            self.scan_btn.text = 'START SCAN'
            self.scan_btn.disabled = False

    def on_broadcast(self, context, intent):
        try:
            if intent.getAction() == 'android.bluetooth.device.action.FOUND':
                raw = intent.getParcelableExtra('android.bluetooth.device.extra.DEVICE')
                if raw:
                    dev = self.cast_func('android.bluetooth.BluetoothDevice', raw)
                    self.add_device(dev)
        except Exception as e:
            self.show_message(f'[ERROR] Broadcast: {e}', (1,0,0,1))

    @mainthread
    def add_device(self, dev):
        try:
            addr = dev.getAddress()
            if addr in self.devices:
                return
            self.devices[addr] = dev
            name = dev.getName() or 'Unknown'
            item = DeviceItem(name, addr, self.on_device_connect)
            self.device_container.add_widget(item)
            self.show_message(f'[DEVICE] {name} [{addr}]', (0,1,0,1))
        except Exception as e:
            self.show_message(f'[ERROR] Add device: {e}', (1,0,0,1))

    def on_device_connect(self, mac_addr, pin):
        dev = self.devices.get(mac_addr)
        if not dev:
            self.show_message('[ERROR] Device not found', (1,0,0,1))
            return
        self.pending_pin[mac_addr] = pin
        bond_state = dev.getBondState()
        self.show_message(f'[CONN] {dev.getName()} bond state: {bond_state}', (1,1,0,1))
        if bond_state == 12:
            self._do_connect(dev)
        elif bond_state == 11:
            self.show_message('[INFO] Pairing in progress, will auto-connect after bond', (1,1,0,1))
            self.pending_connect[mac_addr] = True
        else:
            self.show_message(f'[PAIR] Starting pairing with {dev.getName()} using PIN {pin}', (1,1,0,1))
            if self.adapter.isDiscovering():
                self.adapter.cancelDiscovery()
            self.pending_connect[mac_addr] = True
            dev.createBond()

    def _do_connect(self, dev):
        threading.Thread(target=self._try_connect, args=(dev,), daemon=True).start()

    def _try_connect(self, dev):
        name = dev.getName() or 'Unknown'
        # 先尝试RFCOMM
        if self._rfcomm_connect(dev):
            return
        self.show_message(f'[INFO] RFCOMM failed for {name}, trying GATT...', (1,1,0,1))
        self._gatt_connect(dev)

    def _rfcomm_connect(self, dev):
        name = dev.getName() or 'Unknown'
        try:
            from jnius import autoclass
            UUID = autoclass('java.util.UUID')
            SPP_UUID = UUID.fromString("00001101-0000-1000-8000-00805F9B34FB")

            if self.adapter.isDiscovering():
                self.adapter.cancelDiscovery()
            time.sleep(0.3)

            # 1. 安全RFCOMM
            try:
                socket = dev.createRfcommSocketToServiceRecord(SPP_UUID)
                socket.connect()
                Clock.schedule_once(lambda dt, n=name: self.show_message(f'[SUCCESS] RFCOMM connected (secure) to {n}', (0,1,0,1)))
                return True
            except Exception as e:
                err = str(e)[:80]
                Clock.schedule_once(lambda dt, msg=err: self.show_message(f'[DEBUG] Secure fail: {msg}', (1,1,0,1)))

            # 2. 不安全RFCOMM
            try:
                socket = dev.createInsecureRfcommSocketToServiceRecord(SPP_UUID)
                socket.connect()
                Clock.schedule_once(lambda dt, n=name: self.show_message(f'[SUCCESS] RFCOMM connected (insecure) to {n}', (0,1,0,1)))
                return True
            except Exception as e:
                err = str(e)[:80]
                Clock.schedule_once(lambda dt, msg=err: self.show_message(f'[DEBUG] Insecure fail: {msg}', (1,1,0,1)))

            # 3. 反射通道1-5（正确调用方式）
            from jnius import autoclass
            int_class = autoclass('java.lang.Integer').TYPE
            for channel in range(1, 6):
                try:
                    method = dev.getClass().getMethod("createRfcommSocket", int_class)
                    socket = method.invoke(dev, channel)
                    socket.connect()
                    Clock.schedule_once(lambda dt, n=name, ch=channel: self.show_message(f'[SUCCESS] RFCOMM connected (reflection ch{ch}) to {n}', (0,1,0,1)))
                    return True
                except Exception as e:
                    err = str(e)[:50]
                    Clock.schedule_once(lambda dt, ch=channel, msg=err: self.show_message(f'[DEBUG] Channel {ch} fail: {msg}', (1,1,0,1)))
                    continue
            return False
        except Exception as e:
            self.show_message(f'[ERROR] RFCOMM setup error: {e}', (1,0,0,1))
            return False

    def _gatt_connect(self, dev):
        name = dev.getName() or 'Unknown'
        addr = dev.getAddress()
        try:
            from jnius import autoclass, PythonJavaClass, java_method
            from android import activity

            # 正确实现BluetoothGattCallback
            class GattCallback(PythonJavaClass):
                __javacontext__ = 'app'
                __javainterfaces__ = ['android/bluetooth/BluetoothGattCallback']

                def __init__(self, scanner, device_addr, device_name):
                    super().__init__()
                    self.scanner = scanner
                    self.device_addr = device_addr
                    self.device_name = device_name

                @java_method('(Landroid/bluetooth/BluetoothGatt;II)V')
                def onConnectionStateChange(self, gatt, status, newState):
                    if newState == 2:  # STATE_CONNECTED
                        self.scanner.show_message(f'[GATT] Connected to {self.device_name}', (0,1,0,1))
                        gatt.discoverServices()
                    elif newState == 0:  # DISCONNECTED
                        self.scanner.show_message(f'[GATT] Disconnected from {self.device_name}', (1,1,0,1))

                @java_method('(Landroid/bluetooth/BluetoothGatt;I)V')
                def onServicesDiscovered(self, gatt, status):
                    if status == 0:
                        self.scanner.show_message(f'[GATT] Services discovered for {self.device_name}', (0,1,0,1))
                        # 可以在此处实现特征读写
                    else:
                        self.scanner.show_message(f'[GATT] Service discovery failed: {status}', (1,0,0,1))

                @java_method('(Landroid/bluetooth/BluetoothGatt;Landroid/bluetooth/BluetoothCharacteristic;I)V')
                def onCharacteristicRead(self, gatt, characteristic, status):
                    pass

                @java_method('(Landroid/bluetooth/BluetoothGatt;Landroid/bluetooth/BluetoothCharacteristic;I)V')
                def onCharacteristicWrite(self, gatt, characteristic, status):
                    pass

                @java_method('(Landroid/bluetooth/BluetoothGatt;Landroid/bluetooth/BluetoothCharacteristic;[B)V')
                def onCharacteristicChanged(self, gatt, characteristic, value):
                    pass

            callback = GattCallback(self, addr, name)
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            context = PythonActivity.mActivity
            gatt = dev.connectGatt(context, False, callback)
            self.gatt_connections[addr] = gatt
            self.show_message(f'[GATT] Connecting to {name}...', (1,1,0,1))
        except Exception as e:
            self.show_message(f'[ERROR] GATT connection failed: {e}', (1,0,0,1))

    def on_pause(self):
        if self.br:
            self.br.stop()
        if self.bond_receiver:
            self.bond_receiver.stop()
        if self.pairing_receiver:
            self.pairing_receiver.stop()
        for gatt in self.gatt_connections.values():
            try:
                gatt.close()
            except:
                pass
        return True

    def on_resume(self):
        if self.br:
            self.br.start()
        if self.bond_receiver:
            self.bond_receiver.start()
        if self.pairing_receiver:
            self.pairing_receiver.start()
        return True

class MainApp(App):
    def build(self):
        return BluetoothScanner()

if __name__ == '__main__':
    MainApp().run()