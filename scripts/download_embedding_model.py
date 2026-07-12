"""一次性下载 BGE 中文向量模型到本地，供离线 embedding 使用。"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    import sys

    sys.path.insert(0, str(ROOT))
    import config as cfg

    dest = Path(cfg.EMBEDDING_MODEL_PATH)
    dest.parent.mkdir(parents=True, exist_ok=True)

    marker = dest / "config.json"
    if marker.exists():
        print(f"模型已存在: {dest}")
        return

    print("下载 BAAI/bge-small-zh-v1.5 ...")
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer("BAAI/bge-small-zh-v1.5")
    model.save(str(dest))
    print(f"模型已缓存到: {dest}")


if __name__ == "__main__":
    main()
