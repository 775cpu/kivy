import sys, io, urllib.parse, threading, traceback, struct
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

def get_bmp_bytes(rgb=None, size=(16, 16)):
    if not rgb: rgb = (255, 0, 0)
    if isinstance(size, int): size = [size, size]
    width, height = size
    r, g, b = (max(0, min(255, c)) for c in rgb)
    bgr_color = bytes([b, g, r])
    bytes_per_pixel = 3
    bytes_per_row = (width * bytes_per_pixel + 3) // 4 * 4
    pixel_data_size = bytes_per_row * height
    file_size = 14 + 40 + pixel_data_size
    bmp_header = struct.pack('<2sIII', b'BM', file_size, 0, 54)
    bmp_info = struct.pack('<IIIHHIIIIII', 40, width, height, 1, 24, 0, pixel_data_size, 3780, 3780, 0, 0)
    pixels = b''
    for _ in range(height):
        row = bgr_color * width
        padding = b'\x00' * (bytes_per_row - len(row))
        pixels += row + padding
    return bmp_header + bmp_info + pixels

def pretty_format(obj, width=120):
    if isinstance(obj,str):return obj
    try:
        from IPython.lib.pretty import pretty
        return pretty(obj, max_width=width)
    except ImportError:
        try:
            from pprint import pformat
            return pformat(obj, width=width)
        except:
            return repr(obj)

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True

class RPCRequestHandler(BaseHTTPRequestHandler):
    key = ''
    globals_dict = None
    locals_dict={}
    favicon_bytes = None
    def log_message(self, format, *args):
        print(f"[RPC] {self.address_string()} - {format % args}")
    def do_GET(self):
        if self.path == '/favicon.ico' and self.favicon_bytes:
            self.send_response(200)
            self.send_header('Content-Type', 'image/x-icon')
            self.send_header('Cache-Control', 'max-age=86400')
            self.send_header('Content-Length', str(len(self.favicon_bytes)))
            self.end_headers()
            self.wfile.write(self.favicon_bytes)
            return
        self.handle_rpc()
    def do_POST(self):
        self.handle_rpc()
    def handle_rpc(self):
        try:
            # 原始路径（包括查询字符串），不做任何解析
            raw_path = self.path
            # 去掉开头的斜杠
            # 验证并去除 key 前缀（如果设置了 key）
            if self.key:
                prefix = self.key + '/'
                if not raw_path.startswith(prefix):
                    self.send_error(403, "Forbidden")
                    return
                code_str = raw_path[len(prefix):]  # 去除 key/ 后剩余部分（可能包含 ?）
            else:            
                if raw_path.startswith('/'):
                    raw_path = raw_path[1:]
                code_str = raw_path
            if not code_str:
                self.send_error(400, "No code")
                return
            # URL 解码（将 %3B 等转回原字符）
            code = urllib.parse.unquote(code_str)
            print(f"[RPC]{self.client_address} {self.path}")# , code={code[:200]}")

            exec_globals = self.globals_dict.copy() if self.globals_dict else {}
            exec_globals['__name__'] = '__rpc_exec__'
            exec_globals['request'] = self
            exec_globals['q'] = self
            class ResponseWrapper:
                def __init__(self):
                    self.status = 200
                    self.headers = {}
                    self.data = None
                def set_data(self, data):
                    self.data = data
                def set_status(self, code):
                    self.status = code
                def set_header(self, key, value):
                    self.headers[key] = value
            resp = ResponseWrapper()
            exec_globals['response'] = resp
            exec_globals['p'] = resp
            old_stdout = sys.stdout
            sys.stdout = io.StringIO()
            try:
                exec(code, exec_globals,self.locals_dict)
                output = sys.stdout.getvalue()
                if 'r' in self.locals_dict:
                    result_obj = self.locals_dict['r']
                elif 'r' in exec_globals:
                    result_obj = exec_globals['r']
                elif resp.data is not None:
                    result_obj = resp.data
                elif output:
                    result_obj = output
                else:
                    result_obj = f"no 'r' variable, locals keys: {list(exec_globals.keys())}"
                result_str = pretty_format(result_obj)
                self.send_response(resp.status)
                for k, v in resp.headers.items():
                    self.send_header(k, v)
            except Exception as e:
                result_str = traceback.format_exc()
                self.send_response(500)
            finally:
                sys.stdout = old_stdout
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.end_headers()
            self.wfile.write(result_str.encode('utf-8'))
        except Exception as e:
            self.send_error(500, str(e))

def start_rpc_server(port=1133, key='', ip='0.0.0.0', globals=None,locals=None, daemon=True, favicon_rgb=None, favicon_size=16):
    if not key:key = ''
    RPCRequestHandler.key = key
    RPCRequestHandler.globals_dict = globals if globals else {}
    RPCRequestHandler.locals_dict = locals if locals is not None else {}
    if favicon_rgb is None:
        favicon_rgb = (port // 100, port % 100, 0)
    RPCRequestHandler.favicon_bytes = get_bmp_bytes(rgb=favicon_rgb, size=favicon_size)
    server = ThreadedHTTPServer((ip, port), RPCRequestHandler)
    thread = threading.Thread(target=server.serve_forever, name='RPC_Server', daemon=daemon)
    thread.start()
    print(f"[RPC server] at http://{ip}:{port}/{key}")
    return server, thread

def qpsu(url="http://192.168.1.100/D%3A/test/qpsu.zip",write_to=''):
    import urllib.request, zipfile, io, sys, importlib.abc, importlib.machinery
    data = urllib.request.urlopen(url).read()
    z = zipfile.ZipFile(io.BytesIO(data))
    class ZipImporter(importlib.abc.PathEntryFinder):
        def __init__(self, zf): self.zf = zf
        def find_spec(self, fullname, path=None, target=None):
            pkg_path = fullname.replace('.', '/') + '/__init__.py'  # 检查是否为包（有 __init__.py）
            if pkg_path in self.zf.namelist():
                return importlib.machinery.ModuleSpec(fullname, self, is_package=True)
            mod_path = fullname.replace('.', '/') + '.py'  # 检查是否为普通模块
            if mod_path in self.zf.namelist():
                return importlib.machinery.ModuleSpec(fullname, self)
            return None
        def create_module(self, spec): return None
        def exec_module(self, module):
            fullname = module.__name__
            pkg_path = fullname.replace('.', '/') + '/__init__.py'  # 先尝试作为包加载 __init__.py
            if pkg_path in self.zf.namelist():
                code = self.zf.read(pkg_path).decode('utf-8')
                module.__path__ = []  # 标记为包
                module.__file__ = f"<zip://{pkg_path}>"  # 修复 __file__ 未定义
                exec(code, module.__dict__)
                return
            mod_path = fullname.replace('.', '/') + '.py'
            code = self.zf.read(mod_path).decode('utf-8')
            module.__file__ = f"<zip://{mod_path}>"  # 修复 __file__ 未定义
            exec(code, module.__dict__)
    sys.meta_path.insert(0, ZipImporter(z))
    from qgb import py,U,T,N,F
    return py,U,T,N,F
    
if __name__ == '__main__':
    start_rpc_server(port=1144, key='', globals=globals(),locals=locals())
    # import sys;'qgb.U' in sys.modules or sys.path.append('C:/QGB/Anaconda3/Lib/site-packages/Pythonwin/');from qgb import *
    input("Press Ctrl+C or anykey to stop\n")