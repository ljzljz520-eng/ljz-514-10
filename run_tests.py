#!/usr/bin/env python3
"""一键运行全部后端算法/API 测试。

    python3 run_tests.py            # 使用内置 unittest
    pytest backend/tests            # 如已安装 pytest 亦可
"""
import sys
import unittest

if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite = loader.discover(start_dir="backend/tests", pattern="test_*.py")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
