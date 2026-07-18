# -*- coding: utf-8 -*-
import rpc
rpc_server, rpc_thread = rpc.start_rpc_server(port=1133, key='', globals=globals(), locals=locals())

from collections import deque
import os
import traceback
import hashlib
import hmac as hmac_lib
import random
import struct
import pyaes

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
PackageManager = autoclass('android.content.pm.PackageManager')
BluetoothProfile = autoclass('android.bluetooth.BluetoothProfile')
BluetoothGattDescriptor = autoclass('android.bluetooth.BluetoothGattDescriptor')
UUID = autoclass('java.util.UUID')
String = autoclass('java.lang.String')
BleBridge = autoclass('org.qgb.ble.BleBridge')
KeyPairGenerator = autoclass('java.security.KeyPairGenerator')
KeyAgreement = autoclass('javax.crypto.KeyAgreement')
KeyFactory = autoclass('java.security.KeyFactory')
ECGenParameterSpec = autoclass('java.security.spec.ECGenParameterSpec')
ECPublicKeySpec = autoclass('java.security.spec.ECPublicKeySpec')
ECPoint = autoclass('java.security.spec.ECPoint')
BigInteger = autoclass('java.math.BigInteger')

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
        color: 1,1,1,1
        font_size: '20sp'
        bold: True
    Label:
        text: app.status_text
        text_size: self.width, None
        halign: 'left'
        valign: 'middle'
        color: 0.7,0.9,1,1
        size_hint_y: None
        height: dp(70)
    Label:
        text: app.device_text
        text_size: self.width, None
        halign: 'left'
        valign: 'middle'
        color: 0.9,0.9,0.9,1
        size_hint_y: None
        height: dp(45)
    Label:
        text: app.handshake_text
        text_size: self.width, None
        halign: 'left'
        valign: 'middle'
        color: 1,0.85,0.4,1
        size_hint_y: None
        height: dp(45)
    BoxLayout:
        size_hint_y: None
        height: dp(48)
        spacing: dp(8)
        Button:
            text: 'Rescan'
            on_release: app.manual_rescan()
        Button:
            text: 'Disconnect'
            on_release: app.manual_disconnect()
        Button:
            text: 'Reconnect'
            on_release: app.manual_reconnect()
    BoxLayout:
        size_hint_y: None
        height: dp(48)
        spacing: dp(8)
        Button:
            text: 'Power Toggle'
            disabled: not app.control_ready
            on_release: app.toggle_power()
        Button:
            text: 'Handshake'
            disabled: not app.gatt_ready
            on_release: app.send_security_handshake()
    BoxLayout:
        orientation: 'vertical'
        size_hint_y: None
        height: dp(170)
        spacing: dp(8)
        Label:
            text: 'Temp: {}°C'.format(app.target_temp)
            color: 1,1,1,1
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
                text: 'Cool'
                disabled: not app.control_ready
                on_release: app.set_mode('cool')
            Button:
                text: 'Heat'
                disabled: not app.control_ready
                on_release: app.set_mode('heat')
            Button:
                text: 'Fan'
                disabled: not app.control_ready
                on_release: app.set_mode('fan')
            Button:
                text: 'Dry'
                disabled: not app.control_ready
                on_release: app.set_mode('dry')
            Button:
                text: 'Auto'
                disabled: not app.control_ready
                on_release: app.set_mode('auto')
        BoxLayout:
            size_hint_y: None
            height: dp(44)
            spacing: dp(8)
            Button:
                text: 'Auto Fan'
                disabled: not app.control_ready
                on_release: app.set_fan('auto')
            Button:
                text: 'Low'
                disabled: not app.control_ready
                on_release: app.set_fan('low')
            Button:
                text: 'Med'
                disabled: not app.control_ready
                on_release: app.set_fan('medium')
            Button:
                text: 'High'
                disabled: not app.control_ready
                on_release: app.set_fan('high')
    Label:
        text: app.control_text
        text_size: self.width, None
        halign: 'left'
        valign: 'middle'
        color: 0.85,1,0.85,1
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
            color: 0.85,0.85,0.85,1
