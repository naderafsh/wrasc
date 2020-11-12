import matplotlib.pyplot as plt

from numpy import genfromtxt
from os import path
import pandas as pd

Enc_Res = 50e-6  # mm/count
Step_Res = 0.0003125  # mm/ustep

filename = path.join("autest_out", "ma_small_steps_201111_2030.csv")


df = pd.read_csv(filename)

# test_data = genfromtxt(filename, delimiter=",")

headers = list(df.columns)

assert "CapturedPos" in headers[1]

rdb_capt_mm = df["M11_CapturedPos"] * Enc_Res
rdb_hash_mm = df["A11_HashPos"] * Enc_Res
rdb_calib_mm = rdb_hash_mm - rdb_capt_mm - df["M3_HomeOffset"] * Step_Res
step_hash_mm = df["A3_HashPos"] * Step_Res
time_sec = df["Time"]

plt.plot(time_sec, pd.concat([rdb_calib_mm, step_hash_mm], axis=1))
plt.ylabel("rdb and steps [mm]")
plt.xlabel("Time[sec]")
plt.show()

plt.plot(time_sec, rdb_calib_mm - step_hash_mm)
plt.ylabel("rdb - steps [mm]")
plt.xlabel("Time[sec]")
plt.show()

