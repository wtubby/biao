"""知识库 _registry.yaml 与磁盘目录一致性检查。"""

from services.knowledge_registry import (
    clear_registry_cache,
    disk_knowledge_folders,
    get_knowledge_folders,
    load_registry,
    registered_folder_names,
    registry_path,
)


def test_registry_file_exists():
    assert registry_path().is_file(), f"缺少注册表: {registry_path()}"


def test_registered_folders_exist_on_disk():
    clear_registry_cache()
    disk = disk_knowledge_folders()
    missing = sorted(registered_folder_names() - disk)
    assert not missing, f"_registry.yaml 登记了但不存在的文件夹: {missing}"


def test_disk_folders_are_registered():
    clear_registry_cache()
    registered = registered_folder_names()
    orphan = sorted(disk_knowledge_folders() - registered)
    assert not orphan, (
        f"磁盘上有文件夹未登记进任何 registry 分类（永远不会被绑定）: {orphan}"
    )


def test_default_list_non_empty():
    clear_registry_cache()
    folders = get_knowledge_folders(None)
    assert folders
    assert folders == load_registry()["default"]


def test_project_type_match():
    clear_registry_cache()
    line = get_knowledge_folders("220kV线路工程")
    assert "电缆敷设" in line
    assert "主变安装" not in line
    default = get_knowledge_folders("变电站新建")
    assert "主变安装" in default


def test_non_power_domain_does_not_get_power_default():
    """市政等非电力项目不得回退到电力 default 文件夹（张冠李戴）。"""
    clear_registry_cache()
    folders = get_knowledge_folders("其他", "市政工程")
    assert folders == []
    assert "主变安装" not in folders
    assert "GIS安装" not in folders


def test_power_domain_uses_default_when_type_unmatched():
    clear_registry_cache()
    folders = get_knowledge_folders("其他", "电力工程")
    assert "主变安装" in folders
