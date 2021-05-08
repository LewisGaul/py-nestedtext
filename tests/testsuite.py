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
    "inline_dict_01": "Unsupported cases: empty values, trailing commas",
    "inline_list_01": "Unsupported cases: empty values, trailing commas",
}

skip_load_testcases = {}

skip_dump_testcases = {
    "dict_16": "Colon in object key",
    "dict_17": "Undiagnosed",
    "dict_20": "Very weird object keys",
    "dict_26": "Colon in object key",
    "string_multiline_12": "Very weird characters",
}


@pytest.mark.parametrize("case", nt_test_api.load_test_cases(), ids=lambda c: c.id)
def test_all(case: nt_test_api.TestCase):
    if case.id in skip_testcases:
        pytest.skip(skip_testcases[case.id])

    if "load" in case.case:
        load_in_path = case.case["load"]["in"]["path"]

        if case.id in skip_load_testcases:
            logger.warning(
                "Skipping load check for %s: %s", case.id, skip_load_testcases[case.id]
            )

        elif "out" in case.case["load"]:
            logger.info("Checking successful load")
            expected = case.case["load"]["out"]["data"]
            with open(load_in_path, "r", encoding="utf-8") as f:
                actual = nt.load(f)
            assert actual == expected

            # Debug info.
            logger.debug("Loaded %s", load_in_path)
            with open(load_in_path, "r", encoding="utf-8") as f:
                logger.debug("\n%s", f.read())
            logger.debug("%s", json.dumps(actual))

            # Check loads() function too.
            with open(load_in_path, "r", encoding="utf-8") as f:
                actual2 = nt.loads(f.read())
            assert actual2 == expected

        elif "err" in case.case["load"]:
            logger.info("Checking load error")
            with pytest.raises(nt.NestedtextError):
                with open(load_in_path, "r", encoding="utf-8") as f:
                    nt.load(f)
            # TODO: Proper error checking

    if "dump" in case.case:
        if case.id in skip_dump_testcases:
            logger.warning(
                "Skipping dump check for %s: %s", case.id, skip_dump_testcases[case.id]
            )

        elif "out" in case.case["dump"]:
            logger.info("Checking successful dump")
            actual = nt.dumps(case.case["dump"]["in"]["data"])
            with open(case.case["dump"]["out"]["path"], "r") as f:
                expected = f.read()
            assert actual.strip() == expected.strip()

        elif "err" in case.case["dump"]:
            logger.info("Checking dump error")
            with pytest.raises(nt.NestedtextError):
                nt.dumps(case.case["dump"]["in"]["data"])
            # TODO: Proper error checking
