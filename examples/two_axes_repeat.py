from wrasc import reactive_agent as ra
from wrasc import ppmac_ra as ppra
from wrasc import gpcom_wrap
from os import environ, path
from ppmac import GpasciiClient
from math import isclose
import examples.ppmac_code_templates as tls

""" This script is using wrasc ppmac_ra. 
The module provides predefined warsc Agents which are customised to control a sequence 
in a ppmac by sending and checking ppmac native commands.

Fundamental concept is that the ppmac internal state is NOT duplicated nor mapped at python.
The agents interact with the ppmac controller all the time to check the actual ppmac values, 
as the only copy of the machine state.
The agents share some "parameters" in python variable space, and may publish logs and state 
information to epics but don't rely on these for conditions and transitions.

As a result, this model heavily relies on fast ppmac communication and 
also wrasc poll cycle shall be fast.

Each Agent has a Pass Condition which checks everycycle, using refreshed ppmac variables. 
The Agents then can e forced to an "anchored sequence"

The aoa method of the Agent can be used to implement additional functions which execute after pass condition is met.

Returns:
    [type]: [description]
"""


def dwell_aoa(ag_self: ra.Agent):

    if ag_self.dwell_aoa and (ra.timer() - ag_self.poll.ChangeTime < ag_self.dwell_aoa):
        return ra.StateLogics.Armed, f"dwelling by {ag_self.dwell_aoa}"

    return ra.StateLogics.Done, "user aoa done."


_VERBOSE_ = 0
wracs_period = 0.250


# test code
# Linux:  export PPMAC_TEST_IP="10.23.92.220"
# Win sc: $env:PPMAC_TEST_IP="10.23.92.220"
ppmac_test_IP = environ["PPMAC_TEST_IP"]
test_gpascii = GpasciiClient(ppmac_test_IP)

# verify strings are native ppmac
# but commands use macros in {} (defined by ppra.macrostrs) which need to be evaluated realtime.

m3_init_checks_ag = ppra.WrascPmacGate(verbose=_VERBOSE_, ppmac=test_gpascii,)
m4_init_checks_ag = ppra.WrascPmacGate(verbose=_VERBOSE_, ppmac=test_gpascii,)

mAll_start_pos_ag = ppra.WrascPmacGate(verbose=3, ppmac=test_gpascii,)

m3_on_lim_ag = ppra.WrascPmacGate(verbose=_VERBOSE_, ppmac=test_gpascii,)
m4_on_lim_ag = ppra.WrascPmacGate(verbose=_VERBOSE_, ppmac=test_gpascii,)

m3_slide_off_ag = ppra.WrascPmacGate(verbose=_VERBOSE_, ppmac=test_gpascii,)
m4_slide_off_ag = ppra.WrascPmacGate(verbose=_VERBOSE_, ppmac=test_gpascii,)

collision_stopper_ag = ppra.WrascPmacGate(verbose=3, ppmac=test_gpascii,)

# -------------------------------------------------------------------
# this one monitors the two motors for collision.
# stops both motors when collision zone condition is met.
# celeb cpommands may kill or stop the engaged motors, or
# may disable a coordinate system altogether.
# this shall not go to Done. After pass, it shall continue checking.

collision_stopper_ag.setup(
    ongoing=True,
    pass_conds=[
        "#3p - #4p > {collision_clearance}",
        "Motor[3].DesVelZero + Motor[4].DesVelZero == 0",
    ],
    collision_clearance=1000,
    celeb_cmds=["#3..4k"],
)


def kill_aoa(ag_self: ra.Agent):
    """
    This aoa checks for collission zone condition. 
    celeb commands are
    This is an ongoing check, therefore never gets Done.

    """
    return ra.StateLogics.Idle, "back to idle"


collision_stopper_ag.act_on_armed = kill_aoa

# -------------------------------------------------------------------
# 0 - check configuration
m3_init_checks_ag.setup(
    pass_conds=tls.verify_config_rdb_lmt,
    cry_cmds=tls.config_rdb_lmt,
    L1=3,
    L2=0,
    L3=2,
    L7=11,
    JogSpeed=3.2,
)
# -------------------------------------------------------------------
# 0 - check configuration
m4_init_checks_ag.setup(
    pass_conds=tls.verify_config_rdb_lmt,
    cry_cmds=tls.config_rdb_lmt,
    L1=4,
    L2=0,
    L3=3,
    L7=12,
    JogSpeed=3.2,
)
# -------------------------------------------------------------------
# 1 - settle at staring point
SettlePos = 77000
mAll_start_pos_ag.setup(
    pass_conds=tls.assert_pos_wf(3, SettlePos, 10)[0]
    + tls.assert_pos_wf(4, SettlePos, 10)[0],
    cry_cmds=[f"#3..4j={SettlePos}"],
    celeb_cmds=[],
)

