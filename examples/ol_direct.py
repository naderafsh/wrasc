from wrasc import ppmac_ra as ppra
from wrasc import reactive_agent as ra

# from wrasc import gpcom_wrap
from os import environ, path
from examples.motion_tests_ra import OL_Rdb_Lim2Lim

import utils
from time import sleep

tst = utils.undump_obj("ol_direct_sample", "autest_in")
ol_test = OL_Rdb_Lim2Lim(_VERBOSE_=2, tst=tst)
agents = ppra.ra.compile_n_install({}, globals().copy(), "WORKSHOP01")
max_loop = 100


ppra.process_agents(ol_test.ma_base_config_ag)
ppra.process_agents(ol_test.ma_test_config_ag)
ppra.process_agents(ol_test.ma_go_mlim_ag)
ppra.process_agents(ol_test.ma_home_on_mlim_ag)

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
                -tst["Mot_A"]["bigjog_steps"] + tst["Mot_A"]["smalljog_steps"]
            ) * (1 if is_positive_jog else -1)

        ppra.process_agents(
            [ol_test.ma_slide_on_plim_ag, ol_test.jog_agent(jog_dest, is_positive_jog)]
        )
        if ol_test.ma_slide_on_plim_ag.is_done:
            break
        else:
            n += 1
            print(f"step {n}")

    ppra.process_agents(ol_test.ma_slide_off_plim_ag)

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
                -tst["Mot_A"]["bigjog_steps"] + tst["Mot_A"]["smalljog_steps"]
            ) * (1 if is_positive_jog else -1)

        ppra.process_agents(
            [ol_test.ma_slide_on_mlim_ag, ol_test.jog_agent(jog_dest, is_positive_jog)]
        )
        if ol_test.ma_slide_on_mlim_ag.is_done:
            break
        else:
            n += 1

    ppra.process_agents(ol_test.ma_slide_off_mlim_ag)


print("go celebrate now!")
