import json
import logging
import sys
from pathlib import Path

import pytest

import nestedtext as nt


sys.path.append(str(Path(__file__).parent / "official_tests" / "api"))
import nestedtext_official_tests as nt_test_api


logger = logging.getLogger(__name__)


skip_testcases = {}


@pytest.mark.parametrize("case", nt_test_api.load_test_cases(), ids=lambda c: c.id)
def test_all(case: nt_test_api.TestCase):
    if "inline" in case.id:
        pytest.skip("Inline containers not yet implemented")
    if case.id in skip_testcases:
        pytest.skip(skip_testcases[case.id])
    if "load" in case.case:
        if "out" in case.case["load"]:
            expected = case.case["load"]["out"]["data"]
            actual = nt.load(case.case["load"]["in"]["path"])
            assert actual == expected

            # Debug info.
            logger.debug("Loaded %s", case.case["load"]["in"]["path"])
            with open(case.case["load"]["in"]["path"], "r") as f:
                logger.debug("\n%s", f.read())
            logger.debug("%s", json.dumps(actual))

            # Check loads() function too.
            with open(case.case["load"]["in"]["path"], "r") as f:
                actual2 = nt.loads(f.read())
            assert actual2 == expected

        elif "err" in case.case["load"]:
            # TODO
            logger.warning("Load error checking not implemented")

    if "dump" in case.case:
        if "out" in case.case["dump"]:
            # TODO
            # expected = nt.dumps(case.case["dump"]["in"]["data"])
            with open(case.case["dump"]["out"]["path"], "r") as f:
                actual = f.read()
            logger.warning("Dump success checking not implemented")
            # assert actual == expected

        elif "err" in case.case["dump"]:
            # TODO
            logger.warning("Dump error checking not implemented")
