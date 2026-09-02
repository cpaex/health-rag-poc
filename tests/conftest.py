"""Shared pytest config.

Integration tests marked `@pytest.mark.aws` are skipped unless RUN_AWS_TESTS=1 is
set in the environment (they need real credentials + a deployed dev environment).
"""

from __future__ import annotations

import os

import pytest


def pytest_collection_modifyitems(config, items):
    if os.environ.get("RUN_AWS_TESTS") == "1":
        return
    skip_aws = pytest.mark.skip(reason="set RUN_AWS_TESTS=1 to run @pytest.mark.aws tests")
    for item in items:
        if "aws" in item.keywords:
            item.add_marker(skip_aws)
