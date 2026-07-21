from pythonforandroid.recipe import PythonRecipe
import os
import re


class NumpyRecipe(PythonRecipe):
    version = '1.24.3'
    url = 'https://github.com/numpy/numpy/releases/download/v{version}/numpy-{version}.tar.gz'
    depends = ['python3', 'hostpython3', 'setuptools', 'cython']

    def prebuild_arm64_v8a(self):
        """在编译前，安全绕过交叉编译无法执行的数学检测"""
        build_dir = self.get_build_dir('arm64-v8a')
        setup_py = os.path.join(build_dir, 'numpy', 'core', 'setup.py')
        if not os.path.exists(setup_py):
            return

        with open(setup_py, 'r') as f:
            content = f.read()

        # 使用正则替换整个 check_math_capabilities 函数体
        pattern = r'(def check_math_capabilities\(.*?\):).*?(?=\n\S|\Z)'
        replacement = r'\1\n    pass\n'
        new_content = re.sub(pattern, replacement, content, flags=re.DOTALL)

        if new_content != content:
            with open(setup_py, 'w') as f:
                f.write(new_content)
            print('[INFO] Math check function stubbed successfully.')
        else:
            print('[WARNING] Could not find check_math_capabilities function.')

    def get_recipe_env(self, arch, **kwargs):
        env = super().get_recipe_env(arch, **kwargs)

        # 标准交叉编译配置
        env['_PYTHON_HOST_PLATFORM'] = f'linux-{arch.arch}'
        env['NPY_DISABLE_SVML'] = '1'
        env['BLAS'] = 'None'
        env['LAPACK'] = 'None'
        env['ATLAS'] = 'None'

        # C++17 及 NDK libc++ 兼容标志
        cxxflags = env.get('CXXFLAGS', '') or ''
        cflags = env.get('CFLAGS', '') or ''
        env['CXXFLAGS'] = f'{cxxflags} -std=c++17 -D_LIBCPP_DISABLE_AVAILABILITY'.strip()
        env['CFLAGS'] = f'{cflags} -D_LIBCPP_DISABLE_AVAILABILITY'.strip()

        return env


recipe = NumpyRecipe()