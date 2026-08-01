"""Register the dynamic Soup GI namespace with PyInstaller."""


def pre_safe_import_module(api):
    api.add_runtime_module(api.module_name)
