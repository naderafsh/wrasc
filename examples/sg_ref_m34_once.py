# this provides ppmac agent/tasking capability
from wrasc import ppmac_ra as ppra

# take the specific collection of agents/tasks in the specific test class
from examples.motion_tests_ra import SmarGonTestAgents

# this is used for yaml loading
import utils
from os import path


# load test settings from yaml file
tst = utils.undump_obj(
    "sg_ref_m34_once", path.join(path.dirname(path.abspath(__file__)), "autest_in")
)
# setup the collection of test agents (tasks) in the specific class
sg_test = SmarGonTestAgents(_VERBOSE_=tst["verbose_level"], tst=tst, out_path="sg_out")

# process and compile agents dependencies
agents = ppra.ra.compile_n_install({}, globals().copy(), "ARBITRARY")

iters = 0
while iters < tst["loop_repeats"]:
    print(f"\niteration: {iters} ")

    # set aux fault protection for inner and outer axes.
    # This prevents m3 and m4 from finding mlim
    ppra.do_ags([sg_test.setaux_inner_ag, sg_test.setaux_outer_ag])

    # let inner and outer move together towards aux switches.
    ppra.do_ags([sg_test.slide_inner_on_aux_ag, sg_test.slide_outer_on_aux_ag])

    # setup capture on falling aux switch for both motors
    ppra.do_ags([sg_test.setaux_capture_outer_ag, sg_test.setaux_capture_inner_ag])

    # slide off the outer motor first
    ppra.do_ags(sg_test.slide_outer_off_aux_ag)

    # then slide off the inner motor
    ppra.do_ags(sg_test.slide_inner_off_aux_ag)

    iters += 1

# finally reset capture settings to make it possible to home/reference on mlim
ppra.do_ags([sg_test.reset_capture_inner_ag, sg_test.reset_capture_outer_ag])

print("\nSequence is finished.")
