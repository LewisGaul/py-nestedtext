import json
import logging
import sys
from pathlib import Path

import pytest

import nestedtext as nt


sys.path.append(str(Path(__file__).parent / "official_tests" / "api"))
import nestedtext_official_tests as nt_test_api


logger = logging.getLogger(__name__)


skip_testcases = {
    "dict_16": "Colon in object key (dumping)",
    "dict_17": "Dumping not working - undiagnosed",
    "dict_20": "Very weird object keys (dumping)",
    "dict_26": "Colon in object key (dumping)",
    "inline_dict_01": "Unsupported cases: empty values, trailing commas",
    "inline_list_01": "Unsupported cases: empty values, trailing commas",
    "string_multiline_12": "Very weird characters (dumping)",
}


@pytest.mark.parametrize("case", nt_test_api.load_test_cases(), ids=lambda c: c.id)
def test_all(case: nt_test_api.TestCase):
    # if "inline" in case.id:
    #     pytest.skip("Inline containers not yet implemented")
    if case.id in skip_testcases:
        pytest.skip(skip_testcases[case.id])
    if "load" in case.case:
        if "out" in case.case["load"]:
            logger.info("Checking successful load")
            expected = case.case["load"]["out"]["data"]
            with open(case.case["load"]["in"]["path"], "r", encoding="utf-8") as f:
                actual = nt.load(f)
            assert actual == expected

            # Debug info.
            logger.debug("Loaded %s", case.case["load"]["in"]["path"])
            with open(case.case["load"]["in"]["path"], "r", encoding="utf-8") as f:
                logger.debug("\n%s", f.read())
            logger.debug("%s", json.dumps(actual))

            # Check loads() function too.
            with open(case.case["load"]["in"]["path"], "r", encoding="utf-8") as f:
                actual2 = nt.loads(f.read())
            assert actual2 == expected

        elif "err" in case.case["load"]:
            # TODO
            logger.warning("Load error checking not implemented")

    if "dump" in case.case:
        if "out" in case.case["dump"]:
            logger.info("Checking successful dump")
            actual = nt.dumps(case.case["dump"]["in"]["data"])
            with open(case.case["dump"]["out"]["path"], "r") as f:
                expected = f.read()
            assert actual.strip() == expected.strip()

        elif "err" in case.case["dump"]:
            # TODO
            logger.warning("Dump error checking not implemented")
