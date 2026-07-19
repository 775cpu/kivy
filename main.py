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
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput

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
    padding: dp(8)
    spacing: dp(6)
    canvas.before:
        Color:
            rgba: 0.08, 0.09, 0.11, 1
        Rectangle:
            pos: self.pos
            size: self.size
    BoxLayout:
        size_hint_y: None
        height: dp(40)
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
        height: dp(40)
        spacing: dp(8)
        Label:
            text: 'AdvertisData:'
            size_hint_x: None
            width: dp(100)
            halign: 'left'
            valign: 'middle'
            color: 0.9,0.9,0.9,1
        TextInput:
            id: ad_input
            text: app.advertis_data_input
            multiline: False
            font_size: '14sp'
            background_color: 0.2,0.2,0.2,1
            foreground_color: 1,1,1,1
            on_text: app.advertis_data_input = self.text
    Label:
        text: 'Found devices:'
        size_hint_y: None
        height: dp(20)
        color: 0.9,0.9,0.9,1
    ScrollView:
        size_hint_y: 0.20
        BoxLayout:
            id: device_container
            orientation: 'vertical'
            size_hint_y: None
            height: self.minimum_height
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
            text: 'Power Toggle'
            disabled: not app.control_ready
            on_release: app.toggle_power()
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
        height: dp(50)
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

class DeviceItem(BoxLayout):
    def __init__(self, name, address, callback, **kwargs):
        super().__init__(orientation='horizontal', size_hint_y=None, height=dp(36), **kwargs)
        self.callback = callback
        self.device_address = address
        self.name_label = Label(text=name, size_hint_x=0.5, halign='left', valign='middle', color=(1,1,1,1))
        self.addr_label = Label(text=address, size_hint_x=0.3, halign='center', valign='middle', color=(0.8,0.8,0.8,1))
        self.connect_btn = Button(text='Connect', size_hint_x=0.2)
        self.connect_btn.bind(on_press=lambda x: self.callback(self.device_address))
        self.add_widget(self.name_label)
        self.add_widget(self.addr_label)
        self.add_widget(self.connect_btn)

# ---------- Callbacks ----------
class PermissionCallback(PythonJavaClass):
    __javainterfaces__ = ['org/kivy/android/PythonActivity$PermissionsCallback']
    __javacontext__ = 'app'
    def __init__(self, owner):
        super().__init__()
        self.owner = owner
    @java_method('(I[Ljava/lang/String;[I)V')
    def onRequestPermissionsResult(self, requestCode, permissions, grantResults):
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
    @java_method('(Ljava/lang/String;Ljava/lang/String;ILjava/lang/String;)V')
    def onDeviceFoundWithRecord(self, address, name, rssi, recordHex):
        addr = str(address) if address else ''
        dev_name = str(name) if name else ''
        rec = str(recordHex) if recordHex else ''
        Clock.schedule_once(lambda dt: self.owner._on_scan_device_found(addr, dev_name, int(rssi), rec), 0)

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

    # ---------- 新增：接收 onDescriptorWrite 回调 ----------
    @java_method('(I)V')
    def onDescriptorWrite(self, status):
        Clock.schedule_once(lambda dt: self.owner._on_gatt_descriptor_write(
            self.generation, int(status)), 0)
            
# ---------- Crypto helpers ----------
def hexstr(data): return data.hex().upper()
def from_hex(s):
    s = (s or '').replace(' ', '').replace(':', '')
    if len(s) % 2: raise ValueError('even hex length required')
    return bytes.fromhex(s)
