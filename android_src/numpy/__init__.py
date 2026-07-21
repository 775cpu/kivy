import os
import re
from pythonforandroid.recipe import PythonRecipe, Recipe

class NumpyRecipe(PythonRecipe):
    version = '1.24.3'
    url = 'https://github.com/numpy/numpy/releases/download/v{version}/numpy-{version}.tar.gz'
    depends = ['python3', 'hostpython3', 'setuptools', 'cython']

    def prebuild_arm64_v8a(self):
        build_dir = self.get_build_dir('arm64-v8a')
        setup_py = os.path.join(build_dir, 'numpy', 'core', 'setup.py')
        if not os.path.exists(setup_py):
            return
        with open(setup_py, 'r') as f:
            content = f.read()
        pattern = r'(def check_math_capabilities\(.*?\):).*?(?=\n\S|\Z)'
        replacement = r'\1\n    pass\n'
        new_content = re.sub(pattern, replacement, content, flags=re.DOTALL)
        if new_content != content:
            with open(setup_py, 'w') as f:
                f.write(new_content)
            print('[INFO] Math check function stubbed.')

    def get_recipe_env(self, arch, **kwargs):
        env = super().get_recipe_env(arch, **kwargs)

        # 交叉编译标识
        env['_PYTHON_HOST_PLATFORM'] = arch.command_prefix

        # 禁用高级指令集和外部 BLAS
        env['NPY_DISABLE_SVML'] = '1'
        env['BLAS'] = 'None'
        env['LAPACK'] = 'None'
        env['ATLAS'] = 'None'

        # C++17 和 NDK 浮点异常标志修正
        fix_flags = '-D_LIBCPP_DISABLE_AVAILABILITY -fno-trapping-math -Wno-unsupported-floating-point-opt'
        env['CFLAGS'] = f"{env.get('CFLAGS', '')} {fix_flags}".strip()
        env['CXXFLAGS'] = f"{env.get('CXXFLAGS', '')} -std=c++17 {fix_flags}".strip()

        # 动态查找 libpython3.11 目录
        py_recipe = Recipe.get_recipe('python3', self.ctx)
        py_build_dir = py_recipe.get_build_dir(arch.arch)
        py_lib_dir1 = os.path.join(py_build_dir, 'android-build')
        py_lib_dir2 = os.path.join(py_build_dir, 'android-build', 'android-root', 'lib')
        libs_coll_dir = self.ctx.get_libs_dir(arch.arch)

        py_ver = '.'.join(self.ctx.python_recipe.version.split('.')[:2])

        # 同时链接数学库和 Python 库（解决 exp2f 和 PyLong_Type）
        env['LDFLAGS'] = (env.get('LDFLAGS', '') +
                          f' -L{py_lib_dir1} -L{py_lib_dir2} -L{libs_coll_dir}'
                          f' -lpython{py_ver} -lm').strip()

        return env

recipe = NumpyRecipe()