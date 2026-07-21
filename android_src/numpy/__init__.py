from pythonforandroid.recipe import Recipe
from os.path import join

class NumpyRecipe(Recipe):
    version = 'v1.26.4'     # 直接带 v 的 git tag
    url = 'git+https://github.com/numpy/numpy'
    patches = []            # 不用补丁

    def get_recipe_env(self, arch=None):
        env = super().get_recipe_env(arch)
        # 只在交叉编译阶段加入修复标志
        env['CXXFLAGS'] = env.get('CXXFLAGS', '') + ' -std=c++17 -include unordered_map'
        env['CFLAGS'] = env.get('CFLAGS', '') + ' -include unordered_map'
        return env

recipe = NumpyRecipe()

#mkdir android_src/numpy
#touch android_src/numpy/__init__.py