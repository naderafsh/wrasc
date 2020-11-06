from wrasc import reactive_agent as ra
from wrasc import ppmac_ra as ppra

# from wrasc import gpcom_wrap
from os import environ, path
from ppmac import GpasciiClient
import examples.ppmac_code_templates as tls
import utils
import yaml

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


_VERBOSE_ = 3


tst = dict()

Script_Loop_Period = tst["Script_Loop_Period"] = 0.25
Loop_Repeats = tst["Loop_Repeats"] = 20
Collision_Clearance = tst["Collision_Clearance"] = 200000

PpGlobal_Filename = tst[
    "PpGlobal_Filename"
] = r"C:\Users\afsharn\gitdir\psych\outdir\NA_brake_test\Database\pp_global.sym"
BaseConfig_FileName = tst[
    "BaseConfig_FileName"
] = r"C:\Users\afsharn\gitdir\wrasc\examples\data\ppmac_base_config.cfg"

# pp_glob_dictst data


tst["Mot_A"] = ppra.axis(3).LVars()
tst["Mot_B"] = ppra.axis(4).LVars()

tst["Mot_A"]["JogSpeed"] = 3.2
tst["Mot_B"]["JogSpeed"] = 3.2

tst["Mot_A"]["Reverse_Enc"] = False
tst["Mot_B"]["Reverse_Enc"] = True

# tst["Mot_A"]["Trig_Offset"] = 100
# tst["Mot_B"]["Trig_Offset"] = 100

tst["Mot_A"]["Home_Vel"] = 1.28
tst["Mot_B"]["Home_Vel"] = 1.28

tst["Mot_A"]["SlideOff_Dist"] = 400
tst["Mot_B"]["SlideOff_Dist"] = 400

tst["Mot_A"]["csv_file_name"] = path.join("autest_out", "ma_capture.csv")
tst["Mot_B"]["csv_file_name"] = path.join("autest_out", "mb_capture.csv")

tst["Mot_A"]["SettlePos"] = 2000
tst["Mot_B"]["SettlePos"] = 2000


# tst = utils.undump_obj("sample_test", "autest_in")
print(tst)

utils.dump_obj(tst, path.join("autest_in", "sample_test" + ".yaml"))

# test code
# Linux:  export PPMAC_TEST_IP="10.23.92.220"
# Win sc: $env:PPMAC_TEST_IP="10.23.92.220"
ppmac_test_IP = environ["PPMAC_TEST_IP"]
test_gpascii = GpasciiClient(ppmac_test_IP)
# it is possible to use multiple gpascii channels,
# but we don't have a reason to do so, yet!
test_gpascii_A = test_gpascii
test_gpascii_B = test_gpascii

pp_glob_dict = ppra.load_pp_globals(PpGlobal_Filename)
with open(BaseConfig_FileName) as f:
    base_config = f.read().splitlines()
    f.close

# verify strings are native ppmac
# but commands use macros in {} (defined by ppra.macrostrs) which need to be evaluated realtime.

ma_base_config_ag = ppra.WrascPmacGate(verbose=_VERBOSE_, ppmac=test_gpascii_A,)
mb_base_config_ag = ppra.WrascPmacGate(verbose=_VERBOSE_, ppmac=test_gpascii_B,)

ma_init_checks_ag = ppra.WrascPmacGate(verbose=_VERBOSE_, ppmac=test_gpascii_A,)
mb_init_checks_ag = ppra.WrascPmacGate(verbose=_VERBOSE_, ppmac=test_gpascii_B,)

# TODO add home all here

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
config_stats = ppra.expand_globals(base_config, pp_glob_dict, **tst["Mot_A"])

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

# -------- motor B
config_stats = ppra.expand_globals(base_config, pp_glob_dict, **tst["Mot_B"])
mb_base_config_ag.setup(
    **tst["Mot_B"], cry_cmds=config_stats, celeb_cmds="#{L1}$",
)
mb_base_config_ag.cry_retries = 2
# -------------------------------------------------------------------

# -------------------------------------------------------------------
# 0 - check configuration
# also add axis confix if there are deviations from baseConfig

# -------- motor A

rev_enc_cmd = (
    ["PowerBrick[L2].Chan[L3].EncCtrl=7"]
    if tst["Mot_B"]["Reverse_Enc"]
    else ["PowerBrick[L2].Chan[L3].EncCtrl=3"]
)


ma_init_checks_ag.setup(
    cry_cmds=tls.config_rdb_lmt + rev_enc_cmd, celeb_cmds=["%100"], **tst["Mot_A"],
)

# -------- motor B

# axis config
# reverse encoder direction for motor B companion

rev_enc_cmd = (
    ["PowerBrick[L2].Chan[L3].EncCtrl=7"]
    if tst["Mot_B"]["Reverse_Enc"]
    else ["PowerBrick[L2].Chan[L3].EncCtrl=3"]
)

mb_init_checks_ag.setup(
    cry_cmds=tls.config_rdb_lmt + rev_enc_cmd, celeb_cmds=["%100"], **tst["Mot_B"],
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
    celeb_cmds="#{L1}hm j/",  # stop incomplete to leave HomeComplete at 0
)


# 0.2 - Home sliding off the limit

ma_init_on_home_ag = ppra.WrascPmacGate(
    verbose=_VERBOSE_,
    ppmac=test_gpascii_A,
    **tst["Mot_A"],
    pass_conds=["Motor[L1].HomeComplete==1", "Motor[L1].InPos==1"],
    cry_cmds="#{L1}hm",
    celeb_cmds="#{L7} kill",
)


