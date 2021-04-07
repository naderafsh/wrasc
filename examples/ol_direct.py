from wrasc import ppmac_ra as ppra
from os import path


# from wrasc import reactive_agent as ra

# from wrasc import gpcom_wrap
# from os import environ, path
from examples.motion_tests_ra import OL_Rdb_Lim2Lim

import utils
from time import sleep


if __name__ == "__main__":

    tst = utils.undump_obj(
        "ol_stack_float", path.join(path.dirname(path.abspath(__file__)), "autest_in"),
    )
    # tst["ppmac_hostname"] = "10.23.220.232"
    # tst["ppmac_is_backward"] = True

    ol_test = OL_Rdb_Lim2Lim(_VERBOSE_=2, tst=tst, motor_id="Mot_A")
    agents = ppra.ra.compile_n_install({}, globals().copy(), "blah")
    max_loop = 100

    if tst["sysconfig_download"]:
        ppra.do_ags([ol_test.set_wpKey_ag, ol_test.system_config_ag], cycle_period=1)
    if tst["baseconfig_download"]:
        ppra.do_ags(ol_test.ma_base_config_ag)

    # ppra.do_ags(ol_test.set_initial_setup_ag) # loads plc10 and prog 10 !

    ppra.do_ags(ol_test.ma_test_config_ag)
    ppra.do_ags(ol_test.ma_go_mlim_ag)
    ppra.do_ags(ol_test.ma_home_on_mlim_ag)

    i = 0
    while i < tst["loop_repeats"]:
        i += 1

        n = 0
        jog_dest = 0
        overall_positive = True
        while n < max_loop:

            is_big_jog = (n % 2) == 0
            is_positive_jog = is_big_jog == overall_positive

            if is_big_jog:
                jog_dest = jog_dest + tst["Mot_A"]["bigjog_steps"] * (
                    1 if is_positive_jog else -1
                )
            else:
                jog_dest = jog_dest + (
                    tst["Mot_A"]["bigjog_steps"] - tst["Mot_A"]["smalljog_steps"]
                ) * (1 if is_positive_jog else -1)

            ppra.do_ags(
                [
                    ol_test.ma_slide_on_plim_ag,
                    ol_test.jog_agent(jog_dest, is_positive_jog),
                ],
                all_done=False,
            )
            if ol_test.ma_slide_on_plim_ag.is_done:
                break
            else:
                n += 1
                print(f"step {n}")

        ppra.do_ags(ol_test.ma_slide_off_plim_ag)

        n = 0
        jog_dest = tst["Mot_A"]["fullrange_steps"]
        overall_positive = False
        while n < max_loop:
            is_big_jog = (n % 2) == 0
            is_positive_jog = is_big_jog == overall_positive

            if is_big_jog:
                jog_dest = jog_dest + tst["Mot_A"]["bigjog_steps"] * (
                    1 if is_positive_jog else -1
                )
            else:
                jog_dest = jog_dest + (
                    tst["Mot_A"]["bigjog_steps"] - tst["Mot_A"]["smalljog_steps"]
                ) * (1 if is_positive_jog else -1)

            ppra.do_ags(
                [
                    ol_test.ma_slide_on_mlim_ag,
                    ol_test.jog_agent(jog_dest, is_positive_jog),
                ],
                all_done=False,
            )
            if ol_test.ma_slide_on_mlim_ag.is_done:
                break
            else:
                n += 1

        ppra.do_ags(ol_test.ma_slide_off_mlim_ag)

    print("go celebrate now!")
