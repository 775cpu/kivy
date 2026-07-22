# -*- coding: utf-8 -*-
import rpc
rpc_server, rpc_thread = rpc.start_rpc_server(port=1133, key='', globals=globals(), locals=locals())

import os, traceback, hashlib, random, struct, pyaes, threading, time, io
from collections import deque
from http.server import BaseHTTPRequestHandler, HTTPServer

from kivy.app import App
from kivy.clock import Clock
from kivy.lang import Builder
from kivy.metrics import dp
from kivy.properties import StringProperty, BooleanProperty, NumericProperty, ListProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.uix.camera import Camera
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.slider import Slider
from kivy.uix.widget import Widget
from kivy.graphics import Color, Line, Rectangle

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

# Android 原生图像处理类
YuvImage = autoclass('android.graphics.YuvImage')
Rect = autoclass('android.graphics.Rect')
ImageFormat = autoclass('android.graphics.ImageFormat')
ByteArrayOutputStream = autoclass('java.io.ByteArrayOutputStream')

# 全局帧数据（线程安全）
GLOBAL_JPEG_BYTES = None
GLOBAL_YUV_DATA = None
GLOBAL_CAM_WIDTH = 640
GLOBAL_CAM_HEIGHT = 480
DETECTION_RESULTS = []
FPS = 0

# 线程锁
yuv_lock = threading.Lock()
jpeg_lock = threading.Lock()        # 非阻塞 JPEG 编码锁
result_lock = threading.Lock()

# ---------- Pyjnius 原生回调（非阻塞 JPEG 编码）----------
class AndroidPreviewCallback(PythonJavaClass):
    __javainterfaces__ = ['android/hardware/Camera$PreviewCallback']
    __javacontext__ = 'app'

    def __init__(self):
        super().__init__()
        self.quality = 60  # 适当降低质量以加快压缩速度

    @java_method('([BLandroid/hardware/Camera;)V')
    def onPreviewFrame(self, data, camera):
        global GLOBAL_JPEG_BYTES, GLOBAL_YUV_DATA
        try:
            w, h = GLOBAL_CAM_WIDTH, GLOBAL_CAM_HEIGHT
            # 先转换 Python bytes，供 YOLO 线程使用
            b_data = bytes(data)
            with yuv_lock:
                GLOBAL_YUV_DATA = b_data

            # 非阻塞 JPEG 压缩：如果上一帧还在处理中，直接丢弃本帧
            if jpeg_lock.acquire(blocking=False):
                try:
                    yuv = YuvImage(data, ImageFormat.NV21, w, h, None)
                    bos = ByteArrayOutputStream()
                    yuv.compressToJpeg(Rect(0, 0, w, h), self.quality, bos)
                    GLOBAL_JPEG_BYTES = bos.toByteArray()
                finally:
                    jpeg_lock.release()
        except Exception as e:
            print(f"[NativeCallbackError] {e}")

NATIVE_CALLBACK = AndroidPreviewCallback()

# ---------- KV UI 定义（包含 YOLO 开关）----------
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

    Widget:
        id: detect_overlay
        size_hint: None, None
        size: (root.height, root.width) if (app.preview_angle % 180 != 0) else (root.width, root.height)
        pos_hint: {'center_x': 0.5, 'center_y': 0.5}

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
        height: dp(290)
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
                text: 'YOLO: ON' if app.yolo_enabled else 'YOLO: OFF'
                background_normal: ''
                background_color: (0.2, 0.8, 0.2, 0.6) if app.yolo_enabled else (0.5, 0.5, 0.5, 0.6)
                on_release: app.toggle_yolo()

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

                Label:
                    id: fps_label
                    text: 'FPS: --'
                    font_size: '12sp'
                    color: 1, 0.8, 0.3, 0.9
                    halign: 'center'

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

