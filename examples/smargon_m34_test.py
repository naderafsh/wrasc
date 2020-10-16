from wrasc import reactive_agent as ra
from wrasc import ppmac_ra as ppra

# from wrasc import gpcom_wrap
from os import environ, path
from ppmac import GpasciiClient
from math import isclose
import examples.smargon_code_templates as tls

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


_VERBOSE_ = 2
wracs_period = 0.250

# specific test data
collision_clearance = 250
motors = [ppra.axis(3), ppra.axis(4)]

motors[0].JogSpeed = 5/5
motors[1].JogSpeed = 5/5

# IP addreses of the Smargon PBLV
# Linux:  export PPMAC_TEST_IP="10.109.25.22"
# Win sc: $env:PPMAC_TEST_IP="10.109.25.22"
ppmac_test_IP = environ["PPMAC_TEST_IP"]
test_gpascii = GpasciiClient(ppmac_test_IP)
# TODO ! bad practice ! shall be done in the class
# attaching the globals dict to the gpasci

# verify strings are native ppmac
# but commands use macros in {} (defined by ppra.macrostrs) which need to be evaluated realtime.

m3_init_checks_ag = ppra.WrascPmacGate(verbose=_VERBOSE_, ppmac=test_gpascii,)

m3_start_pos_ag = ppra.WrascPmacGate(verbose=_VERBOSE_, ppmac=test_gpascii,)

m3_on_lim_ag = ppra.WrascPmacGate(verbose=_VERBOSE_, ppmac=test_gpascii,)

m3_slide_off_ag = ppra.WrascPmacGate(verbose=_VERBOSE_, ppmac=test_gpascii,)

collision_stopper_ag = ppra.WrascPmacGate(verbose=_VERBOSE_, ppmac=test_gpascii,)

# -------------------------------------------------------------------
# this one monitors the two motors for collision.
# stops both motors when collision zone condition is met.
# celeb cpommands may kill or stop the engaged motors, or
# may disable a coordinate system altogether.
# this shall not go to Done. After pass, it shall continue checking.

# -------------------------------------------------------------------
# 0 - check configuration

pass_conds = ["Motor[3].pAuxFault==Acc65E[0].DataReg[0].a","Motor[3].AuxFaultBit==8","Motor[3].AuxFaultLevel==0"]
cry_cmds = tls.cry_for(pass_conds)
m3_init_checks_ag.setup(
    pass_conds=pass_conds,
    cry_cmds=cry_cmds,
    **motors[0].LVars(),
    JogSpeed=motors[0].JogSpeed,
)
# -------------------------------------------------------------------
# 1 - settle at staring point
SettlePos = 1000
m3_start_pos_ag.setup(
    pass_conds=tls.assert_pos_wf(motors[0].motor_n, SettlePos, 10)[0],
    cry_cmds=[f"#{motors[0].motor_n}jog=={SettlePos}"],
    celeb_cmds=[],
)

# -------------------------------------------------------------------
# 2 - Move onto the minus limit and wait to stabilise
m3_on_lim_ag.setup(
    cry_cmds=[],
    pass_conds=tls.check_on_aux,
    L1=motors[0].motor_n,
)

m3_on_lim_ag.dwell_aoa = 2
m3_on_lim_ag.act_on_armed = dwell_aoa

# -------------------------------------------------------------------
# 3 - Arm Capture and slide off for capturing the falling edge
m3_slide_off_ag.setup(
    cry_cmds=[],
    pass_conds=["Motor[3].AuxFault=0,Motor[3].InPos=1"],
    pass_logs=tls.log_capt_rbk_tl,
    # resetting the changes in this action
    celeb_cmds=tls.reset_rbk_capt_tl + ["#{L1}hmz"],
    # and the macro substitutes
    **motors[0].LVars(),
    JogSpeed=motors[0].JogSpeed,
    trigOffset=100,
    HomeVel=1.28,
    CaptureJogDir="+",
    csv_file_name=path.join("autest_out", "sm3_capture.csv"),
)

m3_slide_off_ag.dwell_aoa = 0.01
m3_slide_off_ag.act_on_armed = dwell_aoa
# -------------------------------------------------------------------

# now setup a sequencer
inner_loop_ag = ppra.WrascRepeatUntil(verbose=_VERBOSE_)
# one cycle is already done so total number of repeats - 1 shall be repeated by the sequencer
inner_loop_ag.repeats = 2 - 1
inner_loop_ag.all_done_ag = m3_slide_off_ag
inner_loop_ag.reset_these_ags = [m3_start_pos_ag, m3_on_lim_ag, m3_slide_off_ag]
# inner_loop_ag.reset_these_ags += [m4_start_pos_ag, m4_on_lim_ag, m4_slide_off_ag]

# ----------------------------------------------------------------------

# -------------------------------------------------------------------
# -------------------------------------------------------------------

collision_stopper_ag.setup(
    ongoing=True,
    pass_conds=[
        # clearance is low
        f"#{motors[0].motor_n}p > #{motors[1].motor_n}p + {collision_clearance}",
        # and it is decreasing
        f"Motor[{motors[0].motor_n}].ActVel - Motor[{motors[1].motor_n}].ActVel > 0",
    ],
    celeb_cmds=[f"#{motors[0].motor_n},{motors[1].motor_n}kill"],
)


def reset_after_kill(ag_self: ra.Agent):
    """
    This aoa checks for collission zone condition. 
    celeb commands are
    This is an ongoing check, therefore never gets Done.

    """

    print("KILLLED TO PREVENT COLLISION")

    return ra.StateLogics.Idle, "back to idle"


collision_stopper_ag.act_on_armed = reset_after_kill

# -------------------------------------------------------------------
# set the forced sequence rules

m3_init_checks_ag.poll_pr = True

m3_start_pos_ag.poll_pr = lambda ag_self: m3_init_checks_ag.is_done

m3_on_lim_ag.poll_pr = lambda ag_self: m3_start_pos_ag.is_done

m3_slide_off_ag.poll_pr = lambda ag_self: m3_on_lim_ag.is_done

# -------------------------------------------------------------------

# ----------------------------------------------------------------------


# =====================================================================================
# input('press a key or break...')
# dm module called to compile and install agents
# agents_sorted_by_layer =
# input('press any key to start the process loop...')
# dm module takes control of the process loop
ppra.ra.process_loop(
    ppra.ra.compile_n_install({}, globals().copy(), "WORKSHOP01"),
    100000,
    cycle_period=wracs_period,
    debug=True,
)

test_gpascii.close