def checksum_neg(data): return (1 + (~(sum(data) & 0xFF))) & 0xFF
def hkdf_sha256(ikm, salt, info, length):
    if salt is None: salt = b'\x00' * 32
    prk = hmac_lib.new(salt, ikm, hashlib.sha256).digest()
    t = b""; okm = b""
    for i in range(1, (length+31)//32+1):
        t = hmac_lib.new(prk, t + info + bytes([i]), hashlib.sha256).digest()
        okm += t
    return okm[:length]

def generate_ec_keypair():
    kg = KeyPairGenerator.getInstance("EC")
    kg.initialize(ECGenParameterSpec("secp256r1"))
    kp = kg.generateKeyPair()
    priv = kp.getPrivate()
    pub = kp.getPublic()
    ec_pub = cast('java.security.interfaces.ECPublicKey', pub)
    x_java = ec_pub.getW().getAffineX().toByteArray()
    y_java = ec_pub.getW().getAffineY().toByteArray()
    x_bytes = bytes([b & 0xFF for b in x_java])
    y_bytes = bytes([b & 0xFF for b in y_java])
    def pad32(b):
        if len(b) > 32: b = b[-32:]
        elif len(b) < 32: b = b'\x00'*(32-len(b))+b
        return b
    pub_bytes = b'\x04' + pad32(x_bytes) + pad32(y_bytes)
    return priv, pub_bytes

def ecdh_shared_secret(priv_key, peer_pub_64):
    x_bytes = peer_pub_64[:32]; y_bytes = peer_pub_64[32:]
    x = BigInteger(1, x_bytes); y = BigInteger(1, y_bytes)
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

# ---------- 修复后的 AES-CCM（nonce=8, tag=8, L=7）----------
def aes_ccm_encrypt(key, nonce, plaintext, aad=b''):
    tag_len = 8
    L = 7
    flags = ((1 if aad else 0) << 6) | (((tag_len - 2) // 2) << 3) | (L - 1)
    b0 = bytes([flags]) + nonce + len(plaintext).to_bytes(L, 'big')

    # 关键修复：认证数据必须包含明文
    if aad:
        if len(aad) < 0xFF00:
            aad_len = struct.pack('>H', len(aad))
        else:
            aad_len = b'\xff\xfe' + struct.pack('>I', len(aad))
        auth_data = b0 + aad_len + aad + plaintext
    else:
        auth_data = b0 + plaintext

    aes = pyaes.AESModeOfOperationECB(key)
    mac = bytearray(16)
    for i in range(0, len(auth_data), 16):
        block = auth_data[i:i+16]
        if len(block) < 16:
            block += b'\x00' * (16 - len(block))
        mac = aes.encrypt(bytes(xor_bytes(mac, block)))

    # 生成密钥流并加密（计数器从 1 开始）
    ctr_flags = L - 1
    ctr_base = bytes([ctr_flags]) + nonce
    keystream = b''
    for j in range(1, (len(plaintext) + 15) // 16 + 1):
        ctr_block = ctr_base + j.to_bytes(L, 'big')
        keystream += aes.encrypt(ctr_block)
    ciphertext = bytes(p ^ k for p, k in zip(plaintext, keystream))

    # 计算 tag
    ctr0 = ctr_base + (0).to_bytes(L, 'big')
    enc_tag = aes.encrypt(ctr0)
    tag = xor_bytes(mac[:tag_len], enc_tag[:tag_len])
    return ciphertext + tag

def aes_ccm_decrypt(key, nonce, ciphertext_tag, aad=b''):
    tag_len = 8
    ciphertext = ciphertext_tag[:-tag_len]
    tag = ciphertext_tag[-tag_len:]

    L = 7
    ctr_flags = L - 1
    ctr_base = bytes([ctr_flags]) + nonce

    # 先解密得到明文
    aes = pyaes.AESModeOfOperationECB(key)
    keystream = b''
    for j in range(1, (len(ciphertext) + 15) // 16 + 1):
        ctr_block = ctr_base + j.to_bytes(L, 'big')
        keystream += aes.encrypt(ctr_block)
    plaintext = bytes(c ^ k for c, k in zip(ciphertext, keystream))

    # 重新计算标签
    flags = ((1 if aad else 0) << 6) | (((tag_len - 2) // 2) << 3) | (L - 1)
    b0 = bytes([flags]) + nonce + len(plaintext).to_bytes(L, 'big')
    if aad:
        if len(aad) < 0xFF00:
            aad_len = struct.pack('>H', len(aad))
        else:
            aad_len = b'\xff\xfe' + struct.pack('>I', len(aad))
        auth_data = b0 + aad_len + aad + plaintext
    else:
        auth_data = b0 + plaintext

    mac = bytearray(16)
    for i in range(0, len(auth_data), 16):
        block = auth_data[i:i+16]
        if len(block) < 16:
            block += b'\x00' * (16 - len(block))
        mac = aes.encrypt(bytes(xor_bytes(mac, block)))

    ctr0 = ctr_base + (0).to_bytes(L, 'big')
    enc_tag = aes.encrypt(ctr0)
    expected_tag = xor_bytes(mac[:tag_len], enc_tag[:tag_len])
    if tag != expected_tag:
        raise ValueError("CCM tag mismatch")
    return plaintext

def xor_bytes(a,b): return bytes(x^y for x,y in zip(a,b))

def crc8_854(data):
    crc=0
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1: crc = (crc>>1)^0x8C
            else: crc >>= 1
    return crc

# ---------- Appliance status parser ----------
def parse_status_frame(data):
    if len(data) < 25 or data[0] != 0xAA or data[10] != 0xC0:
        return None
    state = {}
    run_status = data[11]
    state['power'] = bool(run_status & 0x01)
    state['fault'] = bool(run_status & 0x80)
    mode_map = {1: 'auto', 2: 'cool', 3: 'dry', 4: 'heat', 5: 'fan', 6: 'smart_dry'}
    mode_val = (data[12] >> 5) & 0x07
    state['mode'] = mode_map.get(mode_val, 'unknown')
    temp_int = (data[12] & 0x0F) + 16
    temp_half = (data[12] >> 4) & 0x01
    state['set_temp'] = temp_int + 0.5 * temp_half
    fan_map = {1: 'low', 2: 'medium', 3: 'high', 4: 'strong', 5: 'mute', 6: 'auto', 7: 'fixed'}
    fan_val = data[13] & 0x7F
    state['fan'] = fan_map.get(fan_val, 'unknown')
    indoor_temp = (data[21] - 50) / 2.0
    indoor_temp_frac = (data[25] >> 4) & 0x0F
    state['indoor_temp'] = indoor_temp + indoor_temp_frac * 0.1
    outdoor_temp = (data[22] - 50) / 2.0
    outdoor_temp_frac = data[25] & 0x0F
    state['outdoor_temp'] = outdoor_temp + outdoor_temp_frac * 0.1
    return state

# ---------- Protocol ----------
class MideaProtocol:
    CONN_T1=0x01; CONN_T2=0x02; CONN_T3=0x03
    SEC_C1=0x01; SEC_C2=0x02; SEC_C3=0x03; SEC_C4=0x04
    BIZ_TYPE_AC=32
    def __init__(self):
        self.root_key=None; self.session_key=None; self.ec_priv=None; self.ec_pub_64=None
        self.conn_seq=random.randint(1,255); self.sec_seq=0; self.appliance_order=1
    def derive_root_key(self, ad_hex):
        self.root_key=hkdf_sha256(from_hex(ad_hex),None,b'midea_bleapp',16)
        return self.root_key
    def create_ec_keypair(self):
        priv,pub_full=generate_ec_keypair()
        self.ec_priv=priv; self.ec_pub_64=pub_full[1:]
        return self.ec_pub_64
    def derive_session_key(self, peer_pub_64):
        shared=ecdh_shared_secret(self.ec_priv, peer_pub_64)
        self.session_key=hashlib.sha256(shared).digest()[:16]
        return self.session_key
    def build_conn_frame(self, conn_type, payload):
        seq = self.conn_seq
        self.conn_seq = (self.conn_seq + 1) & 0xFF
        body_len = len(payload) + 4   #协议规定 LEN = len(payload) + 4
        frame = bytearray(2 + 1 + 1 + 1 + len(payload) + 1)
        frame[0] = 0xAA
        frame[1] = 0x55
        frame[2] = body_len & 0xFF
        frame[3] = seq
        frame[4] = conn_type
        frame[5:5+len(payload)] = payload
        frame[-1] = checksum_neg(frame[2:-1])
        return bytes(frame)
        
    def build_security_frame(self, cmd, body):
        self.sec_seq=(self.sec_seq+1)&0xFF; length=len(body)
        return bytes([cmd, self.sec_seq, length])+body
    def encrypt_security_payload(self, key, sec_bytes):
        nonce=os.urandom(8)
        ct=aes_ccm_encrypt(key, nonce, sec_bytes)
        return nonce+ct
    def decrypt_security_payload(self, key, blob):
        nonce=blob[:8]; ct_tag=blob[8:]
        return aes_ccm_decrypt(key, nonce, ct_tag)
    def build_c1_frame(self):
        openid=os.urandom(6)
        sec=self.build_security_frame(self.SEC_C1, openid)
        encrypted=self.encrypt_security_payload(self.root_key, sec)
        return self.build_conn_frame(self.CONN_T2, encrypted)
    def build_c2_frame(self):
        sec=self.build_security_frame(self.SEC_C2, b'')
        encrypted=self.encrypt_security_payload(self.root_key, sec)
        return self.build_conn_frame(self.CONN_T2, encrypted)
    def build_c3_frame(self, my_pub_64, ad_hex):
        ad=from_hex(ad_hex)
        encrypted_ad=aes_ccm_encrypt(self.session_key, os.urandom(8), ad)
        body=my_pub_64+encrypted_ad
        sec=self.build_security_frame(self.SEC_C3, body)
        encrypted=self.encrypt_security_payload(self.root_key, sec)
        return self.build_conn_frame(self.CONN_T2, encrypted)
    def build_biz_frame(self, biz_type, body):
        length=len(body)+4
        biz=bytearray(2+1+len(body)+1)
        biz[0]=biz_type; biz[1]=length&0xFF; biz[2]=0x00
        biz[3:3+len(body)]=body; biz[-1]=checksum_neg(biz[:len(body)+3])
        encrypted=aes_ccm_encrypt(self.session_key, os.urandom(8), bytes(biz))
        return self.build_conn_frame(self.CONN_T3, encrypted)
    def build_query_frame(self):
        order=self.appliance_order; self.appliance_order=(order%255)+1
        frame=bytearray(25)
        frame[0]=0xAA; frame[1]=23; frame[2]=0xAC; frame[8]=0x00; frame[9]=0x03; frame[10]=0x41
        frame[11]=0x21; frame[12]=0x00; frame[13]=0xFF; frame[14]=0x03; frame[15]=0xFF
        frame[16]=0x00; frame[17]=0x02; frame[18:22]=b'\x00\x00\x00\x00'; frame[22]=order
        crc=crc8_854(frame[10:23]); frame[23]=crc
        cs=checksum_neg(frame[1:24]); frame[24]=cs
        return bytes(frame)
    def build_control_frame(self, state):
        order=self.appliance_order; self.appliance_order=(order%255)+1
        frame=bytearray(37)
        frame[0]=0xAA; frame[1]=36; frame[2]=0xAC; frame[8]=0x02; frame[9]=0x02; frame[10]=0x40
        power=state.get('power', False); mode=state.get('mode','cool')
        temp=state.get('temp',25); fan=state.get('fan','auto')
        mode_map={'auto':1,'cool':2,'dry':3,'heat':4,'fan':5}; mode_byte=mode_map.get(mode,2)
        temp_int=max(16, min(30, int(temp)))
        fan_map={'low':1,'medium':2,'high':3,'auto':6,'mute':5,'strong':4}; fan_byte=fan_map.get(fan,6)
        frame[11]=(1 if power else 0)|0x02
        frame[12]=(mode_byte<<5)|(temp_int-16)&0x0F
        frame[13]=fan_byte; frame[17]=0x30
        crc=crc8_854(frame[10:35]); frame[35]=crc
        cs=checksum_neg(frame[1:36]); frame[36]=cs
        return bytes(frame)
    def parse_conn_frame(self, data):
        if len(data)<4: return None
        if data[0]!=0xAA or data[1]!=0x55: return None
        body_len=data[2]; frame_len=2+1+body_len
        if len(data)<frame_len: return None
        frame=data[:frame_len]
        if checksum_neg(frame[2:-1])!=frame[-1]: return None
        conn_type=frame[4]; payload=frame[5:-1]
        return conn_type, payload, frame_len

# ---------- Main App ----------
class HualingACApp(App):
    title_text = StringProperty('Midea AC BLE Control')
    status_text = StringProperty('')
    device_text = StringProperty('')
    handshake_text = StringProperty('')
    control_text = StringProperty('Status: Power=False Temp=25 Mode=cool Fan=auto')
    log_text = StringProperty('')
    gatt_ready = BooleanProperty(False)
    control_ready = BooleanProperty(False)
    target_temp = NumericProperty(25)
    advertis_data_input = StringProperty('AC32323034303535370D368D302724')  # 备用

    MIDEA_SERVICE_UUID = "0000ffa0-0000-1000-8000-00805f9b34fb"
    MIDEA_WRITE_UUID = "0000ffa1-0000-1000-8000-00805f9b34fb"
    MIDEA_NOTIFY_UUID = "0000ffa2-0000-1000-8000-00805f9b34fb"
    CCCD_UUID = "00002902-0000-1000-8000-00805f9b34fb"

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
        self.handshake_started = False
        self.cccd_retry_count = 0
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
        self.c1_timer = None
        self.step_timer = None
        self.c2_frame = None
        self.c3_frame = None
        self.step_count = 0
        self.c1_count = 0
        self.hs_state = 'idle'
        self.desired_state = {'power': False, 'mode': 'cool', 'temp': 25, 'fan': 'auto'}
        self.rx_buffer = b''
        self._log('[App] Starting...')
        Clock.schedule_once(lambda dt: self.startup(), 0.2)
        self._service_discovery_timeout = None
        return self.root_widget

    # ---------- 日志和界面更新 ----------
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
        self.control_text = (f'Status: Power={self.desired_state["power"]} '
                             f'Temp={self.desired_state["temp"]} '
                             f'Mode={self.desired_state["mode"]} '
                             f'Fan={self.desired_state["fan"]}')

    # ---------- Lifecycle ----------
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
        for ev in ('auto_reconnect_event', 'scan_timeout_event', 'handshake_timeout_event',
                   'c1_timer', 'step_timer'):
            e = getattr(self, ev, None)
            if e:
                try:
                    e.cancel()
                except:
                    pass
            setattr(self, ev, None)

    # ---------- Permissions ----------
    def startup(self):
        self.request_permissions()

    def _required_permissions(self):
        if int(Build_VERSION.SDK_INT) >= 31:
            return ["android.permission.BLUETOOTH_SCAN", "android.permission.BLUETOOTH_CONNECT"]
        else:
            return ["android.permission.ACCESS_FINE_LOCATION",
                    "android.permission.ACCESS_COARSE_LOCATION",
                    "android.permission.BLUETOOTH",
                    "android.permission.BLUETOOTH_ADMIN"]

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

    # ---------- Scan/Connect ----------
    def ensure_scan_or_connect(self):
        if self.is_paused or not self.permissions_ok:
            return
        if self.is_connected or self.is_connecting:
            return
        if self.current_device_addr:
            self.connect_to_device(self.current_device_addr, self.current_device_name,
                                   self.current_advertis_data)
        else:
            self.start_scan()

    def manual_rescan(self):
        self._log('[UI] Rescan pressed')
        self.stop_scan()
        self.disconnect_gatt(True)
        self.seen_devices.clear()
        self.current_device_addr = ''
        container = self.root_widget.ids.device_container
        container.clear_widgets()
        Clock.schedule_once(lambda dt: self.start_scan(), 0.2)

    def manual_disconnect(self):
        self._log('[UI] Disconnect pressed')
        self.disconnect_gatt(False)

    def manual_reconnect(self):
        self._log('[UI] Reconnect pressed')
        self.disconnect_gatt(False)
        Clock.schedule_once(lambda dt: self.ensure_scan_or_connect(), 0.8)

    def start_scan(self):
        self._log('[SCAN] start_scan()')
        if self.is_paused or not self.permissions_ok:
            return
        if self.is_scanning:
            return
        self.stop_scan()
        self.seen_devices.clear()
        container = self.root_widget.ids.device_container
        container.clear_widgets()
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
            try:
                self.scan_timeout_event.cancel()
            except:
                pass
            self.scan_timeout_event = None
        if self.scan_session:
            try:
                self.scan_session.stop()
            except:
                pass
            self.scan_session = None
        self.scan_listener = None

    def _on_scan_timeout(self):
        self.scan_timeout_event = None
        if self.is_connected or self.is_connecting:
            return
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

    # ---------- 修改后的扫描回调，接收原始广播数据 ----------
    def _on_scan_device_found(self, addr, name, rssi, record_hex=''):
        if not addr:
            return
        if addr in self.seen_devices:
            return
        # 尝试从广播数据中解析正确的 advertisData
        advertis_data = self._parse_advertis_from_record(record_hex, addr)
        if not advertis_data:
            # 解析失败时，回退使用输入框的值（可能错误）
            advertis_data = self.advertis_data_input.strip()
            self._log(f'[SCAN] Could not parse advertisData from record, using input: {advertis_data}')
        self.seen_devices[addr] = {'name': name, 'rssi': rssi, 'advertis': advertis_data}
        self._log(f'[SCAN] Found {name} {addr} rssi={rssi} advertis={advertis_data}')
        container = self.root_widget.ids.device_container
        item = DeviceItem(name, addr, self.on_device_connect)
        container.add_widget(item)

    # ---------- 广播数据解析方法 ----------
    def _parse_advertis_from_record(self, record_hex, mac_address):
        """从广播原始数据中提取美的空调的 advertisData (AC + SN8 + 逆序MAC)"""
        if not record_hex:
            return None
        try:
            data = bytes.fromhex(record_hex)
        except Exception:
            return None

        # 遍历广播包，寻找 Manufacturer Specific Data (AD type = 0xFF)
        i = 0
        while i < len(data) - 1:
            length = data[i]
            if length == 0 or i + length >= len(data):
                break
            ad_type = data[i+1]
            if ad_type == 0xFF:  # Manufacturer Specific Data
                payload = data[i+2 : i+1+length]
                # 美的公司 ID 为 0x06A8 (小端字节序: A8 06)
                if len(payload) >= 2 and payload[0:2] == b'\xA8\x06':
                    manu_data = payload[2:]   # 跳过公司 ID
                    # 根据文档，美的自定义数据格式：[01][SN14][01 03 00 32][MAC6][00]
                    if len(manu_data) >= 9:
                        # SN14 开始于 manu_data[1] 并取14字节 ASCII
                        sn14_bytes = manu_data[1:15]
                        sn14 = sn14_bytes.decode('ascii', errors='ignore')
                        if len(sn14) == 14:
                            sn8 = sn14[:8]   # 取前8位作为 SN8
                            # MAC 位于 manu_data[19:25] 并需要逆序
                            if len(manu_data) >= 25:
                                mac_bytes = manu_data[19:25]
                                mac_rev = bytes(reversed(mac_bytes))
                                advertis = b'\xAC' + sn8.encode('ascii') + mac_rev
                                return advertis.hex().upper()
                        # 如果 SN14 不是14字节，尝试直接取 manu_data[2:10] 作为 SN8
                        if len(manu_data) >= 10:
                            sn8_bytes = manu_data[2:10]
                            try:
                                sn8 = sn8_bytes.decode('ascii')
                                if len(sn8) == 8 and sn8.isalnum():
                                    mac_clean = mac_address.replace(':', '')
                                    mac_bytes = bytes.fromhex(mac_clean)
                                    mac_rev = bytes(reversed(mac_bytes))
                                    advertis = b'\xAC' + sn8.encode('ascii') + mac_rev
                                    return advertis.hex().upper()
                            except Exception:
                                pass
                    # 未解析成功，记录原始数据以便调试
                    self._log(f'[SCAN] Manu data hex: {manu_data.hex()}')
                break
            i += (length + 1)

        return None

    def on_device_connect(self, mac_addr):
        self._log(f'[UI] Connect pressed for {mac_addr}')
        dev_info = self.seen_devices.get(mac_addr, {})
        advertis_data = dev_info.get('advertis')
        if not advertis_data:
            # 如果解析失败，回退使用输入框里的值
            advertis_data = self.advertis_data_input.strip()
        self.current_advertis_data = advertis_data
        if not self.current_advertis_data:
            self._set_status('[ERROR] advertisData not set!')
            return
        name = dev_info.get('name', '')
        self.connect_to_device(mac_addr, name, self.current_advertis_data)

    def connect_to_device(self, address, name='', advertis_data_hex=''):
        self._log(f'[UI] connect_to_device {address} ({name}) advertisData: {advertis_data_hex}')
        if self.is_connecting or self.is_connected:
            self.disconnect_gatt(False)
            Clock.schedule_once(lambda dt: self.connect_to_device(address, name, advertis_data_hex), 0.6)
            return
        if not address:
            return
        self.disconnect_gatt(False)
        self.stop_scan()
        self.is_connecting = True
        self.is_connected = False
        self.gatt_ready = False
        self.control_ready = False
        self.notification_ready = False
        self.handshake_done = False
        self.handshake_started = False
        self.cccd_retry_count = 0
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
            self.gatt = BleBridge.connectGatt(self.context, String(address), False, 512, self.gatt_callback)
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
        self.handshake_started = False
        self.cccd_retry_count = 0
        self.write_queue.clear()
        self.write_in_progress = False
        self.connection_generation += 1
        self.hs_state = 'idle'
        self._cancel_handshake_timers()
        self.c2_frame = None
        self.c3_frame = None
        self.step_count = 0
        if self._service_discovery_timeout:
            self._service_discovery_timeout.cancel()
            self._service_discovery_timeout = None
        if self.gatt:
            try:
                self.gatt.disconnect()
                self.gatt.close()
            except:
                pass
            self.gatt = None
        self.gatt_callback = None
        self.write_char = None
        if clear_target:
            self.current_device_addr = ''
            self.current_device_name = ''
            self.current_advertis_data = self.advertis_data_input
            self.device_text = ''
        self.handshake_text = ''

    def schedule_reconnect(self, delay=2.5):
        if self.is_paused:
            return
        if self.auto_reconnect_event:
            try:
                self.auto_reconnect_event.cancel()
            except:
                pass
        self.auto_reconnect_event = Clock.schedule_once(lambda dt: self.ensure_scan_or_connect(), delay)

    # ---------- GATT 事件处理 ----------
    def _on_gatt_connection_state_change(self, gen, status, newState):
        if gen != self.connection_generation:
            return
        if newState == BluetoothProfile.STATE_CONNECTED and status == 0:
            self.is_connecting = False
            self.is_connected = True
            self._log('[GATT] Connected')
            self.handshake_text = 'Handshake: Service Discovery'
            if self.gatt:
                self._log('[GATT] Starting service discovery...')
                self.gatt.discoverServices()
                self._service_discovery_timeout = Clock.schedule_once(
                    lambda dt: self._on_service_discovery_timeout(), 10.0)
        elif newState == BluetoothProfile.STATE_DISCONNECTED:
            self._log(f'[GATT] Disconnected status={status}')
            self.disconnect_gatt(False)
            self.schedule_reconnect()

    def _on_service_discovery_timeout(self):
        self._log('[GATT] Service discovery timed out (10s), disconnecting...')
        self.disconnect_gatt(False)
        self.schedule_reconnect()

    def _on_gatt_services_discovered(self, gen, status):
        if self._service_discovery_timeout:
            self._service_discovery_timeout.cancel()
            self._service_discovery_timeout = None
        if gen != self.connection_generation:
            return
        self._log(f'[GATT] Services discovered callback, status={status}')
        if status != 0:
            self._log(f'[GATT] Service discovery failed {status}')
            self.disconnect_gatt(False)
            return
        if not self.gatt:
            return
        try:
            srv = self.gatt.getService(UUID.fromString(self.MIDEA_SERVICE_UUID))
            if not srv:
                self._log('[GATT] FFA0 not found')
                self.disconnect_gatt(False)
                return

            self.write_char = srv.getCharacteristic(UUID.fromString(self.MIDEA_WRITE_UUID))
            if self.write_char:
                self.write_char.setWriteType(2)

            notify_char = srv.getCharacteristic(UUID.fromString(self.MIDEA_NOTIFY_UUID))
            if notify_char:
                props = notify_char.getProperties()
                self._log(f'[GATT] Notify char properties: {props}')
                can_notify = (props & 0x10) != 0
                can_indicate = (props & 0x20) != 0
                if not can_notify and not can_indicate:
                    self._log('[GATT] FFA2 does not support notify/indicate, aborting')
                    self.disconnect_gatt(False)
                    return

                self.gatt.setCharacteristicNotification(notify_char, True)
                cccd = notify_char.getDescriptor(UUID.fromString(self.CCCD_UUID))
                if cccd:
                    if can_notify:
                        enable_val = BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE
                    else:
                        enable_val = BluetoothGattDescriptor.ENABLE_INDICATION_VALUE
                    cccd.setValue(enable_val)
                    self._log(f'[GATT] Writing CCCD with value: {enable_val[0]:02X} {enable_val[1]:02X}')
                    ok = self.gatt.writeDescriptor(cccd)
                    self._log(f'[GATT] writeDescriptor returned: {ok}')
                    if not ok:
                        Clock.schedule_once(lambda dt, d=cccd, v=enable_val: self._retry_write_descriptor(d, v), 0.3)
                else:
                    self._log('[GATT] CCCD descriptor not found')
            else:
                self._log('[GATT] Notify characteristic not found')

            self.gatt_ready = True
            self._log('[GATT] Services ready')
            self.device_text = f'Device: {self.current_device_name} [{self.current_device_addr}]  FFA0 ready'
            self.handshake_text = 'Handshake: waiting for notify setup...'

            if not self.current_advertis_data:
                self._set_status('[ERROR] AdvertisData not set!')
                return

            self.protocol.derive_root_key(self.current_advertis_data)
            self.protocol.create_ec_keypair()
            self.handshake_started = False

        except Exception as e:
            self._log(f'[GATT] Service setup error {e}')

    def _retry_write_descriptor(self, cccd, value):
        if not self.gatt:
            return
        try:
            cccd.setValue(value)
            ok = self.gatt.writeDescriptor(cccd)
            self._log(f'[GATT] retry writeDescriptor returned: {ok}')
        except Exception as e:
            self._log(f'[GATT] retry writeDescriptor error: {e}')

    def _on_gatt_descriptor_write(self, gen, status):
        if gen != self.connection_generation:
            return
        self._log(f'[GATT] onDescriptorWrite status={status}')
        if status == 0:
            self.notification_ready = True
            self._log('[GATT] Notification truly enabled')
            if not self.handshake_started:
                self._start_handshake()
                self.handshake_started = True
        else:
            self.cccd_retry_count += 1
            self._log(f'[GATT] CCCD write failed (attempt {self.cccd_retry_count})')
            if self.cccd_retry_count >= 3:
                self._log('[GATT] Too many CCCD failures, disconnecting')
                self.disconnect_gatt(False)
                return
            if self.gatt:
                try:
                    srv = self.gatt.getService(UUID.fromString(self.MIDEA_SERVICE_UUID))
                    if srv:
                        notify_char = srv.getCharacteristic(UUID.fromString(self.MIDEA_NOTIFY_UUID))
                        if notify_char:
                            cccd = notify_char.getDescriptor(UUID.fromString(self.CCCD_UUID))
                            if cccd:
                                if self.cccd_retry_count == 1:
                                    new_val = BluetoothGattDescriptor.ENABLE_INDICATION_VALUE
                                else:
                                    new_val = BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE
                                cccd.setValue(new_val)
                                self.gatt.writeDescriptor(cccd)
                                self._log(f'[GATT] Retrying CCCD with value: {new_val[0]:02X} {new_val[1]:02X}')
                except Exception as e:
                    self._log(f'[GATT] Retry CCCD error: {e}')

    # ---------- 握手状态机 ----------
    def _start_handshake(self):
        if not self.gatt_ready or not self.write_char:
            return
        self._cancel_handshake_timers()
        self.hs_state = 'c1_wait'
        self.c1_count = 0
        self._send_c1()
        self._schedule_c1_retry()

    def _send_c1(self):
        if not self.gatt_ready or not self.write_char or self.hs_state != 'c1_wait':
            return
        frame = self.protocol.build_c1_frame()
        self.queue_frame(frame, 'c1')
        self.c1_count += 1
        self._log(f'[SEC] Sent C1 #{self.c1_count}')

    def _schedule_c1_retry(self):
        if self.c1_timer:
            self.c1_timer.cancel()
        self.c1_timer = Clock.schedule_once(lambda dt: self._c1_retry(), 1.5)

    def _c1_retry(self):
        if self.hs_state != 'c1_wait':
            return
        if self.c1_count >= 15:
            self._log('[SEC] C1 timeout')
            self.disconnect_gatt(False)
            self.schedule_reconnect()
            return
        self.write_queue.clear()
        self._send_c1()
        self._schedule_c1_retry()

    def _send_c2(self):
        if not self.gatt_ready or not self.write_char or self.hs_state != 'c2_wait':
            return
        self.c2_frame = self.protocol.build_c2_frame()
        self.queue_frame(self.c2_frame, 'c2')
        self.step_count = 0
        self._log('[SEC] Sent C2')

    def _send_c3(self):
        if not self.gatt_ready or not self.write_char or self.hs_state != 'c3_wait':
            return
        self.c3_frame = self.protocol.build_c3_frame(self.protocol.ec_pub_64, self.current_advertis_data)
        self.queue_frame(self.c3_frame, 'c3')
        self.step_count = 0
        self._log('[SEC] Sent C3')

    def _schedule_step_retry(self):
        if self.step_timer:
            self.step_timer.cancel()
        self.step_timer = Clock.schedule_once(lambda dt: self._step_retry(), 1.2)

    def _step_retry(self):
        if self.hs_state not in ('c2_wait', 'c3_wait'):
            return
        self.step_count += 1
        if self.step_count > 8:
            self._log('[SEC] Step timeout')
            self.disconnect_gatt(False)
            self.schedule_reconnect()
            return
        self.write_queue.clear()
        if self.hs_state == 'c2_wait' and self.c2_frame:
            self.queue_frame(self.c2_frame, 'c2_retry')
            self._log('[SEC] Resend C2')
        elif self.hs_state == 'c3_wait' and self.c3_frame:
            self.queue_frame(self.c3_frame, 'c3_retry')
            self._log('[SEC] Resend C3')
        self._schedule_step_retry()

    def _cancel_handshake_timers(self):
        for t in ('c1_timer', 'step_timer'):
            timer = getattr(self, t, None)
            if timer:
                timer.cancel()
                setattr(self, t, None)

    def _on_gatt_characteristic_write(self, gen, status):
        if gen != self.connection_generation:
            return
        self.write_in_progress = False
        self._log(f'[WRITE] status={status}')
        if status != 0:
            self._log(f'[WRITE] status={status} (ignored, keep alive)')
            Clock.schedule_once(lambda dt: self._write_next(), 0.1)
            return
        Clock.schedule_once(lambda dt: self._write_next(), 0)

    def _on_gatt_characteristic_changed(self, gen, hex_value):
        if gen != self.connection_generation:
            return
        data = from_hex(hex_value)
        self.rx_buffer += data
        self._process_rx()

    # ---------- RX 处理 ----------
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
                        if self.hs_state == 'c1_wait':
                            self._cancel_handshake_timers()
                            self.hs_state = 'c2_wait'
                            self._send_c2()
                            self._schedule_step_retry()
                    elif cmd == self.protocol.SEC_C2:
                        self._log(f'[SEC] Received C2, peer_pub={hexstr(body)}')
                        if len(body) != 64:
                            self._log('[SEC] Invalid C2 length')
                            return
                        if self.hs_state == 'c2_wait':
                            self._cancel_handshake_timers()
                            self.protocol.derive_session_key(body)
                            self.hs_state = 'c3_wait'
                            self._send_c3()
                            self._schedule_step_retry()
                    elif cmd == self.protocol.SEC_C3:
                        self._log('[SEC] Received C3 result')
                        if self.hs_state == 'c3_wait':
                            self._cancel_handshake_timers()
                            if len(body) >= 1 and body[0] == 1:
                                self.hs_state = 'biz'
                                self.handshake_done = True
                                self.control_ready = True
                                self.handshake_text = 'Handshake: Completed'
                                self._set_status('[SEC] Handshake complete')
                                self.send_query_frame()
                            else:
                                self._log('[SEC] Handshake failed')
                                self.disconnect_gatt(False)
                                self.schedule_reconnect()
                except Exception as e:
                    self._log(f'[SEC] Decrypt error {e}')
            elif conn_type == self.protocol.CONN_T3:
                if not self.handshake_done:
                    return
                try:
                    nonce = payload[:8]
                    ct_tag = payload[8:]
                    biz = aes_ccm_decrypt(self.protocol.session_key, nonce, ct_tag)
                    self._log(f'[BIZ] Received {hexstr(biz)}')
                    status = parse_status_frame(biz)
                    if status:
                        self.device_text = (
                            f'Power: {status["power"]} | Mode: {status["mode"]} | '
                            f'Set: {status["set_temp"]}°C | Fan: {status["fan"]} | '
                            f'Room: {status["indoor_temp"]}°C | Outdoor: {status["outdoor_temp"]}°C'
                        )
                except Exception as e:
                    self._log(f'[BIZ] Decrypt error {e}')

    # ---------- 写队列 ----------
    def queue_frame(self, frame, tag=''):
        if not self.gatt or not self.is_connected or not self.write_char:
            return
        self.write_queue.append((frame, tag))
        self._write_next()

    def _write_next(self):
        if self.write_in_progress or not self.write_queue:
            return
        if not self.gatt or not self.is_connected or not self.write_char:
            self.write_queue.clear()
            return
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

    # ---------- 业务命令 ----------
    def send_query_frame(self):
        if not self.control_ready:
            return
        query = self.protocol.build_query_frame()
        biz = self.protocol.build_biz_frame(self.protocol.BIZ_TYPE_AC, query)
        self.queue_frame(biz, 'query')

    def send_control_frame(self):
        if not self.control_ready:
            return
        ctrl = self.protocol.build_control_frame(self.desired_state)
        biz = self.protocol.build_biz_frame(self.protocol.BIZ_TYPE_AC, ctrl)
        self.queue_frame(biz, 'control')

    # ---------- RPC ----------
    def set_advertis_data(self, hex_str):
        self.advertis_data_input = hex_str
        self.current_advertis_data = hex_str
        self._log(f'[RPC] advertisData set to {hex_str}')

    def rpc_write_hex(self, hex_str):
        if not self.gatt or not self.is_connected or not self.write_char:
            self._set_status('[RPC] BLE not connected')
            return
        try:
            data = bytearray.fromhex(hex_str)
            self.write_char.setValue(data)
            ok = self.gatt.writeCharacteristic(self.write_char)
            self._set_status(f'[RPC] Sent: {hex_str} ok={ok}')
        except Exception as e:
            self._set_status(f'[RPC] Error: {e}')

    # ---------- UI 操作 ----------
    def toggle_power(self):
        self._log('[UI] Power toggle pressed')
        self.desired_state['power'] = not self.desired_state['power']
        self._refresh_control_text()
        self.send_control_frame()

    def on_temp_slider(self, value):
        new_temp = int(round(value))
        if new_temp != self.desired_state['temp']:
            self._log(f'[UI] Temp slider changed to {new_temp}')
            self.desired_state['temp'] = new_temp
            self._refresh_control_text()
            Clock.schedule_once(lambda dt: self.send_control_frame(), 0.25)

    def set_mode(self, mode):
        self._log(f'[UI] Mode set to {mode}')
        self.desired_state['mode'] = mode
        self._refresh_control_text()
        self.send_control_frame()

    def set_fan(self, fan):
        self._log(f'[UI] Fan set to {fan}')
        self.desired_state['fan'] = fan
        self._refresh_control_text()
        self.send_control_frame()

if __name__=='__main__':
    app=HualingACApp()
    app.run()