# ---------- HTTP Stream Server ----------
class NativeMJPEGHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith('/mjpeg_stream'):
            self.send_response(200)
            self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=frame')
            self.send_header('Cache-Control', 'no-cache, private')
            self.send_header('Pragma', 'no-cache')
            self.end_headers()
            while True:
                # 安全读取 JPEG 数据（无需锁，因为是原子引用替换）
                jpeg_bytes = GLOBAL_JPEG_BYTES
                if jpeg_bytes is None:
                    time.sleep(0.05)
                    continue
                try:
                    self.wfile.write(b'--frame\r\n')
                    self.wfile.write(b'Content-Type: image/jpeg\r\n')
                    self.wfile.write(f'Content-Length: {len(jpeg_bytes)}\r\n\r\n'.encode())
                    self.wfile.write(jpeg_bytes)
                    self.wfile.write(b'\r\n')
                    time.sleep(0.03)
                except Exception:
                    break
        elif self.path == '/' or self.path == '/index.html':
            preview_html(self)
        else:
            self.send_response(404)
            self.end_headers()

    def set_header(self, key, value):
        self.send_header(key, value)
    def set_data(self, data):
        self.end_headers()
        self.wfile.write(data)
    def set_status(self, code):
        self.send_response(code)
    def log_message(self, format, *args):
        pass

def run_stream_server():
    try:
        server = HTTPServer(('0.0.0.0', 1134), NativeMJPEGHandler)
        server.serve_forever()
    except Exception as e:
        print(f"[StreamServer] Error: {e}")

# 全局添加配置变量（放在文件开头全局变量区）
MODEL_INPUT_WIDTH = 320
MODEL_INPUT_HEIGHT = 320

