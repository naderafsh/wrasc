from wrasc import ppmac_ra as ppra
from wrasc import reactive_agent as ra

# from wrasc import gpcom_wrap
from os import environ, path
from examples.motion_tests_ra import SmarGonTestAgents

import utils
from time import sleep


tst = utils.undump_obj("sg_ref_m34_once", "autest_in")
sg_test = SmarGonTestAgents(_VERBOSE_=1, tst=tst, out_path="sg_out")
agents = ppra.ra.compile_n_install({}, globals().copy(), "WORKSHOP01")
max_loop = 100


# initial
# m3 = -12792.64
# m4 pos=-27021.32
# m6 = -1.701905.4

# ppra.do_any(sg_test.set_initial_setup_ag)

iters = 0
while iters < tst["loop_repeats"]:
    print(f"starting loop no. {iters}")
    # set aux fault protection for inner and outer axes.
    # This prevents them to find mlim
    ppra.do_all([sg_test.setaux_inner_ag, sg_test.setaux_outer_ag])
    # let inner and outer move together. Limits are being watched
    ppra.do_all([sg_test.slide_inner_on_aux_ag, sg_test.slide_outer_on_aux_ag])
    # check here explicitly for limits and completion

    ppra.do_all([sg_test.setaux_capture_outer_ag, sg_test.setaux_capture_inner_ag])
    ppra.do_any(sg_test.slide_outer_off_aux_ag)
    ppra.do_any(sg_test.slide_inner_off_aux_ag)

    iters += 1

ppra.do_all([sg_test.reset_capture_inner_ag, sg_test.reset_capture_outer_ag])

# reset capture settings to make it possible to reference on mlim


# now move theouter axis onto the limit

print("Sequence is finished.")