# -------------------------------------------------------------------
# 2 - Move onto the minus limit and wait to stabilise
m3_on_lim_ag.setup(
    cry_cmds=["#{L1}j{MoveToLimitDir}"],
    pass_conds=["Motor[L1].MinusLimit>0", "Motor[L1].InPos>0"],
    L1=3,
    MoveToLimitDir="-",
)

m3_on_lim_ag.dwell_aoa = 0.1
m3_on_lim_ag.act_on_armed = dwell_aoa

# -------------------------------------------------------------------
# 2 - Move onto the minus limit and wait to stabilise
m4_on_lim_ag.setup(
    cry_cmds=["#{L1}j{MoveToLimitDir}"],
    pass_conds=["Motor[L1].MinusLimit>0", "Motor[L1].InPos>0"],
    L1=4,
    MoveToLimitDir="-",
)

m4_on_lim_ag.dwell_aoa = 0.1
m4_on_lim_ag.act_on_armed = dwell_aoa


# -------------------------------------------------------------------
# 3 - Arm Capture and slide off for capturing the falling edge
m3_slide_off_ag.setup(
    cry_cmds=tls.jog_capt_rbk_tl,
    pass_conds=tls.check_off_limit_inpos_tl,
    pass_logs=tls.log_capt_rbk_tl,
    # resetting the changes in this action
    celeb_cmds=tls.reset_rbk_capt_tl + ["#{L1}hmz"],
    # and the macro substitutes
    L1=3,
    L2=0,
    L3=2,
    L7=11,
    JogSpeed=3.2,
    trigOffset=100,
    HomeVel=1.28,
    CaptureJogDir="+",
    csv_file_name=path.join("autest_out", "m3_capture.csv"),
)

m3_slide_off_ag.dwell_aoa = 0.01
m3_slide_off_ag.act_on_armed = dwell_aoa
# -------------------------------------------------------------------
# 3 - Arm Capture and slide off for capturing the falling edge
m4_slide_off_ag.setup(
    cry_cmds=tls.jog_capt_rbk_tl,
    pass_conds=tls.check_off_limit_inpos_tl,
    pass_logs=tls.log_capt_rbk_tl,
    # resetting the changes in this action
    celeb_cmds=tls.reset_rbk_capt_tl + ["#{L1}hmz"],
    # and the macro substitutes
    L1=4,
    L2=0,
    L3=3,
    L7=12,
    JogSpeed=3.2,
    trigOffset=100,
    HomeVel=1.28,
    CaptureJogDir="+",
    csv_file_name=path.join("autest_out", "m4_capture.csv"),
)

m4_slide_off_ag.dwell_aoa = 0.01
m4_slide_off_ag.act_on_armed = dwell_aoa

# -------------------------------------------------------------------


# setup the sequence default dependency (can be done automaticatlly)

m3_init_checks_ag.poll_pr = lambda ag_self: True
m4_init_checks_ag.poll_pr = lambda ag_self: True

mAll_start_pos_ag.poll_pr = (
    lambda ag_self: m3_init_checks_ag.act.Var and m4_init_checks_ag.is_done
)

m3_on_lim_ag.poll_pr = lambda ag_self: mAll_start_pos_ag.is_done

m3_slide_off_ag.poll_pr = lambda ag_self: m3_on_lim_ag.is_done

m4_on_lim_ag.poll_pr = (
    lambda ag_self: mAll_start_pos_ag.is_done
)  # m3_slide_off_ag.is_done

m4_slide_off_ag.poll_pr = lambda ag_self: m4_on_lim_ag.is_done

# -------------------------------------------------------------------

# now setup a sequencer
quit_if_all_done_ag = ppra.WrascSequencer(verbose=_VERBOSE_)
# one cycle is already done so total number of repeats - 1 shall be repeated by the sequencer
quit_if_all_done_ag.repeats = 10 - 1
quit_if_all_done_ag.last_layer_dependency_ag = m4_slide_off_ag

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
