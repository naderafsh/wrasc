from wrasc import reactive_agent as ra
from wrasc import ppmac_ra as ppra
from wrasc import gpcom_wrap
from os import environ, path
from ppmac import GpasciiClient
from math import isclose

""" This script is using wrasc ppmac_ra. 
The module provides predefined warsc Agents which are customised to control a sequence 
in a ppmac by sending and checking ppmac native commands.
Each Agent has a Pass Condition. The Agents then can e forced to an "anchored sequence"

The aoa method of the Agent can be used to implement additional functions which execute after pass condition is met.

Returns:
    [type]: [description]
"""


_VERBOSE_ = 2
wracs_period = 0.250
n_repeats = 30

# test code
# Linux:  export PPMAC_TEST_IP="10.23.92.220"
# Win sc: $env:PPMAC_TEST_IP="10.23.92.220"
ppmac_test_IP = environ["PPMAC_TEST_IP"]
test_gpascii = GpasciiClient(ppmac_test_IP)

# verify strings are native ppmac
# but commands use macros in {} (defined by ppra.macrostrs) which need to be evaluated realtime.

# pmac parameters

xx = 3
L2 = int(xx / 4)
L3 = xx % 4 - 1
# companion axis
cc = xx + 8
# restrictive axis
colliding_xx = 4
encoder_possf = 2000 / 12256 * 2000 / 2050 * 1000 / 992

# test parameters

JogSpeed = 3.2
JogSpeed_rate = 0
JogSpeed_max = 6.4

HomeVel = 1.28 / 10
InPosTime = 255  # ms
trigOffset = 100

# -------------------------------------------------------------------
# 0 - check configuration

cry_cmds = [
    # f"Motor[{cc}].PosSf = {encoder_possf}",
    # f"EncTable[{cc}].ScaleFactor = -1/256",
    # put EncType first, as it resets pCaptFlag and pCaptPos !!!!
    f"Motor[{cc}].EncType=Motor[{xx}].EncType",
    f"Motor[{cc}].CaptControl=Motor[{xx}].CaptControl",
    f"Motor[{cc}].pCaptFlag=Motor[{xx}].pCaptFlag",
    f"Motor[{cc}].pCaptPos=Motor[{xx}].pCaptPos",
    f"Motor[{cc}].LimitBits=Motor[{xx}].LimitBits",
    f"Motor[{cc}].CaptureMode=1",
    # set the following error of the companion axis out of the way
    f"Motor[{cc}].FatalFeLimit=9999999",
    # f"Motor[{cc}].ServoCaptTimeOffset = 3",
    f"Motor[{xx}].CaptureMode=0",
    f"PowerBrick[{L2}].Chan[{L3}].CaptCtrl=10",
    f"Motor[{xx}].JogSpeed={JogSpeed}",
]

pass_conds = [cond.replace("=", "==") for cond in cry_cmds]
m3_init_checks_ag = ppra.WrascPpmac(
    verbose=_VERBOSE_,
    ppmac=test_gpascii,
    pass_conds=pass_conds,
    cry_cmds=cry_cmds,
    celeb_cmds=None,
)
# -------------------------------------------------------------------
# 1 - settle at staring point
pass_conds, cry_cmds = ppra.assert_pos_wf(3, f"#{colliding_xx}p - 100", 1)

m3_start_pos_ag = ppra.WrascPpmac(
    verbose=_VERBOSE_,
    ppmac=test_gpascii,
    pass_conds=pass_conds,
    cry_cmds=cry_cmds,
    celeb_cmds=None,
)
# -------------------------------------------------------------------
# 2 - Move onto the minus limit and wait to stabilise
m3_on_lim_ag = ppra.WrascPpmac(
    verbose=_VERBOSE_,
    ppmac=test_gpascii,
    cry_cmds=[f"Motor[{xx}].InPosTime={InPosTime}", f"#{xx}j-"],
    pass_conds=[f"Motor[{xx}].MinusLimit > 0", f"Motor[{xx}].InPos > 0"],
    # also, log the previous capture values
    celeb_cmds=[],
)


