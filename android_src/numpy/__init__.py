from pythonforandroid.recipe import PythonRecipe
import os
import re

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

        env['_PYTHON_HOST_PLATFORM'] = f'linux-{arch.arch}'
        env['NPY_DISABLE_SVML'] = '1'
        env['BLAS'] = 'None'
        env['LAPACK'] = 'None'
        env['ATLAS'] = 'None'

        # 关键修复：仅添加 -lm 解决 exp2f 等数学符号缺失
        env['LDFLAGS'] = (env.get('LDFLAGS', '') + ' -lm').strip()

        cxxflags = env.get('CXXFLAGS', '') or ''
        cflags = env.get('CFLAGS', '') or ''
        env['CXXFLAGS'] = f'{cxxflags} -std=c++17 -D_LIBCPP_DISABLE_AVAILABILITY'.strip()
        env['CFLAGS'] = f'{cflags} -D_LIBCPP_DISABLE_AVAILABILITY'.strip()
        return env

recipe = NumpyRecipe()