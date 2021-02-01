# this provides ppmac agent/tasking capability
from wrasc import ppmac_ra as ppra

# take the specific collection of agents/tasks in the specific test class
from examples.motion_tests_ra import SgPhiM5Agents

# this is used for yaml loading
import utils
from os import path


# load test settings from yaml file
tst = utils.undump_obj(
    "sg_m5_repeat", path.join(path.dirname(path.abspath(__file__)), "autest_in")
)
# setup the collection of test agents (tasks) in the specific class
sg_test = SgPhiM5Agents(_VERBOSE_=tst["verbose_level"], tst=tst, out_path="sg_out")

# process and compile agents dependencies
agents = ppra.ra.compile_n_install({}, globals().copy(), "ARBITRARY")

iters = 0
while iters < tst["loop_repeats"]:
    print(f"\niteration: {iters} ")

    # set aux fault protection for inner and outer axes.
    # This prevents m3 and m4 from finding mlim

    ppra.do_ags([sg_test.jog_90_ag])

    iters += 1


print("\nSequence is finished.")
