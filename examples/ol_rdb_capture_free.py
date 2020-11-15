from wrasc import ppmac_ra as ppra

# from wrasc import gpcom_wrap
from os import environ, path
from examples.motion_tests_ra import OLRDBCapt

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
loop_repeats = tst["loop_repeats"] = 2
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
tst["Mot_A"]["ID"] = f"CIL_M{axis_n}"
tst["Mot_A"]["encoder_reversed"] = axis_n == 4
micro_steps = tst["Mot_A"]["micro_steps"] = 32
fullsteps_per_rev = tst["Mot_A"]["fullsteps_per_rev"] = 200
overall_egu_per_rev = tst["Mot_A"]["overall_egu_per_rev"] = 2
enc_res = tst["Mot_A"]["encoder_res"] = 50e-6  # mm

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


ol_test = OLRDBCapt(_VERBOSE_=_VERBOSE_, tst=tst)

################################################################################################################
# folowing section is defining wrasc agents for specific jobs. nothing happens untill the agents get processed #
################################################################################################################
agents = ppra.ra.compile_n_install({}, globals().copy(), "WORKSHOP01")

# TODO confirm with user before starting the test

ppra.ra.process_loop(
    agents, 100000, cycle_period=tst["wrasc_cycle_period"], debug=True,
)

ol_test.test_ppmac.close

# now load the csv file and plot

filename = ol_test.ma_step_until_ag.csv_file_stamped
print(f"here is the log file: {filename}")

import matplotlib.pyplot as plt

from numpy import genfromtxt
from os import path
from pandas import read_csv, concat

# Enc_Res = 50e-6  # mm/count
# Step_Res = 0.0003125  # mm/ustep

# filename = path.join("autest_out", "ma_small_steps_201111_2030.csv")

df = read_csv(filename)

# test_data = genfromtxt(filename, delimiter=",")

headers = list(df.columns)

gen_headers = dict()
assert "CapturedPos" in headers[1]

for header in headers:
    axis_index = header.split("_")[0][1:]
    if axis_index.isdigit():
        axis_prefix = "cc" if int(axis_index) > 8 else "xx"
    else:
        axis_prefix = ""
    # companion

    gen_ = axis_prefix + header.split("_")[-1]
    gen_headers[gen_] = header

# TODO fix this hardcoded headers!

step_res = tst["Mot_A"]["step_res"] = (
    1
    / tst["Mot_A"]["fullsteps_per_rev"]
    / tst["Mot_A"]["micro_steps"]
    * tst["Mot_A"]["overall_egu_per_rev"]
)


rdb_capt_mm = df[gen_headers["ccCapturedPos"]] * enc_res
rdb_hash_mm = df[gen_headers["ccHashPos"]] * enc_res
rdb_calib_mm = rdb_hash_mm - rdb_capt_mm - df[gen_headers["xxHomeOffset"]] * step_res
step_hash_mm = df[gen_headers["xxHashPos"]] * step_res
time_sec = df["Time"]

plt.plot(time_sec, concat([rdb_calib_mm, step_hash_mm], axis=1))
plt.title("{} and {}".format(gen_headers["ccHashPos"], gen_headers["xxHashPos"]))
plt.ylabel(f"readback and steps [mm]")
plt.xlabel("Time[sec]")
plt.show()

plt.plot(time_sec, rdb_calib_mm - step_hash_mm)
plt.ylabel("rdb - steps [mm]")
plt.xlabel("Time[sec]")
plt.show()
