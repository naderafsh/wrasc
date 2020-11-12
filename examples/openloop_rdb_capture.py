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

pass condition statements and commands use native ppmac statements and macros in {} format
macros evaluate and expand at setup time to ppmac native statements which will be evaluated real time 


Returns:
    stats_inscription]
"""


_VERBOSE_ = 2


tst = dict()

wrasc_cycle_period = tst["wrasc_cycle_period"] = 0.25
loop_repeats = tst["loop_repeats"] = 3
tst["clearance_egu"] = 10

tst["ppmac_is_backward"] = False
ppmac_hostname = tst["ppmac_hostname"] = "10.23.92.220"

tst[
    "ppglobal_fname"
] = r"C:\Users\afsharn\gitdir\psych\outdir\NA_brake_test\Database\pp_global.sym"
tst[
    "baseconfig_fname"
] = r"C:\Users\afsharn\gitdir\wrasc\examples\data\ppmac_base_config.cfg"

# pp_glob_dictst data
axis_n = 4
tst["Mot_A"] = ppra.axis(axis_n).LVars()
tst["Mot_A"]["encoder_reversed"] = axis_n == 4
micro_steps = tst["Mot_A"]["micro_steps"] = 32
fullsteps_per_rev = tst["Mot_A"]["fullsteps_per_rev"] = 200
overall_egu_per_rev = tst["Mot_A"]["overall_egu_per_rev"] = 2
enc_res = tst["Mot_A"]["enc_res"] = 50e-6  # mm

tst["Mot_A"]["HomeOffset_EGU"] = tst["Mot_A"]["overall_egu_per_rev"] / 20
tst["Mot_A"]["JogSpeed_EGU"] = tst["Mot_A"]["overall_egu_per_rev"]

tst["Mot_A"]["HomeVel_EGU"] = tst["Mot_A"]["JogSpeed_EGU"] / 5
tst["Mot_A"]["slideoff_steps"] = 400
# tst["Mot_A"]["csv_file_name"] = path.join("autest_out", "ma_capture.csv")
tst["Mot_A"]["attackpos_egu"] = 2
tst["Mot_A"]["smalljog_egu"] = 0.5

tst["Mot_A"]["jog_settle_time"] = 1  # sec
tst["Mot_A"]["limit_settle_time"] = 2  # sec

# tst = utils.undump_obj("sample_test", "autest_in")
# print(tst)

utils.dump_obj(tst, path.join("autest_in", "sample_test" + ".yaml"))

step_res = tst["Mot_A"]["step_res"] = (
    1 / fullsteps_per_rev / micro_steps * overall_egu_per_rev
)
tst["Mot_A"]["smalljog_steps"] = tst["Mot_A"]["smalljog_egu"] / step_res
tst["Mot_A"]["HomeOffset"] = tst["Mot_A"]["HomeOffset_EGU"] / step_res
tst["Mot_A"]["attackpos_enc"] = (
    tst["Mot_A"]["attackpos_egu"] + tst["Mot_A"]["HomeOffset_EGU"]
) / enc_res
tst["Mot_A"]["JogSpeed"] = tst["Mot_A"]["JogSpeed_EGU"] / step_res / 1000
tst["Mot_A"]["HomeVel"] = tst["Mot_A"]["HomeVel_EGU"] / step_res / 1000
clearance_enc = tst["clearance_egu"] / enc_res

test_gpascii = ppra.PPMAC(ppmac_hostname, backward=tst["ppmac_is_backward"])
# it is possible to use multiple gpascii channels,
# but we don't have a reason to do so, yet!
test_gpascii_A = test_gpascii

pp_glob_dict = ppra.load_pp_globals(tst["ppglobal_fname"])
with open(tst["baseconfig_fname"]) as f:
    base_config = f.read().splitlines()
    f.close

# using a default set of parameters to log for each motor
pass_logs = ppra.expand_globals(tls.log_capt_rbk_tl, pp_glob_dict, **tst["Mot_A"])

################################################################################################################
# folowing section is defining wrasc agents for specific jobs. nothing happens untill the agents get processed #
################################################################################################################

# -1 - check configuration

# -------- motor A
config_stats = ppra.expand_globals(base_config, pp_glob_dict, **tst["Mot_A"])

ma_base_config_ag = ppra.WrascPmacGate(
    verbose=_VERBOSE_,
    ppmac=test_gpascii_A,
    **tst["Mot_A"],
    # validate / download calibration
    cry_cmds=config_stats,
    cry_retries=2,
    # phase the motor
    celeb_cmds="#{L1}$",
)

# to ensure plc type config files take effect,
# the config may need to be applied more than one time.
# this is because some statements refer to other settings
# which may change during download.
# Also, some native ppmac settings will AUTOMATICALLY change others
# e.g. EncType resets many related variables to their "type" default
#
# TODO : maybe consider downloading only the non-matching criteria...
# and try as many times? or skip exact statements if they are lready verified?

# -------------------------------------------------------------------

# -------------------------------------------------------------------
# 0 - check configuration
# also add axis confix if there are deviations from baseConfig

# -------- motor A

rev_enc_cmd = (
    ["PowerBrick[L2].Chan[L3].EncCtrl=7"]
    if tst["Mot_A"]["encoder_reversed"]
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
    + ["Motor[L1].HomeOffset = {HomeOffset}"],
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
    wait_after_celeb=tst["Mot_A"]["limit_settle_time"],
    celeb_cmds=["#{L1}j-", "#{L7}kill"],
)
# -------------------------------------------------------------------
# 0.2 - Home sliding off the limit

ma_init_on_home_ag = ppra.WrascPmacGate(
    verbose=_VERBOSE_,
    ppmac=test_gpascii_A,
    **tst["Mot_A"],
    pass_conds=["Motor[L1].HomeComplete==1"] + tls.check_off_limit_inpos_tl,
    cry_cmds="#{L1}hm",
    celeb_cmds=["#{L7}kill"],
    wait_after_celeb=tst["Mot_A"]["limit_settle_time"],
)

# -------------------------------------------------------------
# Only once (first time) the main axis is homed
# and companion axis is killed, reset companion axis readback to zero
# This is not very accurate anyways.
# ma_hmz_companion_ag = ppra.WrascPmacGate(
#     verbose=_VERBOSE_,
#     ppmac=test_gpascii_A,
#     **tst["Mot_A"],
#     pass_conds=[
#         "Motor[L7].AmpEna==0",
#         "Motor[L1].HomeComplete==1",
#         "#{L1}p > -5",
#         "#{L1}p < 5",
#     ],
#     cry_cmds=[],
#     celeb_cmds="#{L7}hmz",
#     # this is a one off. therefore, if it fails, then th loop gets stock
#     ongoing=False,
# )

# -------------------------------------------------------------------
# 1 - settle at staring point

# -------- motor A
ma_start_pos_ag = ppra.WrascPmacGate(
    verbose=_VERBOSE_,
    ppmac=test_gpascii_A,
    **tst["Mot_A"],
    pass_conds=[
        "Motor[L1].InPos==1",
        "#{L7}p > {attackpos_enc} + Motor[L7].CapturedPos",
    ],
)

# -------------------------------------------------------------------
# 1.1 - Step towards the staring point

# -------- motor A
ma_step_until_ag = ppra.WrascPmacGate(
    verbose=_VERBOSE_,
    ppmac=test_gpascii_A,
    **tst["Mot_A"],
    pass_conds="Motor[L1].InPos==1",
    cry_cmds=[],
    pass_logs=pass_logs,
    csv_file_name=path.join("autest_out", "ma_small_steps.csv"),
    celeb_cmds=["#{L1}jog:{smalljog_steps}"],
    wait_after_celeb=tst["Mot_A"]["jog_settle_time"],
)
# this agent will not be put on old when passed:
ma_step_until_ag.ongoing = True
# step until will be active everytime the ma_start_pos_ag is not on hold
ma_step_until_ag.poll_pr = (
    lambda ag_self: not ma_start_pos_ag.inhibited and ma_start_pos_ag.poll.Var is False
)


# -------------------------------------------------------------------
# 2 - Move onto the minus limit and wait to stabilise,

# -------- motor A
ma_on_lim_ag = ppra.WrascPmacGate(
    verbose=_VERBOSE_,
    ppmac=test_gpascii_A,
    **tst["Mot_A"],
    #
    pass_conds=tls.cond_on_neg_lim,
    cry_cmds=["#{L1}jog-"],
    #
    pass_logs=pass_logs,
    csv_file_name=path.join("autest_out", "ma_slide_on.csv"),
    #
    celeb_cmds=["#{L7}kill"],
    wait_after_celeb=tst["Mot_A"]["limit_settle_time"],
)

# -------------------------------------------------------------------
# 3 - Arm Capture and slide off for capturing the falling edge

# -------- motor A
ma_slide_off_ag = ppra.WrascPmacGate(
    verbose=_VERBOSE_,
    ppmac=test_gpascii_A,
    **tst["Mot_A"],
    #
    pass_conds=tls.check_off_limit_inpos_tl,
    cry_cmds=[
        "Motor[L1].JogSpeed={HomeVel}",
        "#{L7}j:{SlideOff_Dir}{slideoff_steps}",
        "Motor[L7].CapturePos=1",
        # "#{L1}j:{SlideOff_Dir}{slideoff_steps}",
        "#{L1}j=0",
    ],
    SlideOff_Dir="+",
    #
    pass_logs=pass_logs,
    csv_file_name=path.join("autest_out", "ma_slide_off.csv"),
    # resetting the changes in this action
    celeb_cmds=[
        "Motor[L1].JogSpeed={JogSpeed}",
        "PowerBrick[L2].Chan[L3].CountError=0",
    ],
    wait_after_celeb=tst["Mot_A"]["jog_settle_time"],
)

# -------------------------------------------------------------------

# now setup a sequencer
inner_loop_ag = ppra.WrascRepeatUntil(verbose=_VERBOSE_)
# one cycle is already done so total number of repeats - 1 shall be repeated by the sequencer
inner_loop_ag.repeats = tst["loop_repeats"] - 1
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
        f"#11p > #12p + {clearance_enc}",
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


################################################################################################################
# folowing section is defining wrasc agents for specific jobs. nothing happens untill the agents get processed #
################################################################################################################

# -------------------------------------------------------------------
# set the forced sequence rules

ma_init_checks_ag.poll_pr = lambda ag_self: ma_base_config_ag.is_done
ma_init_on_lim_ag.poll_pr = lambda ag_self: ma_init_checks_ag.is_done
ma_init_on_home_ag.poll_pr = lambda ag_self: ma_init_on_lim_ag.is_done

# setup the sequence default dependency (can be done automaticatlly)
ma_start_pos_ag.poll_pr = (
    lambda ag_self: ma_init_on_home_ag.is_done
)  # and ma_hmz_companion_ag.is_done

ma_on_lim_ag.poll_pr = lambda ag_self: ma_start_pos_ag.is_done
ma_slide_off_ag.poll_pr = lambda ag_self: ma_on_lim_ag.is_done
# ----------------------------------------------------------------------

################################################################################################################
# folowing section is defining wrasc agents for specific jobs. nothing happens untill the agents get processed #
################################################################################################################
agents = ppra.ra.compile_n_install({}, globals().copy(), "WORKSHOP01")

# TODO confirm with user before starting the test

################################################################################################################
# folowing section is defining wrasc agents for specific jobs. nothing happens untill the agents get processed #
################################################################################################################

ppra.ra.process_loop(
    agents, 100000, cycle_period=tst["wrasc_cycle_period"], debug=True,
)

test_gpascii.close

# now load the csv file and plot

filename = ma_step_until_ag.csv_file_stamped
print(f"here is the log file: {filename}")

import matplotlib.pyplot as plt

from numpy import genfromtxt
from os import path
import pandas as pd

# Enc_Res = 50e-6  # mm/count
# Step_Res = 0.0003125  # mm/ustep

# filename = path.join("autest_out", "ma_small_steps_201111_2030.csv")

df = pd.read_csv(filename)

# test_data = genfromtxt(filename, delimiter=",")

headers = list(df.columns)

assert "CapturedPos" in headers[1]
# TODO fix this hardcoded headers!
rdb_capt_mm = df["M12_CapturedPos"] * enc_res
rdb_hash_mm = df["A12_HashPos"] * enc_res
rdb_calib_mm = rdb_hash_mm - rdb_capt_mm - df["M4_HomeOffset"] * step_res
step_hash_mm = df["A4_HashPos"] * step_res
time_sec = df["Time"]

plt.plot(time_sec, pd.concat([rdb_calib_mm, step_hash_mm], axis=1))
plt.ylabel("rdb and steps [mm]")
plt.xlabel("Time[sec]")
plt.show()

plt.plot(time_sec, rdb_calib_mm - step_hash_mm)
plt.ylabel("rdb - steps [mm]")
plt.xlabel("Time[sec]")
plt.show()
