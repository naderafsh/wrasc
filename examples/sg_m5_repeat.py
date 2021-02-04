# this provides ppmac agent/tasking capability
from wrasc import ppmac_ra as ppra

# take the specific collection of agents/tasks in the specific test class
from examples.motion_tests_ra import SgPhiM5Agents

# this is used for yaml loading
import utils
from os import path

separation_line = "\n***********************\n\n"

# load test settings from yaml file
tst = utils.undump_obj(
    "sg_m5_repeat", path.join(path.dirname(path.abspath(__file__)), "autest_in")
)
# setup the collection of test agents (tasks) in the specific class
outpath = path.join(path.dirname(path.abspath(__file__)), "sg_out")
sg_test = SgPhiM5Agents(_VERBOSE_=tst["verbose_level"], tst=tst, out_path=outpath)

# process and compile agents dependencies
agents = ppra.ra.compile_n_install({}, globals().copy(), "ARBITRARY")

print(separation_line, "Starting the sequence...")

iters = 0
while iters < tst["loop_repeats"]:
    print(f"\niteration: {iters} ")

    # TODO see why this doesn't work!!!!
    sg_test.jog_rel_ag.setup(cry_cmds=["#{L1}jog:{jog_size_mu}"])

    ppra.do_ags(
        [sg_test.jog_rel_ag, sg_test.until_not_moving_ag],
        all_done=False,
        cycle_period=tst["wrasc_cycle_period"],
    )

    # if jog is not successful (InPos) then terminate
    if not sg_test.jog_rel_ag.is_done:
        print(
            f"\n\nExiting due to unsuccessful jog at iteration {iters}",
            end=separation_line,
        )
        exit(1)

    iters += 1


print("\n\nSequence is finished successfully.", end=separation_line)
