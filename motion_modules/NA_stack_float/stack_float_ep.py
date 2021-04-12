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


def verify_all(verify_epvs):
    fail_count = 0
    msg = ""
    for epv in verify_epvs:
        assert isinstance(epv, et.EPV)
        verified = epv.verify()
        if verified:
            if epv.tolerance != epv.default_tolerance:
                msg += f"{epv.PV.pvname}({epv.value}) is within {epv.tolerance} of expected({epv.expected_value}) [{epv.PV.units}]\n"
        elif not epv.fail_if_unexpected:
            msg += f"  Change: {epv.PV.pvname}({epv.value}) was {epv.expected_value}\n"
        else:
            fail_count += 1
            msg += f"  Fail: {epv.PV.pvname}({epv.value}) expected value is {epv.expected_value}\n"

        if not epv.persistent_failure and verified is False:
            # once a fail is reported, the expected value can be set to actual
            # so that this failure is not spread to consequential tests.
            # this feature shall be used with extreme care;
            epv.expected_value = None

    passed = fail_count == 0

    msg += (
        f"\n ** FAIL ** {fail_count} unexpeced values.\n"
        if not passed
        else "\n** PASS **"
    )

    return passed, msg


def test_case(func):
    def function_wrapper(mot: et.EpicsMotor, **kwargs):

        print(f"{func.__name__} {kwargs}", end=" ... ")
        logging.info(f"{func.__name__}\nDescription:\n{func.__doc__}")
        f_msg = func(mot, **kwargs)
        sleep(mot.default_wait)
        passed, msg = verify_all(verify_epvs)
        if f_msg:
            msg = f_msg + msg
        v_msg = "Outcome:\n" + ("  Not verified!" if not msg else msg)
        logging.info(f"\n{v_msg}")
        sleep(0.25)
        if passed:
            print("pass")
        else:
            print("FAIL")

        # wait for the user to interact
        if stop_at_fail and not passed:
            usr = input("press any key... [Abort]")
            if usr.upper() == "A":
                print("Aborting.")
                exit(1)
        return passed, v_msg

    return function_wrapper


@test_case
def tc_base_setting(mot: et.EpicsMotor, **kwargs):
    """  set/reset to the baseline settings and reset all expected values
    """

    mot._d_lvio.expected_value = 0

    # to check if the motor is initialised with no faults:
    mot._d_mres.value = 1 / 200 / 32
    mot._d_mscf.value = tst["Mot_A"]["motor_unit_per_rev"]
    # mot._d_off.value = 0

    mot._d_vmax.value = tst["Mot_A"]["JogSpeed_EGU"]
    mot._d_velo.value = mot._d_vmax.value - mot._d_velo.default_tolerance * 5
    mot._d_bvel.value = mot._d_velo.value / 2

    mot._d_twv.value = 5

    mot._d_hlm.value = tst["Mot_A"]["fullrange_egu"] * (1.01)
    mot._d_llm.value = 0 - tst["Mot_A"]["fullrange_egu"] * (0.01)

    mot._d_set.value = 0

    mot._d_dir.value = 0

    mot.reset_expected_values()


@test_case
def tc_move_to_mlim(mot: et.EpicsMotor, **kwargs):
    """move to hardware mlim using preset range information (not JREV)
    """
    # move indefinitely reverse towards mlim
    mot._d_lls.expected_value = 1 - mot._d_dir.value
    mot._d_hls.expected_value = mot._d_dir.value

    mlim_direction = -2 * (0.5 - mot._d_dir.value)

    mot.move(
        mlim_direction * mot.travel_range, override_slims=True, expect_success=False,
    )

    # move indefinitely reverse towards mlim
    mot._d_msta.expected_value = "$x10xx0xx0xxx0xxx"

    # wait for the flags to come back, in addition to motors default wait
    sleep(0.5)


@test_case
def tc_move_to_lim(mot: et.EpicsMotor, **kwargs):
    """move to hardware mlim using preset range information (not JREV)
    """

    dial_direction = kwargs.get("dial_direction", None)

    usr_direction = 2 * (0.5 - mot._d_dir.value) * dial_direction

    # move indefinitely reverse towards mlim
    mot._d_lls.expected_value = 1 if usr_direction < 0 else 0
    mot._d_hls.expected_value = 0 if usr_direction < 0 else 1

    mot.move(
        usr_direction * mot.travel_range, override_slims=True, expect_success=False,
    )

    # move indefinitely reverse towards mlim
    mot._d_msta.expected_value = (
        "$x10xx0xx0xxx0xxx" if dial_direction < -1 else "$x00xx0xx0xxx1xxx"
    )

    # wait for the flags to come back, in addition to motors default wait
    sleep(0.5)


@test_case
def tc_home_on_mlim(mot: et.EpicsMotor, **kwargs):
    """home using extras
    """
    mot._d_hls.expected_value = 0
    mot._d_lls.expected_value = 0
    mot._d_msta.expected_value = "$100xx0xx0xxx0xxx"  # bit 15 (HOMED)

    mot._c_homing = 1


