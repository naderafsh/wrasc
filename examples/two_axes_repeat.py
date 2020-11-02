from wrasc import reactive_agent as ra
from wrasc import ppmac_ra as ppra

# from wrasc import gpcom_wrap
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
    stats_inscription]
"""


def dwell_aoa(ag_self: ra.Agent):

    if ag_self.dwell_aoa and (ra.timer() - ag_self.poll.ChangeTime < ag_self.dwell_aoa):
        return ra.StateLogics.Armed, f"dwelling by {ag_self.dwell_aoa}"

    return ra.StateLogics.Done, "user aoa done."


_VERBOSE_ = 2
wracs_period = 0.250
Loop_Repeats = 20
# pp_glob_dictst data
collision_clearance = 2000
motors = {"a": ppra.axis(3).LVars(), "b": ppra.axis(4).LVars()}


motors["a"]["JogSpeed"] = 3.2
motors["b"]["JogSpeed"] = 3.2

motors["a"]["Reverse_Enc"] = False
motors["b"]["Reverse_Enc"] = True

motors["a"]["MoveToLimitDir"] = "-"
motors["b"]["MoveToLimitDir"] = "-"

motors["a"]["Trig_Offset"] = 100
motors["b"]["Trig_Offset"] = 100

motors["a"]["Home_Vel"] = 1.28
motors["b"]["Home_Vel"] = 1.28

motors["a"]["CaptureJogDir"] = "+"
motors["b"]["CaptureJogDir"] = "+"

motors["a"]["csv_file_name"] = path.join("autest_out", "ma_capture.csv")
motors["b"]["csv_file_name"] = path.join("autest_out", "mb_capture.csv")


# test code
# Linux:  export PPMAC_TEST_IP="10.23.92.220"
# Win sc: $env:PPMAC_TEST_IP="10.23.92.220"
ppmac_test_IP = environ["PPMAC_TEST_IP"]
test_gpascii = GpasciiClient(ppmac_test_IP)
# it is possible to use multiple gpascii channels,
# but we don't have a reason to do so, yet!
test_gpascii_A = test_gpascii
test_gpascii_B = test_gpascii


pp_global_filename = (
    r"C:\Users\afsharn\gitdir\psych\outdir\NA_brake_test\Database\pp_global.sym"
)
pp_glob_dict = ppra.load_pp_globals(pp_global_filename)
baseConfigFileName = (
    r"C:\Users\afsharn\gitdir\wrasc\examples\data\ppmac_base_config.cfg"
)

with open(baseConfigFileName) as f:
    base_config = f.read().splitlines()
    f.close

# verify strings are native ppmac
# but commands use macros in {} (defined by ppra.macrostrs) which need to be evaluated realtime.

ma_base_config_ag = ppra.WrascPmacGate(verbose=_VERBOSE_, ppmac=test_gpascii_A,)
mb_base_config_ag = ppra.WrascPmacGate(verbose=_VERBOSE_, ppmac=test_gpascii_B,)

ma_init_checks_ag = ppra.WrascPmacGate(verbose=_VERBOSE_, ppmac=test_gpascii_A,)
mb_init_checks_ag = ppra.WrascPmacGate(verbose=_VERBOSE_, ppmac=test_gpascii_B,)

ma_start_pos_ag = ppra.WrascPmacGate(verbose=_VERBOSE_, ppmac=test_gpascii_A,)
mb_start_pos_ag = ppra.WrascPmacGate(verbose=_VERBOSE_, ppmac=test_gpascii_B,)

ma_on_lim_ag = ppra.WrascPmacGate(verbose=_VERBOSE_, ppmac=test_gpascii_A,)
mb_on_lim_ag = ppra.WrascPmacGate(verbose=_VERBOSE_, ppmac=test_gpascii_B,)

ma_slide_off_ag = ppra.WrascPmacGate(verbose=_VERBOSE_, ppmac=test_gpascii_A,)
mb_slide_off_ag = ppra.WrascPmacGate(verbose=_VERBOSE_, ppmac=test_gpascii_B,)

collision_stopper_ag = ppra.WrascPmacGate(verbose=_VERBOSE_, ppmac=test_gpascii,)

# -------------------------------------------------------------------
# this one monitors the two motors for collision.
# stops both motors when collision zone condition is met.
# celeb cpommands may kill or stop the engaged motors, or
# may disable a coordinate system altogether.
# this shall not go to Done. After pass, it shall continue checking.

# -1 - check configuration

# -------- motor A
config_stats = ppra.expand_globals(base_config, pp_glob_dict, **motors["a"])

ma_base_config_ag.setup(
    # pass_conds=verify_stats,
    cry_cmds=config_stats,
    celeb_cmds="#{L1}$",
    **motors["a"],
)

# to ensure plc type config files take effect,
# the config needs to be applied more than one time.
# this is because some statements refer to other settings
# which may change during download.
#
# TODO : maybe consider downloading only the non-matching criteria...
# and trry as many times? or skip exact statements if they are lready verified?
ma_base_config_ag.cry_retries = 2

# -------- motor B
config_stats = ppra.expand_globals(base_config, pp_glob_dict, **motors["b"])
mb_base_config_ag.setup(
    # pass_conds=verify_stats,
    cry_cmds=config_stats,
    celeb_cmds="#{L1}$",
    **motors["b"],
)
mb_base_config_ag.cry_retries = 2
# -------------------------------------------------------------------

# -------------------------------------------------------------------
# 0 - check configuration
# also add axis confix if there are deviations from baseConfig

# -------- motor A
ma_init_checks_ag.setup(
    cry_cmds=tls.config_rdb_lmt, celeb_cmds="%100", **motors["a"],
)

# -------- motor B

# axis config
# reverse encoder direction for motor B companion

rev_enc_cmd = (
    ["PowerBrick[L2].Chan[L3].EncCtrl=7"]
    if motors["b"]["Reverse_Enc"]
    else ["PowerBrick[L2].Chan[L3].EncCtrl=3"]
)

mb_init_checks_ag.setup(
    cry_cmds=tls.config_rdb_lmt + rev_enc_cmd, celeb_cmds="%100", **motors["b"],
)
# -------------------------------------------------------------------
# 1 - settle at staring point

# -------- motor A
SettlePos = 10000
ma_start_pos_ag.setup(
    pass_conds=tls.assert_pos_wf(motors["a"]["L1"], SettlePos, 10)[0],
    cry_cmds=["#{L1}jog=={SettlePos}"],
    celeb_cmds=[],
    **motors["a"],
    SettlePos=SettlePos,
)

# -------- motor B
SettlePos = 10000
mb_start_pos_ag.setup(
    pass_conds=tls.assert_pos_wf(motors["b"]["L1"], SettlePos, 10)[0],
    cry_cmds=["#{L1}jog=={SettlePos}"],
    celeb_cmds=[],
    **motors["b"],
    SettlePos=SettlePos,
)

# -------------------------------------------------------------------
# 2 - Move onto the minus limit and wait to stabilise,

# -------- motor A
ma_on_lim_ag.setup(
    cry_cmds=["#{L1}jog{MoveToLimitDir}"],
    pass_conds=["Motor[L1].MinusLimit>0", "Motor[L1].InPos>0"],
    celeb_cmds=[
        "Motor[L1].JogSpeed={Home_Vel}",
        "Motor[L7].JogSpeed=0.00001",
        "Motor[L7].CapturePos=1",
    ],
    **motors["a"],
)

ma_on_lim_ag.dwell_aoa = 0.1
ma_on_lim_ag.act_on_armed = dwell_aoa

# -------- motor B
mb_on_lim_ag.setup(
    cry_cmds=["#{L1}jog{MoveToLimitDir}"],
    pass_conds=["Motor[L1].MinusLimit>0", "Motor[L1].InPos>0"],
    celeb_cmds=[
        "Motor[L1].JogSpeed={Home_Vel}",
        "Motor[L7].JogSpeed=0.00001",
        "Motor[L7].CapturePos=1",
    ],
    **motors["b"],
)

mb_on_lim_ag.dwell_aoa = 0.1
mb_on_lim_ag.act_on_armed = dwell_aoa

# -------------------------------------------------------------------
# 3 - Arm Capture and slide off for capturing the falling edge

# -------- motor A
pass_logs = ppra.expand_globals(tls.log_capt_rbk_tl, pp_glob_dict, **motors["a"])

ma_slide_off_ag.setup(
    cry_cmds=tls.jog_capt_rbk_tl,
    pass_conds=tls.check_off_limit_inpos_tl,
    pass_logs=pass_logs,
    # resetting the changes in this action
    celeb_cmds=tls.reset_rbk_capt_tl,
    **motors["a"],
)
ma_slide_off_ag.dwell_aoa = 0.01
ma_slide_off_ag.act_on_armed = dwell_aoa

# -------- motor B

pass_logs = ppra.expand_globals(tls.log_capt_rbk_tl, pp_glob_dict, **motors["b"])

mb_slide_off_ag.setup(
    cry_cmds=tls.jog_capt_rbk_tl,
    pass_conds=tls.check_off_limit_inpos_tl,
    pass_logs=pass_logs,
    # resetting the changes in this action,
    celeb_cmds=tls.reset_rbk_capt_tl,
    **motors["b"],
)
mb_slide_off_ag.dwell_aoa = 0.01
mb_slide_off_ag.act_on_armed = dwell_aoa

# -------------------------------------------------------------------

# now setup a sequencer
inner_loop_ag = ppra.WrascRepeatUntil(verbose=_VERBOSE_)
# one cycle is already done so total number of repeats - 1 shall be repeated by the sequencer
inner_loop_ag.repeats = Loop_Repeats - 1
inner_loop_ag.all_done_ag = mb_slide_off_ag
inner_loop_ag.reset_these_ags = [ma_start_pos_ag, ma_on_lim_ag, ma_slide_off_ag]
inner_loop_ag.reset_these_ags += [mb_start_pos_ag, mb_on_lim_ag, mb_slide_off_ag]

# ----------------------------------------------------------------------

# -------------------------------------------------------------------
# -------------------------------------------------------------------

collision_stopper_ag.setup(
    ongoing=True,
    pass_conds=[
        # clearance is low
        f"#{motors['a']['L7']}p > #{motors['b']['L7']}p + {collision_clearance}",
        # and it is decreasing
        f"Motor[{motors['a']['L1']}].ActVel - Motor[{motors['b']['L1']}].ActVel > 0",
    ],
    celeb_cmds=[f"#{motors['a']['L1']},{motors['b']['L1']}kill"],
)


def reset_after_kill(ag_self: ra.Agent):
    """    
    This aoa checks for collission zone condition. 
    celeb commands are
    This is an ongoing check, therefore never gets Done.

    Args:
        ag_self (ra.Agent): [description]

    Returns:
        [type]: [description]
    """
    print("KILLLED TO PREVENT COLLISION")

    return ra.StateLogics.Idle, "back to idle"


collision_stopper_ag.act_on_armed = reset_after_kill

# -------------------------------------------------------------------
# set the forced sequence rules

ma_init_checks_ag.poll_pr = lambda ag_self: ma_base_config_ag.is_done
mb_init_checks_ag.poll_pr = lambda ag_self: mb_base_config_ag.is_done

# setup the sequence default dependency (can be done automaticatlly)
mb_start_pos_ag.poll_pr = (
    lambda ag_self: ma_init_checks_ag.act.Var and mb_init_checks_ag.is_done
)

ma_start_pos_ag.poll_pr = lambda ag_self: mb_start_pos_ag.poll_pr(
    ag_self
)  # or .is_done if you want ma to wait for mb

ma_on_lim_ag.poll_pr = lambda ag_self: ma_start_pos_ag.is_done

mb_on_lim_ag.poll_pr = lambda ag_self: mb_start_pos_ag.is_done  # ma_on_lim_ag.is_done

ma_slide_off_ag.poll_pr = lambda ag_self: ma_on_lim_ag.is_done
mb_slide_off_ag.poll_pr = lambda ag_self: mb_on_lim_ag.is_done

# -------------------------------------------------------------------

# ----------------------------------------------------------------------


# =====================================================================================
# input('press a key or break...')
# dm module called to compile and install agents
# agents_sorted_by_layer =
# input('press any key to start the process loop...')
# dm module takes control of the process loop

agents = ppra.ra.compile_n_install({}, globals().copy(), "WORKSHOP01")

ppra.ra.process_loop(
    agents, 100000, cycle_period=wracs_period, debug=True,
)

test_gpascii.close
