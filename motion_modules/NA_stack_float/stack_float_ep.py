from os import path

# from tests.test_eputils import test_epicsmotor
from time import sleep

# from epics.ca import replace_printf_handler

# from wrasc import reactive_agent as ra

# from wrasc import gpcom_wrap
# from os import environ, path

from utils.utils import undump_obj, set_test_params

import utils.eputils as et

from pathlib import Path

import logging

import utils.eptesting as est

# Prepare filepath to store logs
logs_file_path = Path.cwd().joinpath("logs", "")
# Create the folder to store logs
logs_file_path.mkdir(parents=True, exist_ok=True)

# Set the basic config for logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    filename="{file}/{name}.log".format(
        file=logs_file_path.as_posix(), name="stack_float_ep"
    ),  # current_datetime.strftime('%Y%m%d-%H%M%S')
)

user_confirm = None


if __name__ == "__main__":

    tst = undump_obj(
        "stack_float", path.join(path.dirname(path.abspath(__file__)), ""),
    )

    # tst["ppmac_hostname"] = "10.23.220.232"
    # tst["ppmac_is_backward"] = True

    motor_id = "Mot_A"
    tst = set_test_params(tst, motor_id)

    mot = et.EpicsMotor("CIL:MOT2", base_settings=tst["Mot_A"])
    # print(f"{mot.printable_list}")
    # for epv in mot.all_epvs:
    #     print(
    #         f"{epv.pyname} -> {epv.fullname} = {epv.PV.value}, tol={epv.default_tolerance}"
    #     )

    """
    - Soft Limits shall be accessible by @scientist at any circumstances
    - Move requests with target position outside the range defined by Soft Limits shall be rejected at software level
    - Soft Limits should apply at controller level to protect and limit the motion, regardless of the higher level controls operating or not.  
    - Soft Limit values shall be synchronised to the actual applied limit in the controller at all times. 
    - Each Soft limit can be disabled by setting to inf
    - Both Soft Limits will be disabled when they are both set to zero
    - For both cases of a rejected setpoint, or an actual readback in violation of the limits, the field .LVIO must be set to 1. This field will be reset to 0 as soon as a new acceptable setpoint is put in.    
    """

    est.tc_base_setting(mot)
    est.tc_move_to_lim(mot, dial_direction=1)
    est.tc_move_to_lim(mot, dial_direction=-1)
    est.tc_home_on_mlim(mot, stop_at_fail=False)

    # # manually home it here until HOMING is implemented:
    # usr = input("Please home the axis manually, and press Y/y to continue")
    # if usr.lower() != "y":
    #     exit(1)

    est.tc_change_offset(mot, set_pos=-1)

    est.tc_move(
        mot, pos_inc=5 * (1 if mot._d_dir.value == 0 else -1), override_slims=True
    )

    # SFT_LMT tests
    est.tc_softlim_inf(mot)
    est.tc_softlims_llm_reject(mot)
    est.tc_base_setting(mot)
    est.tc_move(mot, pos_inc=0, override_slims=False)
    est.tc_softlims_hlm_reject(mot,)
    est.tc_base_setting(mot)
    est.tc_move(mot, pos_inc=0, override_slims=False)
    est.tc_lls(mot)
    est.tc_base_setting(mot)
    est.tc_move(mot, pos_inc=0, override_slims=False)
    est.tc_hls(mot)

    # now test the user coord
    # USR_CRD_FNC

    """
    - User coordinate direction shall be changeable using direction (.DIR) or sign of scale (.MRES) or both
    - User coordinate scale shall be changeable using Motor Record mechanisms i.e. .MRES or .REV or .UREV)
    - In any case, all User Coordinate values and parameters including readback (.RBV), setpoint (.VAL) velocities, and travel limits shall change accordingly and consistently
    - Offset parameter shall be invalidated by any change in User Coordinate
    - All resulting changes shall be synced to the controller automatically and immediately, whenever applicable
    """

    est.tc_base_setting(mot)
    est.tc_toggle_dir(mot)
    est.tc_toggle_dir(mot, stop_at_fail=False)
    est.tc_base_setting(mot)
    est.tc_set_offset(mot, set_pos=-1)
    est.tc_base_setting(mot)

    # see what happens of OFF is changed:

