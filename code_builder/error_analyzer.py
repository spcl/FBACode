#!/usr/bin/env python3
import re
import json
from fuzzywuzzy import fuzz
from fuzzywuzzy import process
from itertools import combinations

# path_regex = r"(?:\.\.|\.)?(?:[/]*/)+\S*\.\S+(?:\sline\s\d+:?)?(?=\s|$|\.)"

log = "ERROR - [1/0] I: pybuild base:217: python3.7 setup.py config \nI: pybuild base:217: /usr/bin/python3 setup.py build \nwarning: no directories found matching 'package'\nutils/oslogin_utils.cc:34:10: fatal error: 'boost/regex.hpp' file not found\n#include <boost/regex.hpp>\n         ^~~~~~~~~~~~~~~~~\n1 error generated.\nutils/oslogin_utils.cc:34:10: fatal error: 'boost/regex.hpp' file not found\n#include <boost/regex.hpp>\n         ^~~~~~~~~~~~~~~~~\n1 error generated.\nutils/oslogin_utils.cc:34:10: fatal error: 'boost/regex.hpp' file not found\n#include <boost/regex.hpp>\n         ^~~~~~~~~~~~~~~~~\n1 error generated.\nmake[2]: *** [Makefile:126: utils/oslogin_utils.o] Error 1\nmake[1]: *** [debian/rules:19: override_dh_auto_build] Error 2\nmake: *** [debian/rules:15: build] Error 2\n\n"
path_regex = r"(?:\.\.|\.)?(?:[/]*/)+\S*\.\S+(?:\sline\s\d+:?)?(?=\s|$|\.)"
with open("errortypes.json") as f:
    errs = json.load(f)
    # errs_path = [x for x in errs if re.search(path_regex, x) is not None]
    # for err in errs:
    #     errs[err]["amount"] = 0
    # for err1, err2 in combinations(errs, 2):
    #     ratio = fuzz.partial_ratio(err1, err2)
    #     if ratio == 100:
    #         print(ratio)
    #         print(err1)
    #         print(err2)
    lines = [re.sub(path_regex, "PATH/FILE.TXT", l) for l in log.splitlines()]
    for l in lines:
        print("\n")
        print(l)
        print()
        matches = process.extract(l, errs.keys(),
                                  limit=5, scorer=fuzz.partial_ratio)
        # what threshold??
        for m in matches:
            print(m[1])
            print(m[0])
    
# with open("errortypes.json", "w") as f:
#     f.write(json.dumps(errs, indent=2))