from os import path
from tests.test_eputils import test_epicsmotor
from time import sleep, time
from typing import Union

from epics.ca import replace_printf_handler

# from wrasc import reactive_agent as ra

# from wrasc import gpcom_wrap
# from os import environ, path

from utils.utils import undump_obj, set_test_params

import utils.eputils as et


def verify_all():
    fail_count = 0
    msg = ""
    for epv in verify_epvs:
        if epv.verify():
            pass
            # print(
            #     # f"Pass: {epv.PV.pvname} is {epv.value} is within {epv.default_tolerance} error limit"
            #     f"Pass: {epv.PV.pvname} "
            # )
        elif not epv.fail_if_unexpected:
            msg += f"  Change: {epv.PV.pvname} is {epv.value} was {epv.expected}\n"
        else:
            fail_count += 1
            msg += f"  Fail: {epv.PV.pvname} is {epv.value} instead of {epv.expected}\n"

    passed = fail_count == 0

    msg += f"\nFinished with {fail_count} fails.\n" if not passed else "\n** PASS **"

    return passed, msg


def test_case(func):
    def function_wrapper(mot: et.EpicsMotor, **kwargs):
        print(f"<<< {func.__name__}\n{func.__doc__}", end="")
        msg = func(mot, **kwargs)
        sleep(mot.default_wait)
        passed, msg = verify_all()
        msg = "  Not verified!" if not msg else msg
        print(f"\n{msg}", end="\n>>>\n\n")
        sleep(1)
        return passed, msg

    return function_wrapper


@test_case
def tc_base_setting(mot: et.EpicsMotor, **kwargs):
    """initial setting
    """

    mot._d_lvio.expected = 0

    # to check if the motor is initialised with no faults:
    mot._d_mres.value = 1 / 200 / 32
    mot._d_mscf.value = tst["Mot_A"]["motor_unit_per_rev"]
    # mot._d_off.value = 0

    mot._d_vmax.value = tst["Mot_A"]["JogSpeed_EGU"]
    mot._d_velo.value = mot._d_vmax.value - mot._d_vmax.default_tolerance * 5
    mot._d_bvel.value = mot._d_velo.value / 2

    mot._d_twv.value = 5

    mot._d_hlm.value = tst["Mot_A"]["travel_range_egu"] * (1.01)
    mot._d_llm.value = 0 - tst["Mot_A"]["travel_range_egu"] * (0.01)

    mot.reset_expected_values()


@test_case
def tc_move_to_mlim(mot: et.EpicsMotor, **kwargs):
    """using limited move not JFOR
    """
    # move indefinitely reverse towards mlim
    mot._d_lls.expected = 1
    mot._d_hls.expected = 0

    mot.move(
        -mot.travel_range, override_slims=True, expect_success=False,
    )


@test_case
def tc_home_on_mlim(mot: et.EpicsMotor, **kwargs):
    """home using extras
    """
    mot._d_hls.expected = 0
    mot._d_lls.expected = 0
    mot._d_msta.expected = "$100xx0xx0xxx0xxx"  # bit 15 (HOMED)

    mot._c_homing = 1


@test_case
def tc_change_offset(mot: et.EpicsMotor, **kwargs):

    assert mot._d_dmov.value

    set_pos = kwargs.get("set_pos", 1)

    offset = set_pos - mot._d_rbv.value

    mot._d_rbv.expected = set_pos
    mot._d_val.expected = mot._d_val.value + offset
    mot._d_dmov.expected = 1
    # rdif shall remain unchanged
    mot._d_rdif.expected = mot._d_rdif.value

    mot._d_hlm.value = mot.travel_range
    mot._d_llm.value = 0

    mot._d_hlm.expected = mot._d_hlm.expected + offset
    mot._d_llm.expected = mot._d_llm.expected + offset

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
    mot._d_llm.value = mot._d_rbv.value + pos_inc + mot._d_rbv.default_tolerance
    mot.move(pos_inc=pos_inc, override_slims=False, expect_success=False)

    # new val shall be rejected, reverted back to sync rbv
    mot._d_val.expected = mot._d_rbv.value

    # sof limit flag raised
    mot._d_lvio.expected = 1

    # val and rbv synced
    mot._d_rdif.expected = 0


@test_case
def tc_softlims_hlm_reject(mot: et.EpicsMotor, **kwargs):
    """
    SFT_LMT
    requests outside the softlims shall be rejected
    """
    pos_inc = kwargs.get("pos_inc", 1)
    mot._d_hlm.value = mot._d_rbv.value + pos_inc - mot._d_rbv.default_tolerance

    mot.move(pos_inc=pos_inc, override_slims=False, expect_success=False)

    # new val shall be rejected, reverted back to sync rbv
    mot._d_val.expected = mot._d_rbv.value

    # sof limit flag raised
    mot._d_lvio.expected = 1

    # val and rbv synced
    mot._d_rdif.expected = 0


@test_case
def tc_lls(mot: et.EpicsMotor, **kwargs):
    """
    SFT_LMT
    when softlimit is changed so that current position is out of softlimit range
    """
    mot._d_llm.value = mot._d_rbv.value + mot._d_rbv.default_tolerance

    # new val shall be rejected, reverted back to sync rbv
    mot._d_val.expected = mot._d_rbv.value

    # sof limit flag raised
    mot._d_lvio.expected = 1

    # val and rbv synced
    mot._d_rdif.expected = 0

    mot._d_lls.expected = 1


@test_case
def tc_hls(mot: et.EpicsMotor, **kwargs):
    """
    SFT_LMT
    when softlimit is changed so that current position is out of softlimit range
    """
    mot._d_hlm.value = mot._d_rbv.value - mot._d_rbv.default_tolerance

    # new val shall be rejected, reverted back to sync rbv
    mot._d_val.expected = mot._d_rbv.value

    # sof limit flag raised
    mot._d_lvio.expected = 1

    # val and rbv synced
    mot._d_rdif.expected = 0

    mot._d_hls.expected = 1


if __name__ == "__main__":

    tst = undump_obj(
        "stack_float", path.join(path.dirname(path.abspath(__file__)), ""),
    )

    # tst["ppmac_hostname"] = "10.23.220.232"
    # tst["ppmac_is_backward"] = True

    motor_id = "Mot_A"
    tst = set_test_params(tst, motor_id)

    mot = et.EpicsMotor("CIL:MOT2", travel_range=100)
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
    tc_move_to_mlim(mot)
    # tc_home_on_mlim(mot)

    # # manually home it here until HOMING is implemented:
    # usr = input("Please home the axis manually, and press Y/y to continue")
    # if usr.lower() != "y":
    #     exit(1)

    tc_change_offset(mot, set_pos=-1)

    tc_move(mot, pos_inc=5, override_slims=True)

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

    # see what happens of OFF is changed:

