from wrasc import reactive_agent as ra
from wrasc import ppmac_ra as ppra

# from wrasc import gpcom_wrap
from os import environ, path

import examples.ppmac_code_templates as tls
import utils

""" 
This script configures and runs an axis in open loop, while capturing its readback
from its encoder via designated companion axis, at limit fall flags.


This script is using wrasc ppmac_ra. 
The module provides predefined warsc Agents which are customised to control a sequence 
in a ppmac by sending and checking ppmac native commands.

Fundamental concept is that the ppmac internal state is NOT duplicated nor mapped in python.
The agents understand ppmac native language and interact with the ppmac controller continuously to check the actual ppmac values, 
as the only copy of the machine state.
The agents share some "parameters" in python variable space, and may publish logs and state 
information to epics but don't rely on these for conditions and transitions.

As a result, this model heavily relies on fast and reliable ppmac communication and also wrasc poll cycle of under 1 second.

Each Agent has a Pass Condition which checks everycycle, using refreshed ppmac variables. 
The Agents then can e forced to an "anchored sequence"

The aoa method of the Agent can be used to implement additional functions which execute after pass condition is met.

Returns:
    stats_inscription]
"""


def dwell_aoa(ag_self: ra.Agent):

    if ag_self.dwell_aoa and (ra.timer() - ag_self.poll.ChangeTime < ag_self.dwell_aoa):
        return ra.StateLogics.Armed, f"dwelling {ag_self.dwell_aoa}sec"

    return ra.StateLogics.Done, "user aoa done."


_VERBOSE_ = 2


tst = dict()

Wrasc_Cycle_Period = tst["Wrasc_Cycle_Period"] = 0.25
Loop_Repeats = tst["Loop_Repeats"] = 30
Collision_Clearance = tst["Collision_Clearance"] = 200000

tst["Backward_Ppmac"] = True
Ppmac_IP = tst["Ppmac_IP"] = "10.23.92.220"

PpGlobal_Filename = tst[
    "PpGlobal_Filename"
] = r"C:\Users\afsharn\gitdir\psych\outdir\NA_brake_test\Database\pp_global.sym"
BaseConfig_FileName = tst[
    "BaseConfig_FileName"
] = r"C:\Users\afsharn\gitdir\wrasc\examples\data\ppmac_base_config.cfg"

# pp_glob_dictst data
axis_n = 3
tst["Mot_A"] = ppra.axis(axis_n).LVars()
tst["Mot_A"]["Reverse_Enc"] = axis_n == 4
Micro_Steps = tst["Mot_A"]["Micro_Steps"] = 32
Full_Steps_per_Rev = tst["Mot_A"]["Full_Steps_per_Rev"] = 200
Overall_Pitch = tst["Mot_A"]["Overall_Pitch"] = 0.5
Enc_Res = tst["Mot_A"]["Enc_Res"] = 50e-6  # mm
Step_Res = tst["Mot_A"]["Step_Res"] = (
    1 / Full_Steps_per_Rev / Micro_Steps * Overall_Pitch
)

tst["Mot_A"]["Home_Offset"] = 0

tst["Mot_A"]["JogSpeed"] = 5

tst["Mot_A"]["Home_Vel"] = 1.28
tst["Mot_A"]["Slide_Off_Steps"] = 400
# tst["Mot_A"]["csv_file_name"] = path.join("autest_out", "ma_capture.csv")
tst["Mot_A"]["Attack_Pos_Enc"] = 2 / Enc_Res
tst["Mot_A"]["Small_Jog_Steps"] = 10000 / 10


# tst = utils.undump_obj("sample_test", "autest_in")
# print(tst)

utils.dump_obj(tst, path.join("autest_in", "sample_test" + ".yaml"))

# test code
# Linux:  export PPMAC_TEST_IP="10.23.92.220"
# Win sc: $env:PPMAC_TEST_IP="10.23.92.220"
# environ["PPMAC_TEST_IP"]
test_gpascii = ppra.PPMAC(Ppmac_IP, backward=tst["Backward_Ppmac"])
# it is possible to use multiple gpascii channels,
# but we don't have a reason to do so, yet!
test_gpascii_A = test_gpascii

pp_glob_dict = ppra.load_pp_globals(PpGlobal_Filename)
with open(BaseConfig_FileName) as f:
    base_config = f.read().splitlines()
    f.close

# using a default set of parameters to log for each motor
pass_logs = ppra.expand_globals(tls.log_capt_rbk_tl, pp_glob_dict, **tst["Mot_A"])

# verify strings are native ppmac
# but commands use macros in {} (defined by ppra.macrostrs) which need to be evaluated realtime.


# -------------------------------------------------------------------
# this one monitors the two motors for collision.
# stops both motors when collision zone condition is met.
# celeb cpommands may kill or stop the engaged motors, or
# may disable a coordinate system altogether.
# this shall not go to Done. After pass, it shall continue checking.

# -1 - check configuration

# -------- motor A
config_stats = ppra.expand_globals(base_config, pp_glob_dict, **tst["Mot_A"])

ma_base_config_ag = ppra.WrascPmacGate(verbose=_VERBOSE_, ppmac=test_gpascii_A,)
ma_base_config_ag.setup(
    **tst["Mot_A"], cry_cmds=config_stats, celeb_cmds="#{L1}$",
)

# to ensure plc type config files take effect,
# the config needs to be applied more than one time.
# this is because some statements refer to other settings
# which may change during download.
#
# TODO : maybe consider downloading only the non-matching criteria...
# and trry as many times? or skip exact statements if they are lready verified?
ma_base_config_ag.cry_retries = 2
# -------------------------------------------------------------------

# -------------------------------------------------------------------
# 0 - check configuration
# also add axis confix if there are deviations from baseConfig

# -------- motor A

rev_enc_cmd = (
    ["PowerBrick[L2].Chan[L3].EncCtrl=7"]
    if tst["Mot_A"]["Reverse_Enc"]
    else ["PowerBrick[L2].Chan[L3].EncCtrl=3"]
)

current_stat = ppra.expand_globals(["full_current(L1)=1"], pp_glob_dict, **tst["Mot_A"])

ma_init_checks_ag = ppra.WrascPmacGate(
    verbose=_VERBOSE_,
    ppmac=test_gpascii_A,
    **tst["Mot_A"],
    cry_cmds=tls.config_rdb_lmt
    + rev_enc_cmd
    + current_stat
    + ["Motor[L1].HomeOffset = {Home_Offset}"],
    celeb_cmds=[
        "%100",
        "#{L1}hm j/",  # puposedly fail homing to clear homed flag
        "#{L7}kill",
    ],
)
# -------------------------------------------------------------------
# 0.1 - Move to MLIM

# -------- motor A
ma_init_on_lim_ag = ppra.WrascPmacGate(
    verbose=_VERBOSE_,
    ppmac=test_gpascii_A,
    **tst["Mot_A"],
    pass_conds=tls.cond_on_neg_lim,
    cry_cmds="#{L1}j-",
    celeb_cmds=["#{L7}kill"],  # stop incomplete to leave HomeComplete at 0
)

ma_init_on_lim_ag.dwell_aoa = 2
ma_init_on_lim_ag.act_on_armed = dwell_aoa

# 0.2 - Home sliding off the limit

ma_init_on_home_ag = ppra.WrascPmacGate(
    verbose=_VERBOSE_,
    ppmac=test_gpascii_A,
    **tst["Mot_A"],
    pass_conds=["Motor[L1].HomeComplete==1"] + tls.check_off_limit_inpos_tl,
    cry_cmds="#{L1}hm",
    celeb_cmds=["#{L7}kill"],
)

ma_init_on_home_ag.dwell_aoa = 2
ma_init_on_home_ag.act_on_armed = dwell_aoa


# Only once (first time) the main axis is homed
# and companion axis is killed, reset companion axis readback to zero
# This is not very accurate anyways.
ma_hmz_companion_ag = ppra.WrascPmacGate(
    verbose=_VERBOSE_,
    ppmac=test_gpascii_A,
    **tst["Mot_A"],
    pass_conds=[
        "Motor[L7].AmpEna==0",
        "Motor[L1].HomeComplete==1",
        "#{L1}p > -5",
        "#{L1}p < 5",
    ],
    cry_cmds=[],
    celeb_cmds="#{L7}hmz",
    # this is a one off. therefore, if it fails, then th loop gets stock
    ongoing=False,
)

# -------------------------------------------------------------------
# 1 - settle at staring point

# -------- motor A
ma_start_pos_ag = ppra.WrascPmacGate(
    verbose=_VERBOSE_,
    ppmac=test_gpascii_A,
    **tst["Mot_A"],
    pass_conds=[
        "Motor[L1].InPos==1",
        "#{L7}p > {Attack_Pos_Enc} + Motor[L7].CapturedPos",
    ],
    cry_cmds=[],
    celeb_cmds=[],
)
ma_start_pos_ag.cry_retries = 1
# -------------------------------------------------------------------
# 1.1 - Step towards the staring point

