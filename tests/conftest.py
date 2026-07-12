"""pytest 共享 fixture。"""

from __future__ import annotations

import re
import sys
from unittest.mock import MagicMock


def _simple_jieba_lcut(text: str) -> list[str]:
  """测试用轻量分词：提取中文词块与字母数字串。"""
  tokens = re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z0-9]{2,}", text or "")
  return tokens or [t for t in (text or "").split() if t]


def pytest_configure(config):
    """在测试收集前 mock jieba；rank_bm25 不可用时提供占位模块。"""
    if "jieba" not in sys.modules:
        jieba_mock = MagicMock()
        jieba_mock.lcut = _simple_jieba_lcut
        sys.modules["jieba"] = jieba_mock
    try:
        import rank_bm25  # noqa: F401
    except ImportError:
        sys.modules.setdefault("rank_bm25", MagicMock())