'''
Builder.load_string(KV)

class RootWidget(BoxLayout):
    pass

# ---------- Callbacks ----------
class PermissionCallback(PythonJavaClass):
    __javainterfaces__ = ['org/kivy/android/PythonActivity$PermissionsCallback']
    __javacontext__ = 'app'
    def __init__(self, owner):
        super().__init__()
        self.owner = owner
    @java_method('([Ljava/lang/String;[I)V')
    def onRequestPermissionsResult(self, permissions, grantResults):
        Clock.schedule_once(lambda dt: self.owner._on_permissions_result(permissions, grantResults), 0)

class PyScanListener(PythonJavaClass):
    __javainterfaces__ = ['org/qgb/ble/ScanListener']
    __javacontext__ = 'app'
    def __init__(self, owner):
        super().__init__()
        self.owner = owner
    @java_method('(Ljava/lang/String;Ljava/lang/String;I)V')
    def onDeviceFound(self, address, name, rssi):
        addr = str(address) if address else ''
        dev_name = str(name) if name else ''
        Clock.schedule_once(lambda dt: self.owner._on_scan_device_found(addr, dev_name, int(rssi)), 0)
    @java_method('(I)V')
    def onScanFailed(self, errorCode):
        Clock.schedule_once(lambda dt: self.owner._on_scan_failed(int(errorCode)), 0)
    @java_method('(Ljava/lang/String;)V')
    def onScanError(self, message):
        msg = str(message) if message else ''
        Clock.schedule_once(lambda dt: self.owner._on_scan_error(msg), 0)

class PyGattCallback(PythonJavaClass):
    __javainterfaces__ = ['org/qgb/ble/GattListener']
    __javacontext__ = 'app'
    def __init__(self, owner, generation, device_name):
        super().__init__()
        self.owner = owner
        self.generation = generation
        self.device_name = device_name
    def _valid(self):
        return self.owner and self.generation == self.owner.connection_generation
    @java_method('(II)V')
    def onConnectionStateChange(self, status, newState):
        Clock.schedule_once(lambda dt: self.owner._on_gatt_connection_state_change(
            self.generation, int(status), int(newState)), 0)
    @java_method('(I)V')
    def onServicesDiscovered(self, status):
        Clock.schedule_once(lambda dt: self.owner._on_gatt_services_discovered(
            self.generation, int(status)), 0)
    @java_method('(I)V')
    def onCharacteristicWrite(self, status):
        Clock.schedule_once(lambda dt: self.owner._on_gatt_characteristic_write(
            self.generation, int(status)), 0)
    @java_method('([B)V')
    def onCharacteristicChanged(self, value):
        if value:
            unsigned = [b & 0xFF for b in value]
            hex_data = bytes(unsigned).hex().upper()
        else:
            hex_data = ""
        Clock.schedule_once(lambda dt: self.owner._on_gatt_characteristic_changed(
            self.generation, hex_data), 0)

# ---------- Cryptographic helpers ----------
def hexstr(data: bytes) -> str:
    return data.hex().upper()

def from_hex(s: str) -> bytes:
    s = (s or '').replace(' ', '').replace(':', '')
    if len(s) % 2:
        raise ValueError('even hex length required')
    return bytes.fromhex(s)

def checksum_neg(data: bytes) -> int:
    total = sum(data) & 0xFF
    return (1 + (~total)) & 0xFF

def chunked(data: bytes, size: int):
    for i in range(0, len(data), size):
        yield data[i:i+size]

def hkdf_sha256(ikm: bytes, salt: bytes, info: bytes, length: int) -> bytes:
    if salt is None:
        salt = b'\x00' * 32
    prk = hmac_lib.new(salt, ikm, hashlib.sha256).digest()
    t = b""
    okm = b""
    for i in range(1, (length + 31) // 32 + 1):
        t = hmac_lib.new(prk, t + info + bytes([i]), hashlib.sha256).digest()
        okm += t
    return okm[:length]

# ECDH
def generate_ec_keypair():
    kg = KeyPairGenerator.getInstance("EC")
    ecSpec = ECGenParameterSpec("secp256r1")
    kg.initialize(ecSpec)
    kp = kg.generateKeyPair()
    priv = kp.getPrivate()
    pub = kp.getPublic()
    x = pub.getW().getAffineX().toByteArray()
    y = pub.getW().getAffineY().toByteArray()
    def pad32(b):
        b = bytes(b)
        if len(b) > 32:
            b = b[-32:]
        elif len(b) < 32:
            b = b'\x00' * (32 - len(b)) + b
        return b
    pub_bytes = b'\x04' + pad32(x) + pad32(y)
    return priv, pub_bytes

def ecdh_shared_secret(priv_key, peer_pub_64: bytes) -> bytes:
    x_bytes = peer_pub_64[:32]
    y_bytes = peer_pub_64[32:]
    x = BigInteger(1, x_bytes)
    y = BigInteger(1, y_bytes)
    tmp_kg = KeyPairGenerator.getInstance("EC")
    tmp_kg.initialize(ECGenParameterSpec("secp256r1"))
    tmp_kp = tmp_kg.generateKeyPair()
    params = tmp_kp.getPublic().getParams()
    pub_spec = ECPublicKeySpec(ECPoint(x, y), params)
    kf = KeyFactory.getInstance("EC")
    peer_pub = kf.generatePublic(pub_spec)
    ka = KeyAgreement.getInstance("ECDH")
    ka.init(priv_key)
    ka.doPhase(peer_pub, True)
    shared = ka.generateSecret()
    return bytes(shared)

# AES-CCM implementation using pyaes
def aes_ccm_encrypt(key: bytes, nonce: bytes, plaintext: bytes, aad: bytes=b'', tag_len: int=8) -> bytes:
    # CCM parameters: L = 2 for 8-byte nonce, M = tag_len
    # Build B0 block
    flags = ((aad and 1) << 6) | (((tag_len - 2) // 2) << 3) | (2 - 1)
    b0 = bytes([flags]) + nonce + struct.pack('>H', len(plaintext))
    if aad:
        if len(aad) < 0xFF00:
            aad_len = struct.pack('>H', len(aad))
        else:
            aad_len = b'\xFF\xFE' + struct.pack('>I', len(aad))
        auth_data = b0 + aad_len + aad
    else:
        auth_data = b0
    # CBC-MAC
    mac = bytes(16)
    aes_ecb = pyaes.AESModeOfOperationECB(key)
    for i in range(0, len(auth_data), 16):
        block = auth_data[i:i+16]
        if len(block) < 16:
            block = block + b'\x00' * (16 - len(block))
        mac = aes_ecb.encrypt(xor_bytes(mac, block))
    # CTR mode encryption
    ctr_base = bytes([2 - 1]) + nonce  # flags = (L-1) = 1
    keystream = b''
    ciphertext = b''
    block_count = (len(plaintext) + 15) // 16
    for j in range(block_count):
        ctr_block = ctr_base + struct.pack('>H', j)
        ks = aes_ecb.encrypt(ctr_block)
        keystream += ks
        chunk = plaintext[j*16:(j+1)*16]
        ciphertext += bytes([c ^ k for c, k in zip(chunk, ks)])
    # Final tag
    # Encrypt MAC (first 16 bytes) with CTR using counter 0, then truncate to tag_len
    ctr0 = ctr_base + b'\x00\x00'
    tag_encrypted = aes_ecb.encrypt(ctr0)
    tag = xor_bytes(mac[:tag_len], tag_encrypted[:tag_len])
    return ciphertext + tag

def aes_ccm_decrypt(key: bytes, nonce: bytes, ciphertext_tag: bytes, aad: bytes=b'', tag_len: int=8) -> bytes:
    ciphertext = ciphertext_tag[:-tag_len]
    tag = ciphertext_tag[-tag_len:]
    # Recompute MAC
    flags = ((aad and 1) << 6) | (((tag_len - 2) // 2) << 3) | (2 - 1)
    b0 = bytes([flags]) + nonce + struct.pack('>H', len(ciphertext))
    if aad:
        if len(aad) < 0xFF00:
            aad_len = struct.pack('>H', len(aad))
        else:
            aad_len = b'\xFF\xFE' + struct.pack('>I', len(aad))
        auth_data = b0 + aad_len + aad
    else:
        auth_data = b0
    mac = bytes(16)
    aes_ecb = pyaes.AESModeOfOperationECB(key)
    for i in range(0, len(auth_data), 16):
        block = auth_data[i:i+16]
        if len(block) < 16:
            block = block + b'\x00' * (16 - len(block))
        mac = aes_ecb.encrypt(xor_bytes(mac, block))
    ctr_base = bytes([2 - 1]) + nonce
    ctr0 = ctr_base + b'\x00\x00'
    tag_encrypted = aes_ecb.encrypt(ctr0)
    expected_tag = xor_bytes(mac[:tag_len], tag_encrypted[:tag_len])
    if tag != expected_tag:
        raise ValueError("CCM tag mismatch")
    # Decrypt
    plaintext = b''
    keystream = b''
    for j in range((len(ciphertext) + 15) // 16):
        ctr_block = ctr_base + struct.pack('>H', j)
        ks = aes_ecb.encrypt(ctr_block)
        keystream += ks
        chunk = ciphertext[j*16:(j+1)*16]
        plaintext += bytes([c ^ k for c, k in zip(chunk, ks)])
    return plaintext

def xor_bytes(a, b):
    return bytes(x ^ y for x, y in zip(a, b))

# ---------- Protocol ----------
class MideaProtocol:
    CONN_T1 = 0x01
    CONN_T2 = 0x02
    CONN_T3 = 0x03
    SEC_C1 = 0x01
    SEC_C2 = 0x02
    SEC_C3 = 0x03
    BIZ_TYPE_AC = 32

    def __init__(self):
        self.root_key = None
        self.session_key = None
        self.ec_priv = None
        self.ec_pub_64 = None
        self.conn_seq = random.randint(1, 255)
        self.sec_seq = 0

    def derive_root_key(self, advertis_data_hex: str) -> bytes:
        ad = from_hex(advertis_data_hex) if advertis_data_hex else b''
        self.root_key = hkdf_sha256(ad, None, b'midea_bleapp', 16)
        return self.root_key

    def create_ec_keypair(self):
        priv, pub_full = generate_ec_keypair()
        self.ec_priv = priv
        self.ec_pub_64 = pub_full[1:]  # strip 0x04
        return self.ec_pub_64

    def derive_session_key(self, peer_pub_64: bytes):
        shared = ecdh_shared_secret(self.ec_priv, peer_pub_64)
        self.session_key = hashlib.sha256(shared).digest()[:16]
        return self.session_key

    def build_conn_frame(self, conn_type: int, payload: bytes) -> bytes:
        seq = self.conn_seq
        self.conn_seq = (self.conn_seq + 1) & 0xFF
        body_len = len(payload) + 4
        frame = bytearray(2 + 1 + 1 + 1 + len(payload) + 1)
        frame[0] = 0xAA
        frame[1] = 0x55
        frame[2] = body_len & 0xFF
        frame[3] = seq
        frame[4] = conn_type
        frame[5:5+len(payload)] = payload
        frame[-1] = checksum_neg(frame[2:-1])
        return bytes(frame)

    def build_security_frame(self, cmd: int, body: bytes) -> bytes:
        self.sec_seq = (self.sec_seq + 1) & 0xFF
        length = len(body)
        return bytes([cmd, self.sec_seq, length]) + body

    def encrypt_security_payload(self, key: bytes, security_bytes: bytes) -> bytes:
        nonce = os.urandom(8)
        ct = aes_ccm_encrypt(key, nonce, security_bytes, b'', 8)
        return nonce + ct

    def decrypt_security_payload(self, key: bytes, blob: bytes) -> bytes:
        nonce = blob[:8]
        ct_tag = blob[8:]
        return aes_ccm_decrypt(key, nonce, ct_tag, b'', 8)

    def build_c1_frame(self) -> bytes:
        openid = os.urandom(6)
        sec = self.build_security_frame(self.SEC_C1, openid)
        encrypted = self.encrypt_security_payload(self.root_key, sec)
        return self.build_conn_frame(self.CONN_T2, encrypted)

    def build_c2_frame(self) -> bytes:
        sec = self.build_security_frame(self.SEC_C2, b'')
        encrypted = self.encrypt_security_payload(self.root_key, sec)
        return self.build_conn_frame(self.CONN_T2, encrypted)

    def build_c3_frame(self, my_pub_64: bytes, advertis_data_hex: str) -> bytes:
        ad = from_hex(advertis_data_hex) if advertis_data_hex else b''
        encrypted_ad = aes_ccm_encrypt(self.session_key, os.urandom(8), ad, b'', 8)
        body = my_pub_64 + encrypted_ad
        sec = self.build_security_frame(self.SEC_C3, body)
        encrypted = self.encrypt_security_payload(self.root_key, sec)
        return self.build_conn_frame(self.CONN_T2, encrypted)

    def build_biz_frame(self, biz_type: int, body: bytes) -> bytes:
        length = len(body) + 4
        biz = bytearray(2 + 1 + len(body) + 1)
        biz[0] = biz_type
        biz[1] = length & 0xFF
        biz[2] = 0x00
        biz[3:3+len(body)] = body
        biz[-1] = checksum_neg(biz[:len(body)+3])
        encrypted = aes_ccm_encrypt(self.session_key, os.urandom(8), bytes(biz), b'', 8)
        return self.build_conn_frame(self.CONN_T3, encrypted)

    def parse_conn_frame(self, data: bytes):
        if len(data) < 4:
            return None
        if data[0] != 0xAA or data[1] != 0x55:
            return None
        body_len = data[2]
        frame_len = 2 + 1 + body_len
        if len(data) < frame_len:
            return None
        frame = data[:frame_len]
        chk = checksum_neg(frame[2:-1])
        if chk != frame[-1]:
            return None
        conn_type = frame[4]
        payload = frame[5:-1]
        return conn_type, payload, frame_len

# ---------- Main App ----------
class HualingACApp(App):
    title_text = StringProperty('Midea AC BLE Control')
    status_text = StringProperty('Initializing...')
    device_text = StringProperty('Device: Not Connected')
    handshake_text = StringProperty('Handshake: Not Started')
    control_text = StringProperty('Status: Power=False Temp=25 Mode=cool Fan=auto')
    log_text = StringProperty('')
    gatt_ready = BooleanProperty(False)
    control_ready = BooleanProperty(False)
    target_temp = NumericProperty(25)

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
        self.current_device_addr = ''
        self.current_device_name = ''
        self.current_advertis_data = ''
        self.seen_devices = {}
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
        self.rx_buffer = b''
        self._log('[App] Starting...')
        Clock.schedule_once(lambda dt: self.startup(), 0.2)
        return self.root_widget

    def _log(self, msg):
        print(f'[BLE-DEBUG] {msg}')
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
            f'Status: Power={self.desired_power} '
            f'Temp={int(self.target_temp)} '
            f'Mode={self.desired_mode} '
            f'Fan={self.desired_fan}'
        )

    def on_start(self):
        self._refresh_control_text()
    def on_pause(self):
        self.is_paused = True
        self.stop_scan()
        return True
    def on_resume(self):
        self.is_paused = False
        Clock.schedule_once(lambda dt: self.ensure_scan_or_connect(), 0.8)
    def on_stop(self):
        self.cleanup_all()
    def cleanup_all(self):
        self.cancel_timers()
        self.stop_scan()
        self.disconnect_gatt(False)
    def cancel_timers(self):
        for ev in ('auto_reconnect_event','scan_timeout_event','handshake_timeout_event','auto_send_event'):
            e = getattr(self, ev, None)
            if e:
                try: e.cancel()
                except: pass
                setattr(self, ev, None)

    def startup(self):
        self.request_permissions()
    def _required_permissions(self):
        if int(Build_VERSION.SDK_INT) >= 31:
            return ["android.permission.BLUETOOTH_SCAN", "android.permission.BLUETOOTH_CONNECT"]
        else:
            return ["android.permission.ACCESS_FINE_LOCATION","android.permission.ACCESS_COARSE_LOCATION",
                    "android.permission.BLUETOOTH","android.permission.BLUETOOTH_ADMIN"]
    def request_permissions(self):
        perms = self._required_permissions()
        missing = [p for p in perms if self.activity.checkSelfPermission(p) != PackageManager.PERMISSION_GRANTED]
        if not missing:
            self.permissions_ok = True
            Clock.schedule_once(lambda dt: self.ensure_scan_or_connect(), 0.2)
            return
        self._set_status('[PERM] Requesting permissions...')
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

    def ensure_scan_or_connect(self):
        if self.is_paused or not self.permissions_ok: return
        if self.is_connected or self.is_connecting: return
        if self.current_device_addr:
            self.connect_to_device(self.current_device_addr, self.current_device_name, self.current_advertis_data)
        else:
            self.start_scan()
    def manual_rescan(self):
        self.stop_scan()
        self.disconnect_gatt(True)
        self.seen_devices.clear()
        self.current_device_addr = ''
        Clock.schedule_once(lambda dt: self.start_scan(), 0.2)
    def manual_disconnect(self): self.disconnect_gatt(False)
    def manual_reconnect(self):
        self.disconnect_gatt(False)
        Clock.schedule_once(lambda dt: self.ensure_scan_or_connect(), 0.8)
    def start_scan(self):
        if self.is_paused or not self.permissions_ok: return
        if self.is_scanning: return
        self.stop_scan()
        self.scan_listener = PyScanListener(self)
        self.scan_session = BleBridge.startScan(self.context, self.scan_listener)
        if self.scan_session is not None:
            self.is_scanning = True
            self.scan_timeout_event = Clock.schedule_once(lambda dt: self._on_scan_timeout(), 12)
            self._log('[SCAN] Started')
        else:
            self._log('[SCAN] Failed')
            self.schedule_reconnect()
    def stop_scan(self):
        self.is_scanning = False
        if self.scan_timeout_event:
            self.scan_timeout_event.cancel()
            self.scan_timeout_event = None
        if self.scan_session:
            try: self.scan_session.stop()
            except: pass
            self.scan_session = None
        self.scan_listener = None
    def _on_scan_timeout(self):
        self.scan_timeout_event = None
        if self.is_connected or self.is_connecting: return
        self._log('[SCAN] Timeout')
        self.stop_scan()
        self.schedule_reconnect()
    def _on_scan_failed(self, code):
        self._log(f'[SCAN] Failed {code}')
        self.stop_scan()
        self.schedule_reconnect()
    def _on_scan_error(self, msg):
        self._log(f'[SCAN] Error {msg}')
        self.stop_scan()
        self.schedule_reconnect()
    def _on_scan_device_found(self, addr, name, rssi):
        if not addr: return
        score = 0
        n = (name or '').lower()
        if 'midea' in n: score += 100
        if 'hualing' in n: score += 100
        if 'air' in n or 'ac' in n: score += 20
        score += max(-100, min(0, int(rssi))) + 100
        self.seen_devices[addr] = {'address':addr,'name':name,'rssi':rssi,'score':score}
        self._log(f'[SCAN] Found {name} {addr} rssi={rssi} score={score}')
    def connect_to_device(self, address, name='', advertis_data_hex=''):
        if self.is_connecting or self.is_connected: return
        if not address: return
        self.disconnect_gatt(False)
        self.stop_scan()
        self.is_connecting = True
        self.is_connected = False
        self.gatt_ready = False
        self.control_ready = False
        self.notification_ready = False
        self.handshake_done = False
        self.write_queue.clear()
        self.write_in_progress = False
        self.rx_buffer = b''
        self.current_device_addr = address
        self.current_device_name = name or 'Unknown'
        self.current_advertis_data = advertis_data_hex
        self.device_text = f'Device: {self.current_device_name} [{address}]'
        self.handshake_text = 'Handshake: Connecting'
        self.connection_generation += 1
        gen = self.connection_generation
        self.gatt_callback = PyGattCallback(self, gen, name)
        self._log(f'[GATT] Connecting to {address}...')
        try:
            self.gatt = BleBridge.connectGatt(self.context, String(address), False, self.gatt_callback)
            if not self.gatt:
                self.is_connecting = False
                self.schedule_reconnect()
        except Exception as e:
            self._log(f'[GATT] connect error {e}')
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
        self.connection_generation += 1
        if self.handshake_timeout_event:
            self.handshake_timeout_event.cancel()
            self.handshake_timeout_event = None
        if self.gatt:
            try:
                self.gatt.disconnect()
                self.gatt.close()
            except: pass
            self.gatt = None
        self.gatt_callback = None
        self.write_char = None
        if clear_target:
            self.current_device_addr = ''
            self.current_device_name = ''
            self.current_advertis_data = ''
            self.device_text = 'Device: Not Connected'
        self.handshake_text = 'Handshake: Not Started'
    def schedule_reconnect(self, delay=2.5):
        if self.is_paused: return
        if self.auto_reconnect_event:
            self.auto_reconnect_event.cancel()
        self.auto_reconnect_event = Clock.schedule_once(lambda dt: self.ensure_scan_or_connect(), delay)

    def _on_gatt_connection_state_change(self, gen, status, newState):
        if gen != self.connection_generation: return
        if newState == BluetoothProfile.STATE_CONNECTED and status == 0:
            self.is_connecting = False
            self.is_connected = True
            self._log('[GATT] Connected')
            self.handshake_text = 'Handshake: Service Discovery'
            if self.gatt: self.gatt.discoverServices()
        elif newState == BluetoothProfile.STATE_DISCONNECTED:
            self._log(f'[GATT] Disconnected status={status}')
            self.disconnect_gatt(False)
            self.schedule_reconnect()
    def _on_gatt_services_discovered(self, gen, status):
        if gen != self.connection_generation: return
        if status != 0:
            self._log(f'[GATT] Service discovery failed {status}')
            self.disconnect_gatt(False)
            return
        if not self.gatt: return
        try:
            srv = self.gatt.getService(UUID.fromString(self.MIDEA_SERVICE_UUID))
            if not srv:
                self._log('[GATT] FFA0 not found')
                self.disconnect_gatt(False)
                return
            self.write_char = srv.getCharacteristic(UUID.fromString(self.MIDEA_WRITE_UUID))
            notify_char = srv.getCharacteristic(UUID.fromString(self.MIDEA_NOTIFY_UUID))
            if notify_char:
                self.gatt.setCharacteristicNotification(notify_char, True)
                cccd = notify_char.getDescriptor(UUID.fromString(self.CCCD_UUID))
                if cccd:
                    cccd.setValue(BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE)
                    self.gatt.writeDescriptor(cccd)
                self.notification_ready = True
            self.gatt_ready = True
            self._log('[GATT] Services ready')
            self.device_text = f'Device: {self.current_device_name} [{self.current_device_addr}]  FFA0 ready'
            self.handshake_text = 'Handshake: ready to send C1'
            if not self.current_advertis_data:
                self._set_status('[ERROR] AdvertisData not set! Use RPC: app.set_advertis_data("hex")')
                return
            self.handshake_timeout_event = Clock.schedule_once(lambda dt: self._on_handshake_timeout(), 30)
            self.protocol.derive_root_key(self.current_advertis_data)
            self.protocol.create_ec_keypair()
            self.send_security_handshake()
        except Exception as e:
            self._log(f'[GATT] Service setup error {e}')
    def _on_handshake_timeout(self):
        self.handshake_timeout_event = None
        if not self.handshake_done and self.is_connected:
            self._log('[SEC] Handshake timeout')
            self.disconnect_gatt(False)
            self.schedule_reconnect()
    def _on_gatt_characteristic_write(self, gen, status):
        if gen != self.connection_generation: return
        self.write_in_progress = False
        self._log(f'[WRITE] status={status}')
        Clock.schedule_once(lambda dt: self._write_next(), 0)
    def _on_gatt_characteristic_changed(self, gen, hex_value):
        if gen != self.connection_generation: return
        data = from_hex(hex_value)
        self.rx_buffer += data
        self._process_rx()

    def _process_rx(self):
        while True:
            res = self.protocol.parse_conn_frame(self.rx_buffer)
            if not res:
                break
            conn_type, payload, frame_len = res
            self.rx_buffer = self.rx_buffer[frame_len:]
            if conn_type == self.protocol.CONN_T2:
                try:
                    sec = self.protocol.decrypt_security_payload(self.protocol.root_key, payload)
                    cmd = sec[0]
                    body = sec[3:] if len(sec) > 3 else b''
                    if cmd == self.protocol.SEC_C1:
                        self._log('[SEC] Received C1 response')
                        self._send_c2()
                    elif cmd == self.protocol.SEC_C2:
                        self._log(f'[SEC] Received C2, peer_pub={hexstr(body)}')
                        if len(body) != 64:
                            self._log('[SEC] Invalid C2 length')
                            return
                        self.protocol.derive_session_key(body)
                        self._send_c3()
                    elif cmd == self.protocol.SEC_C3:
                        self._log('[SEC] Received C3 result')
                        self.handshake_done = True
                        self.control_ready = True
                        self.handshake_text = 'Handshake: Completed'
                        self._set_status('[SEC] Handshake complete')
                        if self.handshake_timeout_event:
                            self.handshake_timeout_event.cancel()
                            self.handshake_timeout_event = None
                        self.send_current_ac_frame()
                    else:
                        self._log(f'[SEC] Unknown cmd {cmd}')
                except Exception as e:
                    self._log(f'[SEC] Decrypt error {e}')
            elif conn_type == self.protocol.CONN_T3:
                if not self.handshake_done:
                    return
                try:
                    biz = aes_ccm_decrypt(self.protocol.session_key, payload[:8], payload[8:], b'', 8)
                    self._log(f'[BIZ] Received {hexstr(biz)}')
                except Exception as e:
                    self._log(f'[BIZ] Decrypt error {e}')

    def _send_c2(self):
        frame = self.protocol.build_c2_frame()
        self.queue_frame(frame, 'c2')
    def _send_c3(self):
        frame = self.protocol.build_c3_frame(self.protocol.ec_pub_64, self.current_advertis_data)
        self.queue_frame(frame, 'c3')
    def send_security_handshake(self, *args):
        if not self.gatt_ready or not self.write_char: return
        frame = self.protocol.build_c1_frame()
        self.queue_frame(frame, 'c1')
    def send_current_ac_frame(self):
        if not self.control_ready: return
        mode_map = {'auto':0x00,'cool':0x01,'dry':0x02,'fan':0x03,'heat':0x04}
        fan_map = {'auto':0x00,'low':0x01,'medium':0x02,'high':0x03}
        body = bytes([0x5A,0x0C,0x02,
                      0x01 if self.desired_power else 0x00,
                      max(16,min(30,int(self.target_temp))),
                      mode_map.get(self.desired_mode,0x01),
                      fan_map.get(self.desired_fan,0x00),
                      0x00,0x00,0x00,0x00])
        biz_frame = self.protocol.build_biz_frame(self.protocol.BIZ_TYPE_AC, body)
        self.queue_frame(biz_frame, 'control')

    def queue_frame(self, frame: bytes, tag=''):
        if not self.gatt or not self.is_connected or not self.write_char: return
        self.write_queue.append((frame, tag))
        self._write_next()
    def _write_next(self):
        if self.write_in_progress or not self.write_queue: return
        if not self.gatt or not self.is_connected or not self.write_char:
            self.write_queue.clear(); return
        frame, tag = self.write_queue.popleft()
        self.last_write_tag = tag
        try:
            self.write_in_progress = True
            self.write_char.setValue(frame)
            ok = self.gatt.writeCharacteristic(self.write_char)
            self._log(f'[WRITE] => {hexstr(frame)} tag={tag} ok={ok}')
            if not ok:
                self.write_in_progress = False
                Clock.schedule_once(lambda dt: self._write_next(), 0)
        except Exception as e:
            self.write_in_progress = False
            self._log(f'[WRITE] error {e}')

    # RPC functions
    def set_advertis_data(self, hex_str):
        self.current_advertis_data = hex_str
        self._log(f'[RPC] advertisData set to {hex_str}')
    def rpc_write_hex(self, hex_str):
        if not self.gatt or not self.is_connected or not self.write_char:
            self._set_status('[RPC] BLE not connected'); return
        try:
            data = bytearray.fromhex(hex_str)
            self.write_char.setValue(data)
            ok = self.gatt.writeCharacteristic(self.write_char)
            self._set_status(f'[RPC] Sent: {hex_str} ok={ok}')
        except Exception as e:
            self._set_status(f'[RPC] Error: {e}')

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
                if self.auto_send_event:
                    self.auto_send_event.cancel()
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
    app = HualingACApp()
    app.run()