from wrasc import reactive_agent as ra
from wrasc import ppmac_ra as ppra
from wrasc import gpcom_wrap
from os import environ, path
from ppmac import GpasciiClient

_VERBOSE_ = 3

# test code
# Linux:  export PPMAC_TEST_IP="10.23.92.220"
# Win sc: $env:PPMAC_TEST_IP="10.23.92.220"

ppmac_test_IP = environ["PPMAC_TEST_IP"]

test_gpascii = GpasciiClient(ppmac_test_IP)


# verify strings are native ppmac
# but commands use macros in {} (defined by ppra.macrostrs) which need to be evaluated realtime.

# main motor
xx = 3
JogSpeed = 1.28
HomeVel = JogSpeed / 10
# companion axis
cc = xx + 8
# restrictive axis
colliding_xx = 4

# 0 - check configuration
s00_inip_ag = ppra.WrascPpmac(ppmac=test_gpascii, poll_pr=lambda ag_self: True,)

# 1 - settle at staring point
pass_conds, cry_cmds = ppra.assert_pos_wf(3, f"#{colliding_xx}p - 100", 1)

s01_inip_ag = ppra.WrascPpmac(
    ppmac=test_gpascii, verifiy_stats=pass_conds, cry_cmds=cry_cmds, celeb_cmds=None,
)

# 2 - put it on the minus limit and log previously captured values
s02_inip_ag = ppra.WrascPpmac(
    verbose=_VERBOSE_,
    ppmac=test_gpascii,
    verifiy_stats=[f"Motor[{xx}].MinusLimit > 0"],
    # also, log the previous capture values
    pass_logs=[f"Motor[{xx}].CapturedPos", f"Motor[{cc}].CapturedPos"],
    cry_cmds=f"#{xx}j-",
    celeb_cmds=None,
)
# add a log filename
s02_inip_ag.csv_file_name = path.join("autest_out", "capt_logs.csv")


# 3 - Arm and slide off for capturing the falling edge
s03_inip_ag = ppra.WrascPpmac(
    ppmac=test_gpascii,
    verifiy_stats=[f"Motor[{xx}].MinusLimit==0", f"Motor[{xx}].PlusLimit==0"],
    cry_cmds=[
        f"Motor[{xx}].JogSpeed=Motor[{xx}].HomeVel",
        f"#{xx}j:300",
        f"Motor[{xx}].CapturePos=1",
        f"Motor[{cc}].CapturePos=1",
        f"Motor[{xx}].JogSpeed={JogSpeed}",
    ],
    celeb_cmds=None,
)

# setup the sequence default dependency (can be done automaticatlly)

s00_inip_ag.poll_pr = lambda ag_self: True
s01_inip_ag.poll_pr = lambda ag_self: s00_inip_ag.poll.Var
s02_inip_ag.poll_pr = lambda ag_self: s01_inip_ag.poll.Var
s03_inip_ag.poll_pr = lambda ag_self: s02_inip_ag.poll.Var

# now setup a sequencer
quit_if_all_done_ag = ppra.WrascSequencer(verbose=_VERBOSE_)

quit_if_all_done_ag.repeats = 5

quit_if_all_done_ag.last_layer_dependency_ag = s03_inip_ag

# ----------------------------------------------------------------------

# =====================================================================================
# input('press a key or break...')
# dm module called to compile and install agents
agents_sorted_by_layer = ppra.ra.compile_n_install({}, globals().copy(), "WORKSHOP01")
# input('press any key to start the process loop...')
# dm module takes control of the process loop
ppra.ra.process_loop(agents_sorted_by_layer, 1000, cycle_period=0.2, debug=True)

test_gpascii.close