@test_case
def tc_change_offset(mot: et.EpicsMotor, **kwargs):
    """USR_CRD_FNC
       change offset value (directly) to match the input [set_pos]
       ( not using .SET mechanism )
       verify that all user coord variables immediately change accoringly
    """

    assert mot._d_dmov.value

    set_pos = kwargs.get("set_pos", 1)

    offset = set_pos - mot._d_rbv.value

    mot._d_rbv.expected_value = set_pos
    mot._d_val.expected_value = mot._d_val.value + offset
    mot._d_dmov.expected_value = 1
    # rdif shall remain unchanged
    mot._d_rdif.expected_value = mot._d_rdif.value

    mot._d_hlm.value = mot.travel_range
    mot._d_llm.value = 0

    mot._d_set.value = 0

    mot._d_hlm.expected_value = mot._d_hlm.expected_value + offset
    mot._d_llm.expected_value = mot._d_llm.expected_value + offset

    mot._d_off.value += offset


@test_case
def tc_move(mot: et.EpicsMotor, **kwargs):
    """move incremental
    """
    mot.move(**kwargs)


@test_case
def tc_softlim_inf(mot: et.EpicsMotor, **kwargs):
    """
    SFT_LMT
    softlims set to inf
    """
    mot._d_hlm.value = float("inf")
    mot._d_llm.value = -float("inf")


@test_case
def tc_softlims_llm_reject(mot: et.EpicsMotor, **kwargs):
    """
    SFT_LMT
    requests outside the softlims shall be rejected
    """

    pos_inc = kwargs.get("pos_inc", -1)
    # setting llm so that the requested move is outside the limit
    mot._d_llm.value = mot._d_rbv.value + pos_inc + mot._d_llm.default_tolerance

    # new val shall be rejected, reverted back to: old val, or rbv?
    mot._d_val.expected_value = mot._d_val.value

    # soft limit flag shall be raised
    mot._d_lvio.expected_value = 1

    # val to rbv value shall not change
    mot._d_rdif.expected_value = mot._d_rdif.value

    mot.move(pos_inc=pos_inc, override_slims=False, expect_success=False)


@test_case
def tc_softlims_hlm_reject(mot: et.EpicsMotor, **kwargs):
    """
    SFT_LMT
    requests outside the softlims shall be rejected
    """
    pos_inc = kwargs.get("pos_inc", 1)
    mot._d_hlm.value = mot._d_rbv.value + pos_inc - mot._d_hlm.default_tolerance

    mot.move(pos_inc=pos_inc, override_slims=False, expect_success=False)

    # new val shall be rejected, reverted back to sync rbv
    mot._d_val.expected_value = mot._d_rbv.value

    # sof limit flag raised
    mot._d_lvio.expected_value = 1

    # val and rbv synced
    mot._d_rdif.expected_value = 0


@test_case
def tc_lls(mot: et.EpicsMotor, **kwargs):
    """
    SFT_LMT
    when softlimit is changed so that current position is out of softlimit range
    """
    mot._d_llm.value = mot._d_rbv.value + mot._d_llm.default_tolerance

    # new val shall be rejected, reverted back to sync rbv
    mot._d_val.expected_value = mot._d_rbv.value

    # sof limit flag raised
    mot._d_lvio.expected_value = 1

    # val and rbv synced
    mot._d_rdif.expected_value = 0

    mot._d_lls.expected_value = 1


@test_case
def tc_hls(mot: et.EpicsMotor, **kwargs):
    """
    SFT_LMT
    when softlimit is changed so that current position is out of softlimit range
    """
    mot._d_hlm.value = mot._d_rbv.value - mot._d_hlm.default_tolerance

    # new val shall be rejected, reverted back to sync rbv
    mot._d_val.expected_value = mot._d_rbv.value

    # sof limit flag raised
    mot._d_lvio.expected_value = 1

    # val and rbv synced
    mot._d_rdif.expected_value = 0

    mot._d_hls.expected_value = 1


@test_case
def tc_toggle_dir(mot: et.EpicsMotor, **kwargs):
    """USR_CRD_FNC
       toggle .DIR (directly) 
       
       verify that all user coord variables immediately change accordingly
       so that:
       1 - motion direction is reversed, meaning .DRBV -> -.DRBV
       2 - offset is chaged so that current readback value is unchanged


    """

    assert mot._d_dmov.value

    post_dir = 1 - mot._d_dir.value

    dir_sign = 1 if post_dir == 0 else -1

    mot._d_drbv.expected_value = mot._d_off.value + dir_sign * mot._d_rbv.value

    mot._d_dmov.expected_value = 1
    # change of direction is around the CURRENT position
    mot._d_rbv.expected_value = mot._d_rbv.value
    mot._d_rdif.expected_value = mot._d_rdif.value

    # no changes in the status ?
    # an "unused bit of the MSTA actually changes!"

    mot._d_msta.expected_value = mot._d_msta.value

    mot._d_dir.value = post_dir