def on_lim_aoa(ag_self: ra.Agent):
    if ra.timer() - ag_self.poll.ChangeTime < ag_self.dwell_on_limit:
        return ra.StateLogics.Armed, f"dwelling by {ag_self.dwell_on_limit}"

    ag_self.dwell_on_limit = ag_self.dwell_on_limit * (1 + ag_self.dwell_on_limit_rate)
    if ag_self.dwell_on_limit > ag_self.dwell_on_limit_max:
        ag_self.dwell_on_limit = ag_self.dwell_on_limit_max

    return ra.StateLogics.Done, "user aoa done."


m3_on_lim_ag.dwell_on_limit = 0.1
m3_on_lim_ag.dwell_on_limit_rate = 0.1
m3_on_lim_ag.dwell_on_limit_max = 3
m3_on_lim_ag.act_on_armed = on_lim_aoa

# -------------------------------------------------------------------
# 3 - Arm Capture and slide off for capturing the falling edge
m3_slide_off_ag = ppra.WrascPpmac(
    verbose=_VERBOSE_,
    ppmac=test_gpascii,
    cry_cmds=[
        f"Motor[{cc}].CapturePos=1",
        f"Motor[{xx}].JogSpeed={HomeVel}",
        f"#{xx}j:2000^{trigOffset}",
        # companion axis is fooled to think it is jogging
        f"Motor[{cc}].JogSpeed={0.00001}",
        f"#{cc}j:10^{0}",
    ],
    pass_conds=[
        f"Motor[{xx}].MinusLimit==0",
        f"Motor[{xx}].PlusLimit==0",
        f"Motor[{xx}].InPos > 0",
        # this will catch the missed captures, but does'nt provide a retry...
        # f"Motor[{cc}].CapturePos==0",
    ],
    pass_logs=[
        f"Motor[{xx}].CapturedPos",
        f"#{xx}p",
        f"Motor[{xx}].JogSpeed",
        f"Motor[{cc}].CapturedPos",
        f"#{cc}p",
        f"Motor[{cc}].CapturePos",
        f"Motor[{cc}].Position",
    ],
    # resetting the changes in this action
    celeb_cmds=[f"Motor[{xx}].JogSpeed={JogSpeed}", f"#{cc}j/",],
)

m3_slide_off_ag.csv_file_name = path.join("autest_out", "s03_slide_off_ag.csv")


def slide_off_aoa(ag_self: ra.Agent):
    if ra.timer() - ag_self.poll.ChangeTime < ag_self.dwell_off_limit:
        return ra.StateLogics.Armed, f"dwelling by {ag_self.dwell_off_limit}"

    # ag_self.JogSpeed = ag_self.JogSpeed * (1 + JogSpeed_rate)
    # if ag_self.JogSpeed > ag_self.JogSpeed_max:
    #     ag_self.JogSpeed = ag_self.JogSpeed_max

    return ra.StateLogics.Done, "user aoa done."


m3_slide_off_ag.dwell_off_limit = 0.01

# s03_slide_off_ag.JogSpeed = 1
# s03_slide_off_ag.JogSpeed_rate = 0
# s03_slide_off_ag.JogSpeed_max = 6.4
m3_slide_off_ag.act_on_armed = slide_off_aoa

# -------------------------------------------------------------------


# setup the sequence default dependency (can be done automaticatlly)

m3_init_checks_ag.poll_pr = lambda ag_self: True
m3_start_pos_ag.poll_pr = lambda ag_self: m3_init_checks_ag.act.Var
m3_on_lim_ag.poll_pr = lambda ag_self: m3_start_pos_ag.act.Var
m3_slide_off_ag.poll_pr = lambda ag_self: m3_on_lim_ag.act.Var

# -------------------------------------------------------------------

# now setup a sequencer
quit_if_all_done_ag = ppra.WrascSequencer(verbose=_VERBOSE_)
quit_if_all_done_ag.repeats = n_repeats
quit_if_all_done_ag.last_layer_dependency_ag = m3_slide_off_ag

# ----------------------------------------------------------------------

# =====================================================================================
# input('press a key or break...')
# dm module called to compile and install agents
agents_sorted_by_layer = ppra.ra.compile_n_install({}, globals().copy(), "WORKSHOP01")
# input('press any key to start the process loop...')
# dm module takes control of the process loop
ppra.ra.process_loop(
    agents_sorted_by_layer, 100000, cycle_period=wracs_period, debug=True
)

test_gpascii.close
