from os import path
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
    for epv in verify_epvs:
        if epv.verify():
            pass
            # print(
            #     # f"Pass: {epv.PV.pvname} is {epv.value} is within {epv.default_tolerance} error limit"
            #     f"Pass: {epv.PV.pvname} "
            # )
        else:
            fail_count += 1
            print(
                f"Fail: {epv.PV.pvname} is {epv.value} instead of {epv.expected_value}"
            )
    print(f"test finished with {fail_count} fails.")


def tc_initial_setting():
    """initial setting
    """
    print(f"running: {__doc__}")
    # test case #1

    # to check if the motor is initialised with no faults:
    mot._d_mres.value = 0.0001
    mot._d_mscf.value = 1.0
    mot._d_off.value = 0

    mot._d_vmax.value = 4
    mot._d_velo.value = mot._d_vmax.value - mot._d_vmax.default_tolerance * 5
    mot._d_bvel.value = mot._d_velo.value / 2

    mot._d_twv.value = 5

    mot._d_hlm.value = 80
    mot._d_llm.value = 1


def tc_initial_position():
    """move to a fixed positon?
    """

    print(f"running: {__doc__}")

    mot._d_val.value = 10
    mot._d_rdif.expected_value = 0
    mot._d_rbv.expected_value = 10
    # and wait until dmov or timeout:
    timeout = mot._d_val.value / mot._d_velo.value * 2
    sleep(0.1)
    start_time = time()
    while not mot._d_dmov.value:
        print(f".", end="")
        sleep(0.05)
        if time() - start_time > timeout:
            print(f"timeout")
            break
    print("")


if __name__ == "__main__":

    tst = undump_obj(
        "stack_float", path.join(path.dirname(path.abspath(__file__)), ""),
    )

    # tst["ppmac_hostname"] = "10.23.220.232"
    # tst["ppmac_is_backward"] = True

    motor_id = "Mot_A"
    tst = set_test_params(tst, motor_id)

    mot = et.EpicsMotor("CIL:MOT2")
    # print(f"{mot.printable_list}")
    # for epv in mot.all_epvs:
    #     print(
    #         f"{epv.pyname} -> {epv.fullname} = {epv.PV.value}, tol={epv.default_tolerance}"
    #     )

    user_setting_s = [
        mot._d_twv,
    ]

    control_s = [
        mot._c_kill_d_proc,
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

    tc_initial_setting()
    verify_all()
    tc_initial_position()
    verify_all()