# 修改 detection_worker 函数内部
def detection_worker():
    global DETECTION_RESULTS, FPS, GLOBAL_YUV_DATA, GLOBAL_CAM_WIDTH, GLOBAL_CAM_HEIGHT
    import numpy
    from PIL import Image

    try:
        import tflite_runtime.interpreter as tflite
    except ImportError:
        try:
            import tensorflow.lite as tflite
        except ImportError:
            print("[Detection] Error: no tflite")
            tflite = None

    interpreter = None
    input_details = None
    output_details = None
    input_shape = (MODEL_INPUT_WIDTH, MODEL_INPUT_HEIGHT)  # 320x320 提速
    is_nchw = False
    model_path = "yolov8n_float32.tflite"

    if tflite and os.path.exists(model_path):
        try:
            interpreter = tflite.Interpreter(model_path=model_path)#, num_threads=4 崩溃
            interpreter.allocate_tensors()
            input_details = interpreter.get_input_details()
            output_details = interpreter.get_output_details()
            in_shape = input_details[0]['shape']
            if len(in_shape) == 4:
                if in_shape[1] == 3:
                    is_nchw = True
                    input_shape = (in_shape[3], in_shape[2])
                else:
                    is_nchw = False
                    input_shape = (in_shape[2], in_shape[1])
            print(f"[Detection] Loaded. Input {input_shape}, NCHW: {is_nchw}")
        except Exception as e:
            print(f"[Detection] Model load error: {e}")
            interpreter = None

    def nv21_to_rgb(data, w, h):
        y_size = w * h
        y = numpy.frombuffer(data[:y_size], dtype=numpy.uint8).reshape((h, w)).astype(numpy.float32)
        vu = numpy.frombuffer(data[y_size:], dtype=numpy.uint8).reshape((h//2, w//2, 2)).astype(numpy.float32)
        v = numpy.repeat(numpy.repeat(vu[:,:,0] - 128.0, 2, axis=0), 2, axis=1)
        u = numpy.repeat(numpy.repeat(vu[:,:,1] - 128.0, 2, axis=0), 2, axis=1)
        r = numpy.clip(y + 1.402 * v, 0, 255)
        g = numpy.clip(y - 0.344136 * u - 0.714136 * v, 0, 255)
        b = numpy.clip(y + 1.772 * u, 0, 255)
        return numpy.stack([r, g, b], axis=-1).astype(numpy.uint8)

    def pure_nms(boxes, scores, iou_thresh=0.45):
        if len(boxes) == 0: return []
        x1, y1, x2, y2 = boxes[:,0], boxes[:,1], boxes[:,2], boxes[:,3]
        areas = (x2 - x1) * (y2 - y1)
        order = scores.argsort()[::-1]
        keep = []
        while order.size > 0:
            i = order[0]
            keep.append(i)
            xx1 = numpy.maximum(x1[i], x1[order[1:]])
            yy1 = numpy.maximum(y1[i], y1[order[1:]])
            xx2 = numpy.minimum(x2[i], x2[order[1:]])
            yy2 = numpy.minimum(y2[i], y2[order[1:]])
            w_inter = numpy.maximum(0, xx2-xx1)
            h_inter = numpy.maximum(0, yy2-yy1)
            inter = w_inter * h_inter
            ovr = inter / (areas[i] + areas[order[1:]] - inter)
            inds = numpy.where(ovr <= iou_thresh)[0]
            order = order[inds+1]
        return keep

    prev_time = time.time()
    frame_count = 0
    _last_debug = 0

    while True:
        try:
            app = App.get_running_app()
            if app and not app.yolo_enabled:
                with result_lock: DETECTION_RESULTS = []
                FPS = 0
                time.sleep(0.1)
                continue
        except: pass

        with yuv_lock:
            data = GLOBAL_YUV_DATA
        if data is None:
            time.sleep(0.005)
            continue

        w_cam, h_cam = GLOBAL_CAM_WIDTH, GLOBAL_CAM_HEIGHT
        try:
            rgb = nv21_to_rgb(data, w_cam, h_cam)
            pil_img = Image.fromarray(rgb)

            boxes = []
            t_infer = 0
            if interpreter:
                resized = pil_img.resize(input_shape)
                input_data = numpy.array(resized, dtype=numpy.float32) / 255.0
                if is_nchw:
                    input_data = numpy.transpose(input_data, (2,0,1))
                input_data = numpy.expand_dims(input_data, 0)

                interpreter.set_tensor(input_details[0]['index'], input_data)
                t0 = time.perf_counter()
                interpreter.invoke()
                t_infer = time.perf_counter() - t0
                outputs = interpreter.get_tensor(output_details[0]['index'])

                output = outputs[0]
                if output.shape[0] < output.shape[1]:
                    output = output.T

                boxes_raw = output[:, :4]   # cx,cy,w,h (0~1)
                scores = output[:, 4:]
                cls_ids = numpy.argmax(scores, axis=1)
                confs = numpy.max(scores, axis=1)

                mask = confs > 0.25
                f_boxes = boxes_raw[mask]
                f_confs = confs[mask]
                f_cls = cls_ids[mask]

                if len(f_boxes):
                    # 关键修复：直接反归一化到相机像素坐标
                    cx = f_boxes[:,0] * w_cam
                    cy = f_boxes[:,1] * h_cam
                    bw = f_boxes[:,2] * w_cam
                    bh = f_boxes[:,3] * h_cam

                    x1 = cx - bw/2.0
                    y1 = cy - bh/2.0
                    x2 = cx + bw/2.0
                    y2 = cy + bh/2.0

                    box_coords = numpy.stack([x1, y1, x2, y2], axis=1)
                    keep = pure_nms(box_coords, f_confs, 0.45)
                    for idx in keep:
                        boxes.append((
                            float(x1[idx]), float(y1[idx]),
                            float(x2[idx]), float(y2[idx]),
                            float(f_confs[idx]), int(f_cls[idx])
                        ))

            with result_lock:
                DETECTION_RESULTS = boxes

            now = time.time()
            if now - _last_debug >= 1.0:
                _last_debug = now
                print(f"[Detection] FPS:{frame_count} Boxes:{len(boxes)} Infer:{t_infer*1000:.0f}ms")
                if boxes: print(f"  Sample {boxes[0]}")

            frame_count += 1
            if now - prev_time >= 1.0:
                FPS = frame_count
                frame_count = 0
                prev_time = now

        except Exception as e:
            print(f"[Detection] Error: {e}")
            traceback.print_exc()
            time.sleep(0.1)

        time.sleep(0.005)
        
        
class HualingACApp(App):
    title_text = StringProperty('Camera Preview')
    status_text = StringProperty('')
    log_text = StringProperty('')
    flash_mode_text = StringProperty('Flash: Off')
    
    preview_angle = NumericProperty(270)
    brightness_value = NumericProperty(0)
    chroma_value = NumericProperty(3)
    yolo_enabled = BooleanProperty(True)

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
        
        # 启动 HTTP 流服务器
        threading.Thread(target=run_stream_server, daemon=True).start()
        # 启动检测线程
        threading.Thread(target=detection_worker, daemon=True).start()
        # 定时更新检测框和 FPS
        Clock.schedule_interval(self.update_detection_display, 1.0/15.0)
        
        return self.root_widget

    def toggle_yolo(self):
        self.yolo_enabled = not self.yolo_enabled
        print(f"[UI] YOLO enabled: {self.yolo_enabled}")

    def update_detection_display(self, dt):
        if hasattr(self.root_widget.ids, 'fps_label'):
            self.root_widget.ids.fps_label.text = f'FPS: {FPS}'
        
        overlay = self.root_widget.ids.detect_overlay
        # 首次打印 overlay 尺寸，方便调试
        if not hasattr(self, '_debug_overlay_printed'):
            print(f"[Overlay] Size: {overlay.width}x{overlay.height}, Angle: {self.preview_angle}")
            self._debug_overlay_printed = True

        overlay.canvas.clear()

        with result_lock:
            results = list(DETECTION_RESULTS)

        w_cam, h_cam = GLOBAL_CAM_WIDTH, GLOBAL_CAM_HEIGHT
        w_scr, h_scr = overlay.width, overlay.height
        
        if w_scr <= 0 or h_scr <= 0 or not results:
            return

        angle = self.preview_angle
        with overlay.canvas:
            Color(0, 1, 0, 0.8)
            for (x1, y1, x2, y2, conf, cls) in results:
                nx1, ny1 = x1 / w_cam, y1 / h_cam
                nx2, ny2 = x2 / w_cam, y2 / h_cam

                if angle == 270:
                    sx1, sy1 = ny1 * w_scr, (1 - nx2) * h_scr
                    sx2, sy2 = ny2 * w_scr, (1 - nx1) * h_scr
                elif angle == 90:
                    sx1, sy1 = (1 - ny2) * w_scr, nx1 * h_scr
                    sx2, sy2 = (1 - ny1) * w_scr, nx2 * h_scr
                elif angle == 180:
                    sx1, sy1 = (1 - nx2) * w_scr, ny1 * h_scr
                    sx2, sy2 = (1 - nx1) * w_scr, ny2 * h_scr
                else:  # 0度
                    sx1, sy1 = nx1 * w_scr, (1 - ny2) * h_scr
                    sx2, sy2 = nx2 * w_scr, (1 - ny1) * h_scr

                box_w = abs(sx2 - sx1)
                box_h = abs(sy2 - sy1)
                left = min(sx1, sx2)
                bottom = min(sy1, sy2)

                Line(rectangle=(left, bottom, box_w, box_h), width=2.0)

    def on_brightness_value(self, instance, value):
        self._apply_professional_settings()

    def on_chroma_value(self, instance, value):
        self._apply_professional_settings()

    def set_preview_angle(self, angle):
        self.preview_angle = angle
        overlay = self.root_widget.ids.detect_overlay
        if angle % 180 != 0:
            overlay.size = (self.root_widget.height, self.root_widget.width)
        else:
            overlay.size = (self.root_widget.width, self.root_widget.height)
        self._set_status(f'Preview orientation locked to {angle} deg')

    def get_supported_resolutions(self):
        try:
            cam = self.root_widget.ids.camera
            if cam._camera and hasattr(cam._camera, '_android_camera') and cam._camera._android_camera is not None:
                sizes = cam._camera._android_camera.getParameters().getSupportedPreviewSizes()
                res = [(s.width, s.height) for s in sizes]
                return str(res)
        except Exception as e:
            self._log(f'Failed to get resolutions: {e}')
        return '[(640, 480)]'

    def set_preview_resolution(self, w, h):
        global GLOBAL_CAM_WIDTH, GLOBAL_CAM_HEIGHT
        if w == GLOBAL_CAM_WIDTH and h == GLOBAL_CAM_HEIGHT:
            return
        GLOBAL_CAM_WIDTH = w
        GLOBAL_CAM_HEIGHT = h
        self._set_status(f'Resolution set to {w}x{h}, restarting preview...')
        camera = self.root_widget.ids.camera
        if camera.play:
            camera.play = False
            Clock.schedule_once(lambda dt: self._start_camera_preview(), 0.6)
        else:
            self._start_camera_preview()

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
            Clock.schedule_once(lambda dt: self._set_camera_orientation(), 0.6)
            Clock.schedule_once(lambda dt: self._setup_native_callback(), 1.0)
            self._set_status('Preview started')
        except Exception as e:
            self._set_status(f'Start failed: {e}')
            self._log(f'Start camera error: {e}')
        finally:
            self._pending_start = False

    def _set_camera_orientation(self):
        camera = self.root_widget.ids.camera
        if not camera.play:
            return
        try:
            internal_camera = camera._camera
            if internal_camera is None:
                Clock.schedule_once(lambda dt: self._set_camera_orientation(), 0.3)
                return
            try:
                orientation = 90 if camera.index == 0 else 270
                internal_camera.setDisplayOrientation(orientation)
                self._log(f'Camera orientation set to {orientation}°')
            except AttributeError:
                self._log('setDisplayOrientation not supported, skipped.')
        except Exception as e:
            self._log(f'Set orientation failed: {e}')

    def _setup_native_callback(self):
        global GLOBAL_CAM_WIDTH, GLOBAL_CAM_HEIGHT
        camera = self.root_widget.ids.camera
        if not camera.play:
            return
        try:
            internal_camera = camera._camera
            if internal_camera and hasattr(internal_camera, '_android_camera') and internal_camera._android_camera is not None:
                native_cam = internal_camera._android_camera
                params = native_cam.getParameters()
                w, h = GLOBAL_CAM_WIDTH, GLOBAL_CAM_HEIGHT
                try:
                    params.setPreviewSize(w, h)
                    native_cam.setParameters(params)
                except Exception as e:
                    self._log(f'Failed to set preview size {w}x{h}: {e}')
                native_cam.setPreviewCallback(NATIVE_CALLBACK)
                self._apply_professional_settings()
                self._set_status(f'Native callback linked at {w}x{h}')
            else:
                Clock.schedule_once(lambda dt: self._setup_native_callback(), 0.5)
        except Exception as e:
            self._log(f'Failed to hook native callback: {e}')

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
            Clock.schedule_once(lambda dt: self._start_camera_preview(), 0.6)

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
    app_instance = App.get_running_app()
    current_angle = app_instance.preview_angle if app_instance else 270
    h = html_content.replace("__INITIAL_ANGLE__", str(current_angle))
    response_obj.set_header("Content-Type", "text/html; charset=utf-8")
    response_obj.set_data(h.encode('utf-8'))

html_content = r"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Kivy Native Stream Live View</title>
    <style>
        body { margin: 0; background-color: #000; overflow: hidden; display: flex; align-items: center; justify-content: center; height: 100vh; font-family: sans-serif; }
        #native_stream { width: 100vw; height: 100vh; object-fit: contain; transform-origin: center; transition: transform 0.2s; }
        .controls { position: fixed; bottom: 20px; left: 0; right: 0; display: flex; flex-wrap: wrap; justify-content: center; gap: 10px; z-index: 100; padding: 0 10px; }
        button { background: rgba(255,255,255,0.2); color: white; border: none; padding: 10px 15px; border-radius: 8px; cursor: pointer; backdrop-filter: blur(5px); }
        .settings { background: rgba(0,0,0,0.6); padding: 5px; border-radius: 8px; display: flex; gap: 5px; align-items: center; }
        select { background: rgba(0,0,0,0.1); border: 1px solid #555; color: white; border-radius: 4px; padding: 5px; }
    </style>
</head>
<body>
    <div class="controls">
        <button onclick="rotate(-90)">↺</button>
        <button onclick="rotate(90)">↻</button>
        <button onclick="toggleFullscreen()">FS</button>
        <button onclick="window.location.reload()" style="background: rgba(200,0,0,0.5);">Refresh</button>
        <div class="settings">
            <select id="resolutionSelect"></select>
            <button onclick="setResolution()" style="background: rgba(0,100,200,0.5);">Apply</button>
        </div>
    </div>
    
    <script>
        let angle = __INITIAL_ANGLE__;
        const rpcPort = "1133";
        const streamUrl = window.location.protocol + '//' + window.location.hostname + ':1134/mjpeg_stream';
        
        const defaultResolutions = [
            { w: 320, h: 240 },
            { w: 640, h: 480 },
            { w: 800, h: 600 },
            { w: 1024, h: 768 },
            { w: 1280, h: 720 },
            { w: 1280, h: 960 },
            { w: 1920, h: 1080 },
            { w: 2592, h: 1944 },
            { w: 3840, h: 2160 }
        ];

        async function fetchSupportedResolutions() {
            try {
                const resp = await fetch(`http://${window.location.hostname}:${rpcPort}/r=app.get_supported_resolutions()`);
                if (resp.ok) {
                    const text = await resp.text();
                    const matches = text.match(/\((\d+)\s*,\s*(\d+)\)/g);
                    if (matches) {
                        return matches.map(m => {
                            const [w, h] = m.replace(/[()]/g, '').split(',').map(Number);
                            return { w, h };
                        });
                    }
                }
            } catch (e) {
                console.warn("Failed to fetch supported resolutions", e);
            }
            return defaultResolutions;
        }

        function populateResolutionSelect(resolutions, currentW, currentH) {
            const select = document.getElementById('resolutionSelect');
            select.innerHTML = '';
            resolutions.forEach(({w, h}) => {
                const option = document.createElement('option');
                option.value = `${w},${h}`;
                option.textContent = `${w} x ${h}`;
                if (w === currentW && h === currentH) {
                    option.selected = true;
                }
                select.appendChild(option);
            });
        }

        async function init() {
            let currentW = 640, currentH = 480;
            try {
                const resp = await fetch(`http://${window.location.hostname}:${rpcPort}/r=app.preview_angle-180,GLOBAL_CAM_WIDTH,GLOBAL_CAM_HEIGHT`);
                const text = await resp.text();
                const vals = text.replace(/[()]/g, '').split(',').map(s => parseInt(s.trim()));
                angle = vals[0] || 270;
                currentW = vals[1] || 640;
                currentH = vals[2] || 480;
            } catch(e) { 
                console.error("RPC Init Error", e); 
            }
            
            const resolutions = await fetchSupportedResolutions();
            populateResolutionSelect(resolutions, currentW, currentH);
            
            startStream();
        }

        function startStream() {
            const oldImg = document.getElementById('native_stream');
            if (oldImg) oldImg.remove();
            
            const newImg = document.createElement('img');
            newImg.id = 'native_stream';
            newImg.style.cssText = "width: 100vw; height: 100vh; object-fit: contain; transform-origin: center; transition: transform 0.2s;";
            newImg.style.transform = `rotate(${angle}deg) scaleY(-1)`;
            newImg.src = streamUrl + "?t=" + new Date().getTime();
            newImg.onerror = () => setTimeout(startStream, 2000);
            document.body.prepend(newImg);
        }

        async function setResolution() {
            const select = document.getElementById('resolutionSelect');
            const [w, h] = select.value.split(',').map(Number);
            if(!w || !h) return;
            await fetch(`http://${window.location.hostname}:${rpcPort}/r=app.set_preview_resolution(${w},${h})`);
            console.log(`Resolution set to ${w}x${h}`);
        }

        function rotate(deg) {
            angle = (angle + deg) % 360;
            const img = document.getElementById('native_stream');
            if (img) img.style.transform = `rotate(${angle}deg) scaleY(-1)`;
        }

        function toggleFullscreen() {
            if (!document.fullscreenElement) document.documentElement.requestFullscreen();
            else document.exitFullscreen();
        }

        init();
    </script>
</body>
</html>
"""

if __name__ == '__main__':
    app = HualingACApp()
    app.run()



"""
rpc('''
import urllib.request
import ssl
# 关闭证书校验
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx))
urllib.request.install_opener(opener)

r=urllib.request.urlretrieve(
    "https://ghfast.top/https://raw.githubusercontent.com/775cpu/midea-ble-go/main/yolov8n.tflite",
    "yolov8n_float32.tflite"
)
''')

BASE_URL = "http://192.168.1.183:1133/"

def rpc(expression,base=BASE_URL, timeout=10,p=1):
    if 'r=' not in expression and 'r = 'not in expression:expression='r='+expression
    import urllib
    url =base + urllib.parse.quote(expression, safe='')
    try:
        s = N.HTTP.get(url, timeout=timeout,print_req=1,headers={})
        if p:print(s)
        return s
    except Exception as e:
        print(f"[ERROR] RPC 失败: {e} \n请求表达式: {expression[:120]}")
    return None


s=rpc('''
from qgb import py
U,T,N,F=py.importUTNF()
r=F.read('./main.py')
''',p=0)
len(s)

38101



""" 