# -------- motor B

mb_init_on_lim_ag = ppra.WrascPmacGate(
    verbose=_VERBOSE_,
    ppmac=test_gpascii_A,
    **tst["Mot_B"],
    pass_conds=tls.cond_on_neg_lim,
    cry_cmds="#{L1}j-",
    celeb_cmds="#{L1}hm j/",  # stop incomplete to leave HomeComplete at 0
)


# 0.2 - Home sliding off the limit

mb_init_on_home_ag = ppra.WrascPmacGate(
    verbose=_VERBOSE_,
    ppmac=test_gpascii_A,
    **tst["Mot_B"],
    pass_conds=["Motor[L1].HomeComplete==1", "Motor[L1].InPos==1"],
    cry_cmds="#{L1}hm",
    celeb_cmds="#{L7} kill",
)


# -------------------------------------------------------------------


# -------------------------------------------------------------------
# -------------------------------------------------------------------


# 1 - settle at staring point

# -------- motor A
SettlePos = tst["Mot_A"]["SettlePos"]
ma_start_pos_ag.setup(
    **tst["Mot_A"],
    pass_conds=tls.assert_pos_wf(tst["Mot_A"]["L1"], SettlePos, 10)[0],
    cry_cmds=["#{L1}jog=={SettlePos}"],
    celeb_cmds=[],
)

# -------- motor B
SettlePos = tst["Mot_B"]["SettlePos"]
mb_start_pos_ag.setup(
    **tst["Mot_B"],
    pass_conds=tls.assert_pos_wf(tst["Mot_B"]["L1"], SettlePos, 10)[0],
    cry_cmds=["#{L1}jog=={SettlePos}"],
    celeb_cmds=[],
)

# -------------------------------------------------------------------
# 2 - Move onto the minus limit and wait to stabilise,

# -------- motor A
ma_on_lim_ag.setup(
    **tst["Mot_A"],
    cry_cmds=["#{L1}jog-"],
    pass_conds=tls.cond_on_neg_lim,
    celeb_cmds=["#{L7}kill"],
)

ma_on_lim_ag.dwell_aoa = 2
ma_on_lim_ag.act_on_armed = dwell_aoa

# -------- motor B
mb_on_lim_ag.setup(
    **tst["Mot_B"],
    cry_cmds=["#{L1}jog-"],
    pass_conds=["Motor[L1].MinusLimit>0", "Motor[L1].InPos>0"],
    celeb_cmds=["#{L7}kill"],
)

mb_on_lim_ag.dwell_aoa = 2
mb_on_lim_ag.act_on_armed = dwell_aoa

# -------------------------------------------------------------------
# 3 - Arm Capture and slide off for capturing the falling edge

# -------- motor A
pass_logs = ppra.expand_globals(tls.log_capt_rbk_tl, pp_glob_dict, **tst["Mot_A"])

ma_slide_off_ag.setup(
    **tst["Mot_A"],
    SlideOff_Dir="+",
    cry_cmds=[
        "Motor[L1].JogSpeed={Home_Vel}",
        "#{L7}j:{SlideOff_Dir}{SlideOff_Dist}",
        "Motor[L7].CapturePos=1",
        "#{L1}j:{SlideOff_Dir}{SlideOff_Dist}",
    ],
    pass_conds=tls.check_off_limit_inpos_tl,
    pass_logs=pass_logs,
    # resetting the changes in this action
    celeb_cmds=[
        "Motor[L1].JogSpeed={JogSpeed}",
        "PowerBrick[L2].Chan[L3].CountError=0",
    ],
)
ma_slide_off_ag.dwell_aoa = 0.01
ma_slide_off_ag.act_on_armed = dwell_aoa

# -------- motor B

pass_logs = ppra.expand_globals(tls.log_capt_rbk_tl, pp_glob_dict, **tst["Mot_B"])

mb_slide_off_ag.setup(
    **tst["Mot_B"],
    SlideOff_Dir="+",
    cry_cmds=[
        "Motor[L1].JogSpeed={Home_Vel}",
        "#{L7}j:{SlideOff_Dir}{SlideOff_Dist}",
        "Motor[L7].CapturePos=1",
        "#{L1}j:{SlideOff_Dir}{SlideOff_Dist}",
    ],
    pass_conds=tls.check_off_limit_inpos_tl,
    pass_logs=pass_logs,
    # resetting the changes in this action
    celeb_cmds=[
        "Motor[L1].JogSpeed={JogSpeed}",
        "PowerBrick[L2].Chan[L3].CountError=0",
    ],
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
        f"#{tst['Mot_A']['L7']}p > #{tst['Mot_B']['L7']}p + {Collision_Clearance}",
        # and it is decreasing
        f"Motor[{tst['Mot_A']['L1']}].ActVel - Motor[{tst['Mot_B']['L1']}].ActVel > 0",
    ],
    celeb_cmds=[f"#{tst['Mot_A']['L1']},{tst['Mot_B']['L1']}kill"],
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

mb_init_checks_ag.poll_pr = lambda ag_self: mb_base_config_ag.is_done
mb_init_on_lim_ag.poll_pr = lambda ag_self: mb_init_checks_ag.is_done
mb_init_on_home_ag.poll_pr = lambda ag_self: mb_init_on_lim_ag.is_done

# setup the sequence default dependency (can be done automaticatlly)
mb_start_pos_ag.poll_pr = (
    lambda ag_self: ma_init_on_home_ag.is_done and mb_init_on_home_ag.is_done
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
    agents, 100000, cycle_period=Script_Loop_Period, debug=True,
)

test_gpascii.close
