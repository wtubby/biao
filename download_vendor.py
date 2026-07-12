"""下载前端依赖到本地 vendor 目录，避免 CDN 不可用导致白屏。"""
import urllib.request
from pathlib import Path

VENDOR_DIR = Path(__file__).resolve().parent / "frontend" / "vendor"
ANTD_VERSION = "5.27.4"

FILES = {
    "react.production.min.js": "https://cdn.jsdelivr.net/npm/react@18.2.0/umd/react.production.min.js",
    "react-dom.production.min.js": "https://cdn.jsdelivr.net/npm/react-dom@18.2.0/umd/react-dom.production.min.js",
    "dayjs.min.js": "https://cdn.jsdelivr.net/npm/dayjs@1.11.10/dayjs.min.js",
    "antd-with-locales.min.js": f"https://cdn.jsdelivr.net/npm/antd@{ANTD_VERSION}/dist/antd-with-locales.min.js",
    "reset.css": f"https://cdn.jsdelivr.net/npm/antd@{ANTD_VERSION}/dist/reset.css",
}

OBSOLETE = ("antd.min.js", "antd.min.css", "moment.min.js", "zh-cn.js")


def main():
    VENDOR_DIR.mkdir(parents=True, exist_ok=True)
    for name in OBSOLETE:
        obsolete = VENDOR_DIR / name
        if obsolete.exists():
            obsolete.unlink()
            print(f"移除旧依赖 {name}")
    for name, url in FILES.items():
        dest = VENDOR_DIR / name
        if dest.exists() and dest.stat().st_size > 1000:
            continue
        print(f"下载 {name} ...")
        urllib.request.urlretrieve(url, dest)
    print("前端依赖就绪")


if __name__ == "__main__":
    main()
