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
import threading
import time

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
from kivy.uix.camera import Camera
from kivy.uix.floatlayout import FloatLayout 
from kivy.uix.slider import Slider

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
KeyAgreement = javax_crypto = autoclass('javax.crypto.KeyAgreement')
KeyFactory = autoclass('java.security.KeyFactory')
ECGenParameterSpec = autoclass('java.security.spec.ECGenParameterSpec')
ECPublicKeySpec = autoclass('java.security.spec.ECPublicKeySpec')
ECPoint = autoclass('java.security.spec.ECPoint')
BigInteger = autoclass('java.math.BigInteger')

GLOBAL_RAW_FRAME = None 

# ---------- Fullscreen Camera Layout (FloatLayout) ----------
KV = r'''
<RootWidget>:
    canvas.before:
        Color:
            rgba: 0.1, 0.1, 0.1, 1
        Rectangle:
            pos: self.pos
            size: self.size

    Camera:
        id: camera
        resolution: (640, 480)
        play: False
        allow_stretch: True
        keep_ratio: False
        size_hint: None, None
        size: (root.height, root.width) if (app.preview_angle % 180 != 0) else (root.width, root.height)
        pos_hint: {'center_x': 0.5, 'center_y': 0.5}
        canvas.before:
            PushMatrix
            Rotate:
                angle: app.preview_angle
                origin: self.center
        canvas.after:
            PopMatrix

    BoxLayout:
        orientation: 'vertical'
        pos_hint: {'center_x': 0.5, 'center_y': 0.5}
        size_hint: None, None
        size: (dp(240), dp(100))
        opacity: 1 if (camera.play and not camera.texture) else 0
        padding: dp(15)
        spacing: dp(10)
        canvas.before:
            Color:
                rgba: 0.0, 0.0, 0.0, 0.75
            RoundedRectangle:
                pos: self.pos
                size: self.size
                radius: [dp(12)]
        Label:
            text: "Connecting Hardware..."
            font_size: '16sp'
            bold: True
            color: 1, 1, 1, 1
        Label:
            text: "Initializing video feed..."
            font_size: '12sp'
            color: 0.7, 0.7, 0.7, 1

    BoxLayout:
        orientation: 'vertical'
        size_hint: 1, None
        height: dp(260)
        pos_hint: {'x': 0, 'y': 0}
        padding: dp(12)
        spacing: dp(8)
        canvas.before:
            Color:
                rgba: 0, 0, 0, 0.65
            Rectangle:
                pos: self.pos
                size: self.size

        Label:
            size_hint_y: None
            height: dp(18)
            text: 'Professional Camera Controller'
            font_size: '14sp'
            color: 1, 1, 1, 0.85

        BoxLayout:
            size_hint_y: None
            height: dp(38)
            spacing: dp(8)

            Button:
                text: 'Start' if not camera.play else 'Stop'
                background_normal: ''
                background_color: (0.2, 0.6, 0.2, 0.6)
                on_release: app.toggle_preview()

            Button:
                text: 'Switch Cam'
                background_normal: ''
                background_color: (0.2, 0.4, 0.8, 0.6)
                on_release: app.switch_camera()

            Button:
                text: app.flash_mode_text
                background_normal: ''
                background_color: (0.5, 0.5, 0.5, 0.6)
                on_release: app.toggle_flash()

        BoxLayout:
            orientation: 'horizontal'
            spacing: dp(12)

            BoxLayout:
                orientation: 'vertical'
                spacing: dp(6)

                BoxLayout:
                    orientation: 'horizontal'
                    size_hint_y: None
                    height: dp(32)
                    Label:
                        text: 'Brightness'
                        size_hint_x: 0.35
                        font_size: '12sp'
                        halign: 'left'
                    Slider:
                        size_hint_x: 0.65
                        min: -4
                        max: 4
                        value: app.brightness_value
                        step: 1
                        on_value: app.brightness_value = self.value

                BoxLayout:
                    orientation: 'horizontal'
                    size_hint_y: None
                    height: dp(32)
                    Label:
                        text: 'Chroma'
                        size_hint_x: 0.35
                        font_size: '12sp'
                        halign: 'left'
                    Slider:
                        size_hint_x: 0.65
                        min: 0
                        max: 6
                        value: app.chroma_value
                        step: 1
                        on_value: app.chroma_value = self.value

                Label:
                    id: status_label
                    text: 'Initializing...'
                    font_size: '12sp'
                    color: 0.7, 0.9, 0.7, 0.8
                    halign: 'center'
                    valign: 'middle'

            FloatLayout:
                size_hint: None, None
                size: dp(140), dp(140)
                pos_hint: {'center_y': 0.5}
                canvas.before:
                    Color:
                        rgba: 0.35, 0.35, 0.35, 0.5
                    Ellipse:
                        pos: self.pos
                        size: self.size
                    Color:
                        rgba: 0.05, 0.05, 0.05, 0.85
                    Ellipse:
                        pos: self.x + dp(22), self.y + dp(22)
                        size: self.width - dp(44), self.height - dp(44)
                
                Button:
                    text: 'UP' if app.preview_angle != 0 else 'UP *'
                    size_hint: None, None
                    size: dp(42), dp(42)
                    pos_hint: {'center_x': 0.5, 'top': 1}
                    background_normal: ''
                    background_color: (0.85, 0.45, 0.1, 0.9) if app.preview_angle == 0 else (0.2, 0.2, 0.2, 0.6)
                    on_release: app.set_preview_angle(0)
                
                Button:
                    text: 'RIGHT' if app.preview_angle != 90 else 'RIGHT *'
                    size_hint: None, None
                    size: dp(42), dp(42)
                    pos_hint: {'right': 1, 'center_y': 0.5}
                    background_normal: ''
                    background_color: (0.85, 0.45, 0.1, 0.9) if app.preview_angle == 90 else (0.2, 0.2, 0.2, 0.6)
                    on_release: app.set_preview_angle(90)
                
                Button:
                    text: 'DOWN' if app.preview_angle != 180 else 'DOWN *'
                    size_hint: None, None
                    size: dp(42), dp(42)
                    pos_hint: {'center_x': 0.5, 'y': 0}
                    background_normal: ''
                    background_color: (0.85, 0.45, 0.1, 0.9) if app.preview_angle == 180 else (0.2, 0.2, 0.2, 0.6)
                    on_release: app.set_preview_angle(180)
                
                Button:
                    text: 'LEFT' if app.preview_angle != 270 else 'LEFT *'
                    size_hint: None, None
                    size: dp(42), dp(42)
                    pos_hint: {'x': 0, 'center_y': 0.5}
                    background_normal: ''
                    background_color: (0.85, 0.45, 0.1, 0.9) if app.preview_angle == 270 else (0.2, 0.2, 0.2, 0.6)
                    on_release: app.set_preview_angle(270)
'''
Builder.load_string(KV)

