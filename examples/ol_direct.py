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


def do_agent(ag_list):
    """process an individual ppra agent, separately

    Args:
        ag_self (ppra.WrascPmacGate): [description]

    Returns:
        [type]: [description]
    """

    if not isinstance(ag_list, list):
        ag_list = [ag_list]

    for ag in ag_list:
        ag.reset()

    while not any([ag.is_done for ag in ag_list]):

        for ag_self in ag_list:
            ag_self: ppra.WrascPmacGate
            ag_self._in_proc()

            desc = ""
            if ag_self.verbose > 0:
                desc = ag_self.annotate()[1]
                print(f"{ag_self.name}: {desc}")

        sleep(0.25)

        for ag_self in ag_list:
            ag_self: ppra.WrascPmacGate
            ag_self._out_proc()


do_agent(ol_test.ma_base_config_ag)
do_agent(ol_test.ma_test_config_ag)
do_agent(ol_test.ma_go_mlim_ag)
do_agent(ol_test.ma_home_on_mlim_ag)

i = 0
while i < tst["loop_repeats"]:
    i += 1

    n = 0
    jog_dest = 0
    while n < max_loop:

        if (n % 2) == 0:
            jog_dest = jog_dest + tst["Mot_A"]["bigjog_steps"]
            ineq = ">" + str(jog_dest) + " - 10"

        else:
            jog_dest = (
                jog_dest - tst["Mot_A"]["bigjog_steps"] + tst["Mot_A"]["smalljog_steps"]
            )
            ineq = "<" + str(jog_dest) + " + 10"

        ol_test.ma_step_ag.setup(
            cry_cmds="#{L1}jog=" + str(jog_dest), pass_conds="#{L1}p" + ineq,
        )

        do_agent([ol_test.ma_slide_on_plim_ag, ol_test.ma_step_ag])
        if ol_test.ma_slide_on_plim_ag.is_done:
            break
        else:
            n += 1

    do_agent(ol_test.ma_slide_off_plim_ag)

    n = 0
    jog_dest = tst["Mot_A"]["fullrange_steps"]
    while n < max_loop:

        if (n % 2) == 0:
            jog_dest = jog_dest - tst["Mot_A"]["bigjog_steps"]
            ineq = "<" + str(jog_dest) + " + 10"

        else:
            jog_dest = (
                jog_dest + tst["Mot_A"]["bigjog_steps"] - tst["Mot_A"]["smalljog_steps"]
            )
            ineq = ">" + str(jog_dest) + " - 10"

        ol_test.ma_step_ag.setup(
            cry_cmds="#{L1}jog=" + str(jog_dest), pass_conds="#{L1}p" + ineq,
        )

        do_agent([ol_test.ma_slide_on_mlim_ag, ol_test.ma_step_ag])
        if ol_test.ma_slide_on_mlim_ag.is_done:
            break
        else:
            n += 1

    do_agent(ol_test.ma_slide_off_mlim_ag)


print("go celebrate now!")
