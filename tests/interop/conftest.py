import os

import pytest
from validatedpatterns_tests.interop.conftest_logger import *  # noqa: F401, F403
from validatedpatterns_tests.interop.conftest_openshift import *  # noqa: F401, F403


@pytest.fixture
def cluster_name():
    return os.getenv(
        "CLUSTER_NAME",
        f'{os.getenv("HUB_CLUSTER_PREFIX")}-{os.getenv("INFRA_PROVIDER")}-{os.getenv("MPTS_TEST_RUN_ID")}',
    )


@pytest.fixture
def cluster_apps_fqdn(cluster_name):
    return f'apps.{cluster_name}.{os.getenv("AWS_DOMAIN")}'