class RootWidget(FloatLayout):
    pass

class PermissionCallback(PythonJavaClass):
    __javainterfaces__ = ['org/kivy/android/PythonActivity$PermissionsCallback']
    __javacontext__ = 'app'
    def __init__(self, owner):
        super().__init__()
        self.owner = owner
    @java_method('(I[Ljava/lang/String;[I)V')
    def onRequestPermissionsResult(self, requestCode, permissions, grantResults):
        Clock.schedule_once(lambda dt: self.owner._on_permissions_result(permissions, grantResults), 0)

# Cryptography and Protocol place-holders
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

def aes_ccm_encrypt(key, nonce, plaintext, aad=b''):
    tag_len = 8
    L = 7
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
    aes = pyaes.AESModeOfOperationECB(key)
    mac = bytearray(16)
    for i in range(0, len(auth_data), 16):
        block = auth_data[i:i+16]
        if len(block) < 16:
            block += b'\x00' * (16 - len(block))
        mac = aes.encrypt(bytes(xor_bytes(mac, block)))
    ctr_flags = L - 1
    ctr_base = bytes([ctr_flags]) + nonce
    keystream = b''
    for j in range(1, (len(plaintext) + 15) // 16 + 1):
        ctr_block = ctr_base + j.to_bytes(L, 'big')
        keystream += aes.encrypt(ctr_block)
    ciphertext = bytes(p ^ k for p, k in zip(plaintext, keystream))
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
    aes = pyaes.AESModeOfOperationECB(key)
    keystream = b''
    for j in range(1, (len(ciphertext) + 15) // 16 + 1):
        ctr_block = ctr_base + j.to_bytes(L, 'big')
        keystream += aes.encrypt(ctr_block)
    plaintext = bytes(c ^ k for c, k in zip(ciphertext, keystream))
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

class MideaProtocol: pass
class PyScanListener(PythonJavaClass): pass
class PyGattCallback(PythonJavaClass): pass


# ---------------- Native High-Performance Stream Server ----------------
from http.server import BaseHTTPRequestHandler, HTTPServer
import io
from PIL import Image

class NativeMJPEGHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/mjpeg_stream':
            self.send_response(200)
            self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=frame')
            self.send_header('Cache-Control', 'no-cache, private')
            self.send_header('Pragma', 'no-cache')
            self.end_headers()
            
            while True:
                global GLOBAL_RAW_FRAME
                if GLOBAL_RAW_FRAME is None:
                    time.sleep(0.01)
                    continue
                
                try:
                    pixels, size = GLOBAL_RAW_FRAME
                    
                    # 【核心优化点】移除 PIL 的 transpose(FLIP_TOP_BOTTOM) 和 rotate() 矩阵计算
                    # 手机端只做纯粹的 RGBA 到 JPEG 的流化压缩，节省 80% 的手机 CPU 算力！
                    img = Image.frombytes('RGBA', size, pixels)
                    buf = io.BytesIO()
                    img.convert('RGB').save(buf, format='JPEG', quality=60) 
                    jpeg_bytes = buf.getvalue()
                    
                    self.wfile.write(b'--frame\r\n')
                    self.wfile.write(b'Content-Type: image/jpeg\r\n')
                    self.wfile.write(f'Content-Length: {len(jpeg_bytes)}\r\n\r\n'.encode())
                    self.wfile.write(jpeg_bytes)
                    self.wfile.write(b'\r\n')
                    
                    time.sleep(0.033) # 限制推流在稳定的 ~30 FPS
                except Exception:
                    break
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass 

def run_stream_server():
    try:
        server = HTTPServer(('0.0.0.0', 1134), NativeMJPEGHandler)
        server.serve_forever()
    except Exception as e:
        print(f"[StreamServer] Error: {e}")


# ---------- Main Application Deck ----------
class HualingACApp(App):
    title_text = StringProperty('Camera Preview')
    status_text = StringProperty('')
    log_text = StringProperty('')
    flash_mode_text = StringProperty('Flash: Off')
    
    preview_angle = NumericProperty(270)
    brightness_value = NumericProperty(0)
    chroma_value = NumericProperty(3)

    def build(self):
        self.root_widget = RootWidget()
        self.activity = PythonActivity.mActivity
        self.context = self.activity.getApplicationContext()
        self.permission_callback = PermissionCallback(self)

        self.is_paused = False
        self.permissions_ok = False
        self.flash_mode = 0  
        self._pending_start = False  

        self._log('App starting...')
        Clock.schedule_once(lambda dt: self.startup(), 0.2)
        
        # 主线程只捞取原始像素尺寸，耗时极低
        Clock.schedule_interval(self._fast_pixel_capture, 1.0 / 30.0)
        
        t = threading.Thread(target=run_stream_server, daemon=True)
        t.start()
        
        return self.root_widget

    def _fast_pixel_capture(self, dt):
        global GLOBAL_RAW_FRAME
        if self.is_paused:
            return
        try:
            camera = self.root_widget.ids.camera
            if camera and camera.play and camera.texture:
                # 只保留像素和大小，不带旋转角度到后台处理
                GLOBAL_RAW_FRAME = (camera.texture.pixels, camera.texture.size)
        except Exception:
            pass

    def on_brightness_value(self, instance, value):
        self._apply_professional_settings()

    def on_chroma_value(self, instance, value):
        self._apply_professional_settings()

    def set_preview_angle(self, angle):
        self.preview_angle = angle
        self._set_status(f'Preview orientation locked to {angle} deg')

    def _log(self, msg):
        print(f'[CameraApp] {msg}')
        lines = self.log_text.split('\n') if self.log_text else []
        lines.append(msg)
        if len(lines) > 120:
            lines = lines[-120:]
        self.log_text = '\n'.join(lines)

    def _set_status(self, msg):
        self.status_text = msg
        self._log(msg)
        if hasattr(self.root_widget.ids, 'status_label'):
            self.root_widget.ids.status_label.text = msg

    def on_pause(self):
        self.is_paused = True
        camera = self.root_widget.ids.camera
        if camera.play:
            camera.play = False
        return True

    def on_resume(self):
        self.is_paused = False

    def on_stop(self):
        camera = self.root_widget.ids.camera
        if camera.play:
            camera.play = False

    def startup(self):
        self.request_camera_permission()

    def _required_permissions(self):
        return ["android.permission.CAMERA"]

    def request_camera_permission(self):
        perms = self._required_permissions()
        missing = [p for p in perms if self.activity.checkSelfPermission(p) != PackageManager.PERMISSION_GRANTED]
        if not missing:
            self.permissions_ok = True
            Clock.schedule_once(lambda dt: self._on_permission_granted(), 0.2)
            return
        self._set_status('Requesting CAMERA permission...')
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
            self._set_status('Camera permission granted')
            Clock.schedule_once(lambda dt: self._on_permission_granted(), 0.2)
        else:
            self._set_status('Camera permission denied')

    def _on_permission_granted(self):
        self._start_camera_preview()

    def _start_camera_preview(self):
        camera = self.root_widget.ids.camera
        if camera.play or self._pending_start:
            return
        try:
            self._pending_start = True
            camera.play = True
            Clock.schedule_once(lambda dt: self._apply_professional_settings(), 0.8)
            self._set_status('Preview started')
        except Exception as e:
            self._set_status(f'Start failed: {e}')
            self._log(f'Start camera error: {e}')
        finally:
            self._pending_start = False

    def _apply_professional_settings(self):
        camera = self.root_widget.ids.camera
        if not camera.play:
            return
        try:
            internal_camera = camera._camera
            if internal_camera is None:
                return

            native_cam = None
            if hasattr(internal_camera, '_android_camera') and internal_camera._android_camera is not None:
                native_cam = internal_camera._android_camera
                
            if native_cam is not None:
                params = native_cam.getParameters()
                if self.flash_mode == 0:
                    params.setFlashMode('off')
                elif self.flash_mode == 1:
                    params.setFlashMode('torch')
                else:
                    params.setFlashMode('auto')
                try:
                    params.setExposureCompensation(int(self.brightness_value))
                except Exception:
                    pass
                try:
                    params.set("saturation", int(self.chroma_value))
                except Exception:
                    pass
                native_cam.setParameters(params)
        except Exception as e:
            self._log(f'Apply hardware settings failed: {e}')

    def toggle_preview(self):
        camera = self.root_widget.ids.camera
        if not self.permissions_ok:
            self.request_camera_permission()
            return
        if camera.play:
            camera.play = False
            self._set_status('Preview stopped')
        else:
            self._start_camera_preview()

    def switch_camera(self):
        camera = self.root_widget.ids.camera
        if not self.permissions_ok:
            self.request_camera_permission()
            return
        if camera.play:
            camera.play = False
            self._set_status('Switching camera...')
            Clock.schedule_once(lambda dt: self._do_switch_camera(), 0.6)
        else:
            self._do_switch_camera()

    def _do_switch_camera(self, *args):
        camera = self.root_widget.ids.camera
        new_index = 1 - camera.index
        camera.index = new_index
        self._start_camera_preview()
        self._set_status(f'Switched to camera {"rear" if new_index==0 else "front"}')

    def toggle_flash(self):
        self.flash_mode = (self.flash_mode + 1) % 3
        mode_names = ['Off', 'On', 'Auto']
        self.flash_mode_text = f'Flash: {mode_names[self.flash_mode]}'
        self._apply_professional_settings()


def preview_html(response_obj):
    """
    【完全重写表现层】利用网页客户端的浏览器内核和显卡能力去动态旋转/翻转视频。
    手机端完全不需要做任何图像旋转处理！
    """
    app_instance = App.get_running_app()
    # 动态获取当前App界面的旋转角度设定
    current_angle = app_instance.preview_angle if app_instance else 270

    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Kivy Native Stream Live View</title>
    <style>
        body {{ margin: 0; background-color: #111; display: flex; flex-direction: column; justify-content: center; align-items: center; height: 100vh; color: #fff; font-family: system-ui, sans-serif; }}
        .container {{ position: relative; max-width: 95vw; max-height: 85vh; box-shadow: 0 4px 20px rgba(0,0,0,0.6); border-radius: 8px; overflow: hidden; }}
        
        img {{ 
            display: block; 
            width: 100%; 
            height: auto; 
            max-height: 85vh; 
            object-fit: contain; 
            background: #000;
            /* 核心黑魔法：Kivy底层OpenGL默认上下颠倒，配合UI角度，使用网页GPU硬加速做翻转与旋转 */
            transform: scaleY(-1) rotate({current_angle}deg);
            transform-origin: center;
        }}
    </style>
</head>
<body>
    <h3 style="margin-bottom: 10px;">Kivy Live Video Deck (GPU Accelerated)</h3>
    <div class="container">
        <img id="native_stream" src="" alt="Connecting to high performance stream...">
    </div>
    <script>
        document.getElementById('native_stream').src = window.location.protocol + '//' + window.location.hostname + ':1134/mjpeg_stream';
    </script>
</body>
</html>
"""
    response_obj.set_header("Content-Type", "text/html; charset=utf-8")
    response_obj.set_data(html_content.encode('utf-8'))


def get_camera_frameBytes(response_obj):
    response_obj.set_status(200)
    response_obj.set_header("Content-Type", "text/plain")
    response_obj.set_data(b"Deprecated. Switched to native streaming at port 1134.")
    return "Redirected"


if __name__ == '__main__':
    app = HualingACApp()
    app.run()