@test_case
def tc_set_offset(mot: et.EpicsMotor, **kwargs):
    """USR_CRD_FNC
       set user offset using .SET so that .VAL matches tuser request [set_pos]
       ( this is using .SET mechanism)
       verify that all user coord variables immediately change accoringly
    """

    assert mot._d_dmov.value

    set_pos = kwargs.get("set_pos", 1)

    mot._d_val.expected_value = set_pos
    mot._d_off.expected_value = set_pos - mot._d_val.value + mot._d_off.value

    mot._d_dmov.expected_value = 1
    # rdif shall remain unchanged
    mot._d_rdif.expected_value = mot._d_rdif.value

    mot._d_set.value = 1
    mot._d_val.value = set_pos


if __name__ == "__main__":

    stop_at_fail = True

    tst = undump_obj(
        "stack_float", path.join(path.dirname(path.abspath(__file__)), ""),
    )

    # tst["ppmac_hostname"] = "10.23.220.232"
    # tst["ppmac_is_backward"] = True

    motor_id = "Mot_A"
    tst = set_test_params(tst, motor_id)

    mot = et.EpicsMotor(
        "CIL:MOT2",
        travel_range=tst["Mot_A"]["fullrange_egu"],
        InPosBand=tst["Mot_A"]["InPosBand"],
    )
    # print(f"{mot.printable_list}")
    # for epv in mot.all_epvs:
    #     print(
    #         f"{epv.pyname} -> {epv.fullname} = {epv.PV.value}, tol={epv.default_tolerance}"
    #     )

    user_setting_s = [
        mot._d_twv,
    ]

    velo_s = [
        mot._d_velo,
        mot._d_vmax,
    ]

    val_and_rbv_s = [mot._d_val, mot._d_rbv, mot._d_rdif]

    usr_coord_setting_s = [
        mot._d_mres,
        mot._d_mscf,
        mot._d_off,
    ]

    soft_lim_s = [
        mot._d_hlm,
        mot._d_llm,
    ]

    extra_s = [
        mot._d_bdst,
        mot._d_bvel,
    ]

    verify_epvs = set(usr_coord_setting_s + velo_s + mot.usregu_epvs + mot.status_epvs)

    """
    - Soft Limits shall be accessible by @scientist at any circumstances
    - Move requests with target position outside the range defined by Soft Limits shall be rejected at software level
    - Soft Limits should apply at controller level to protect and limit the motion, regardless of the higher level controls operating or not.  
    - Soft Limit values shall be synchronised to the actual applied limit in the controller at all times. 
    - Each Soft limit can be disabled by setting to inf
    - Both Soft Limits will be disabled when they are both set to zero
    - For both cases of a rejected setpoint, or an actual readback in violation of the limits, the field .LVIO must be set to 1. This field will be reset to 0 as soon as a new acceptable setpoint is put in.    
    """

    tc_base_setting(mot)
    tc_move_to_lim(mot, dial_direction=1)
    tc_move_to_lim(mot, dial_direction=-1)
    # tc_home_on_mlim(mot)

    # # manually home it here until HOMING is implemented:
    # usr = input("Please home the axis manually, and press Y/y to continue")
    # if usr.lower() != "y":
    #     exit(1)

    tc_change_offset(mot, set_pos=-1)

    tc_move(mot, pos_inc=5 * (1 if mot._d_dir.value == 0 else -1), override_slims=True)

    # SFT_LMT tests
    tc_softlim_inf(mot)
    tc_softlims_llm_reject(mot)
    tc_base_setting(mot,)
    tc_move(mot, pos_inc=0, override_slims=False)
    tc_softlims_hlm_reject(mot,)
    tc_base_setting(mot,)
    tc_move(mot, pos_inc=0, override_slims=False)
    tc_lls(mot)
    tc_base_setting(mot,)
    tc_move(mot, pos_inc=0, override_slims=False)
    tc_hls(mot)

    # now test the user coord
    # USR_CRD_FNC

    """
    - User coordinate direction shall be changeable using direction (.DIR) or sign of scale (.MRES) or both
    - User coordinate scale shall be changeable using Motor Record mechanisms i.e. .MRES or .REV or .UREV)
    - In any case, all User Coordinate values and parameters including readback (.RBV), setpoint (.VAL) velocities, and travel limits shall change accordingly and consistently
    - Offset parameter shall be invalidated by any change in User Coordinate
    - All resulting changes shall be synced to the controller automatically and immediately, whenever applicable
    """

    tc_base_setting(mot)
    tc_toggle_dir(mot)
    tc_toggle_dir(mot)
    tc_base_setting(mot)
    tc_set_offset(mot, set_pos=-1)

    # see what happens of OFF is changed:

