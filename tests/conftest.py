import logging
from pathlib import Path
from pytest import fixture


logging.basicConfig(level=logging.DEBUG)


@fixture
def tmp_dir(tmpdir):
    return Path(str(tmpdir)).resolve()