# -------- motor A
ma_step_until_ag = ppra.WrascPmacGate(
    verbose=_VERBOSE_,
    ppmac=test_gpascii_A,
    **tst["Mot_A"],
    pass_conds=[
        "Motor[L1].InPos==1",
        "#{L7}p < {Attack_Pos_Enc} + Motor[L7].CapturedPos",
    ],
    cry_cmds=[],
    celeb_cmds=["#{L1}jog:{Small_Jog_Steps}"],
    pass_logs=pass_logs,
    csv_file_name=path.join("autest_out", "ma_small_steps.csv"),
)
# this agent will not be put on old when passed:
ma_step_until_ag.ongoing = True
# step until will be active everytime the ma_start_pos_ag is not on hold
ma_step_until_ag.poll_pr = (
    lambda ag_self: not ma_start_pos_ag.inhibited and not ma_start_pos_ag.is_done
)

# -------------------------------------------------------------------
# 2 - Move onto the minus limit and wait to stabilise,

# -------- motor A
ma_on_lim_ag = ppra.WrascPmacGate(
    verbose=_VERBOSE_,
    ppmac=test_gpascii_A,
    **tst["Mot_A"],
    cry_cmds=["#{L1}jog-"],
    pass_conds=tls.cond_on_neg_lim,
    celeb_cmds=["#{L7}kill"],
    pass_logs=pass_logs,
    csv_file_name=path.join("autest_out", "ma_slide_on.csv"),
)

ma_on_lim_ag.dwell_aoa = 2
ma_on_lim_ag.act_on_armed = dwell_aoa
# -------------------------------------------------------------------
# 3 - Arm Capture and slide off for capturing the falling edge

# -------- motor A
ma_slide_off_ag = ppra.WrascPmacGate(verbose=_VERBOSE_, ppmac=test_gpascii_A,)
ma_slide_off_ag.setup(
    **tst["Mot_A"],
    SlideOff_Dir="+",
    cry_cmds=[
        "Motor[L1].JogSpeed={Home_Vel}",
        "#{L7}j:{SlideOff_Dir}{Slide_Off_Steps}",
        "Motor[L7].CapturePos=1",
        "#{L1}j:{SlideOff_Dir}{Slide_Off_Steps}",
    ],
    pass_conds=tls.check_off_limit_inpos_tl,
    # resetting the changes in this action
    celeb_cmds=[
        "Motor[L1].JogSpeed={JogSpeed}",
        "PowerBrick[L2].Chan[L3].CountError=0",
    ],
    pass_logs=pass_logs,
    csv_file_name=path.join("autest_out", "ma_slide_off.csv"),
)
ma_slide_off_ag.dwell_aoa = 0.01
ma_slide_off_ag.act_on_armed = dwell_aoa
# -------------------------------------------------------------------

# now setup a sequencer
inner_loop_ag = ppra.WrascRepeatUntil(verbose=_VERBOSE_)
# one cycle is already done so total number of repeats - 1 shall be repeated by the sequencer
inner_loop_ag.repeats = tst["Loop_Repeats"] - 1
inner_loop_ag.all_done_ag = ma_slide_off_ag
inner_loop_ag.reset_these_ags = [ma_start_pos_ag, ma_on_lim_ag, ma_slide_off_ag]
# ----------------------------------------------------------------------

# -------------------------------------------------------------------
# -------------------------------------------------------------------
collision_stopper_ag = ppra.WrascPmacGate(verbose=_VERBOSE_, ppmac=test_gpascii,)
collision_stopper_ag.setup(
    ongoing=True,
    pass_conds=[
        # clearance is low
        f"#11p > #12p + {Collision_Clearance}",
        # and it is decreasing
        f"Motor[3].ActVel - Motor[4].ActVel > 0",
    ],
    celeb_cmds=[f"#3,4 kill"],
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
ma_init_on_lim_ag.poll_pr = lambda ag_self: ma_init_checks_ag.is_done
ma_init_on_home_ag.poll_pr = lambda ag_self: ma_init_on_lim_ag.is_done

# setup the sequence default dependency (can be done automaticatlly)
ma_start_pos_ag.poll_pr = (
    lambda ag_self: ma_init_on_home_ag.is_done and ma_hmz_companion_ag.is_done
)

ma_on_lim_ag.poll_pr = lambda ag_self: ma_start_pos_ag.is_done
ma_slide_off_ag.poll_pr = lambda ag_self: ma_on_lim_ag.is_done
# ----------------------------------------------------------------------

# =====================================================================================
agents = ppra.ra.compile_n_install({}, globals().copy(), "WORKSHOP01")

# TODO confirm with user before starting the test


ppra.ra.process_loop(
    agents, 100000, cycle_period=tst["Wrasc_Cycle_Period"], debug=True,
)

test_gpascii.close
