from wrasc import reactive_agent as ra
from ppmac import GpasciiClient
from timeit import default_timer as timer
from time import sleep
import re
from io import StringIO
import csv

""" ppmac basic agent. 
This agent checks (watches) a list of statement conditions, 
and triggeres (acts) a triple list of actions. accordingly.

These have no retry or timeout mechanism internally. Some specialised agents can take care of progress and deadlocks



"""

macrostrs = ["{", "}"]


def assert_pos_wf(xx: int, pos, tol):
    """

    retuns 
    1 - assert condition for motor xx at resting at position pos+_tol
    2 - default jog statement to move the motor there if not already there

    """
    if isinstance(pos, str) or isinstance(tol, str):
        tol = str(tol)
        pos = str(pos)
        pos_hi = f"{pos} + {tol}"
        pos_lo = f"{pos} - {tol}"
        target_pos = macrostrs[0] + pos + macrostrs[1]
    else:
        pos_hi = pos + tol
        pos_lo = pos - tol
        target_pos = pos
    return (
        [
            f"#{xx}p < {pos_hi}",
            f"#{xx}p > {pos_lo}",
            f"Motor[{xx}].DesVelZero==1",
            f"Motor[{xx}].InPos==1",
            f"Motor[{xx}].MinusLimit + Motor[{xx}].PlusLimit == 0",
        ],
        [f"#{xx}j={target_pos}"],
    )


def isPmacNumber(s: str):

    if s.startswith("$"):
        # check if it is a valid hex
        try:
            int(s[1:], 16)
        except ValueError:
            return False
        else:
            return True
    else:
        # check if it is a valid decimal
        return (
            s.replace("e-", "")
            .replace("e+", "")
            .lstrip("+-")
            .replace(".", "", 1)
            .isdigit()
        )


def parse_vars(any_side: str):

    # parse right or left soides of equation
    # to parametrised temlate and list of vars

    all_vars = []
    # any_side: no change if it is a ppmacnumber, or an address
    if not (isPmacNumber(any_side) or any_side.endswith(".a")):
        # there is at least a variable on the right,
        # which needs to be evaluated.
        for v in re.split(r"[\+\-\*\/=><! ]", any_side):
            if v and not isPmacNumber(v):
                all_vars.append(v)
                vars_index = len(all_vars) - 1
                any_side = any_side.replace(v, f"_var_{vars_index}")

    return any_side, all_vars


def validate_cmds(cmds):

    if cmds is None:
        return None

    if isinstance(cmds, str):
        return cmds
    elif isinstance(cmds, list):
        # convert list to one string of lines
        return "\n".join(cmds)
    else:
        raise RuntimeError(f"bad command: {cmds}")


def pars_conds(conds_list):

    # makes a list of variables on the watchlist which need to be fetched and relpaced with real-time values, real time.

    if conds_list is None:
        return []

    # make sure "verifies" is a list
    if isinstance(conds_list, str):
        conds_list = [conds_list]

    parsed_conds = list()
    # there are conditions to check.
    for cond in conds_list:
        assert isinstance(cond, str)

        l_template, l_vars = parse_vars(cond)
        parsed_conds.append([l_template, l_vars, cond])

    return parsed_conds


def ppwr_poll_pr(ag_self: ra.Agent):
    """ 
    these are "steged agents" meaning theyt are being inhibited by stage progress
    
    """


def ppwr_poll_in(ag_self: ra.Agent):

    # TODO: it is tricky here as a continuous poll is not always desired?
    if not ag_self.verifies or len(ag_self.verifies) < 1:
        ag_self.poll.Var = True
        return ra.StateLogics.Valid, "no checks"

    # acquire left sides

    for condition in ag_self.verifies:
        # take templates and variables from inside the
        # condisions and verify the statement

        verify_text, statement = ag_self.check_cond(condition)

        if verify_text is None:
            return ra.StateLogics.Invalid, "comms error"

        if eval(verify_text) == False:
            return False, f"False: {statement} "

    # now that it is going to be True, calculate the logs:

    vals = [ag_self.poll.Time]
    for condition in ag_self.log_stats:
        # take templates and variables from inside the
        # condisions and verify the statement

        verify_text, statement = ag_self.check_cond(condition)

        if verify_text:
            # store eval(verify_text) in the logs dict:
            vals.append(eval(verify_text))
    if len(vals) > 1:
        # ag_self.log_vals.append(vals)
        # ag_self.writer.writerow(vals)
        ag_self.csvcontent += ",".join(map(str, vals)) + "\n"

    return True, "True"


def ppwr_act_on_valid(ag_self: ra.Agent):
    """
    The best act here is to Arm when an action is known.
    Because there are two different actions are known here, it is best to reset the
    act status to idle whenever the poll status is changed.
    """

    # Arm for action if poll is changed to False or True
    if ag_self.poll.Var == True:

        # if already celebrated
        if ag_self.poll.is_on_hold():
            return ra.StateLogics.Done, f"Done."
        else:
            if ag_self.celeb_cmds:
                resp = ag_self.ppmac.send_receive_raw(
                    ag_self.expand_cmd_str(ag_self.celeb_cmds)
                )
            else:
                resp = ""

            # stop checking the condition. Stage is now passed.
            ag_self.poll.hold(for_cycles=-1, reset_var=False)

            # now log a line to cvs if there is one
            if ag_self.csvcontent and ag_self.csv_file_name:
                with open(ag_self.csv_file_name, "w+") as file:
                    file.write(ag_self.csvcontent)
                ag_self.cvscontent = None

            return ra.StateLogics.Done, f"Hooray: {resp}"

    elif ag_self.poll.Var == False:

        # condition is not met, so the we need to keep checking, and probably sending a fixer action
        # check how many times this is repeated
        # this is a way of managing reties:
        # once the agent gets armed, it will not be released until externally poked back?

        if ag_self.poll.NoChangeCount > 1:
            return ra.StateLogics.Idle, "Retries exhausted"

        if ag_self.cry_cmds:
            resp = ag_self.ppmac.send_receive_raw(
                ag_self.expand_cmd_str(ag_self.cry_cmds)
            )
            return ra.StateLogics.Idle, "Fix action"

        return ra.StateLogics.Idle, "No action !!!"


def ppwr_act_on_invalid(ag_self: ra.Agent):
    if ag_self.fetch_cmds:
        ag_self.ppmac.send_receive_raw(ag_self.expand_cmd_str(ag_self.fetch_cmds))
    return ra.StateLogics.Idle, "reacted to invalid"


class Conditions(object):
    def __init__(self, value=None):
        self.value = pars_conds(value)

    def __get__(self, instance, owner):
        return self.value

    def __set__(self, instance, value):
        self.value = pars_conds(value)


class WrascPpmac(ra.Agent):

    ppmac = ...  # type : GpasciiClient

    def __init__(
        self,
        ppmac: GpasciiClient = None,
        fetch_cmds=None,
        verifiy_stats=None,
        cry_cmds=None,
        celeb_cmds=None,
        pass_logs=None,
        csv_file_name=None,
        **kwargs,
    ):

        if not ppmac or (not isinstance(ppmac, GpasciiClient)):
            self.dmAgentType = "uninitialised"
            return

        self.verifies = pars_conds(verifiy_stats)
        # log_stats need to be fetched with verifies, stored, and logged at celeb.
        self.log_stats = pars_conds(pass_logs)
        self.csv_file_name = csv_file_name

        # setup the headers, they get written when (and only if) the first set of readings are ready
        if self.log_stats:
            headers = ["Time"] + list(list(zip(*self.log_stats))[2])
            # self.log_vals = headers
            # self.writer.writerow(headers)
            self.csvcontent = ",".join(map(str, headers)) + "\n"
        else:
            # self.log_vals = []
            self.csvcontent = None

        self.celeb_cmds = validate_cmds(celeb_cmds)
        self.cry_cmds = validate_cmds(cry_cmds)
        self.fetch_cmds = validate_cmds(fetch_cmds)

        self.ppmac = ppmac

        if not self.ppmac.connected:
            self.ppmac.connect()
            time_0 = timer()
            time_out = 2  # sec

            while not self.ppmac.connected:

                if timer() < time_0 + time_out:
                    raise TimeoutError(
                        f"GpasciiClient connection timeout: {self.ppmac.host}"
                    )
                sleep(0.1)

        # if you are here, then we have an agent to intialise

        super().__init__(
            poll_in=ppwr_poll_in,
            act_on_invalid=ppwr_act_on_invalid,
            act_on_valid=ppwr_act_on_valid,
            **kwargs,
        )
        self.dmAgentType = "ppmac_wrasc"
        # compile statement lists

    def setup(self, **kwargs):
        super().setup(**kwargs)

    def expand_cmd_str(self, cmds_str):

        # expand {} macros with actual values from ppmac

        macro_list = re.findall(f"(?:{macrostrs[0]})(.*?)(?:{macrostrs[1]})", cmds_str)

        for condition in pars_conds(macro_list):

            l_template, statement = self.check_cond(condition)

            if l_template is None:
                raise RuntimeError(f"comms with ppmac at {self.ppmac.host}")

            rt_val = eval(l_template)
            replace = macrostrs[0] + statement + macrostrs[1]
            cmds_str = cmds_str.replace(f"{replace}", f"{rt_val}")

        return cmds_str

    def check_cond(self, condition):

        l_template, l_vars, statement = condition

        for i, l_var in enumerate(l_vars):
            # acquire the variable to check
            tpl = self.ppmac.send_receive_raw(l_var)

            if not tpl[1]:
                self.poll.Var = None
                l_template = None
                break
                # return ra.StateLogics.Invalid, "comms error"

            l_template = l_template.replace(
                f"_var_{i}", tpl[0][1].strip("\n").strip(" ").split("=")[-1]
            )

        return l_template, statement


# -------------------------------------------------------------------
def done_condition_poi(ag_self: ra.Agent):

    # check "done" condition.
    # set the sequence by setting the prohibits
    # this agent remains invalid until the process is all done
    # and then uses

    all_stages_passed = ag_self.last_layer_dependency_ag.poll.Var

    if not all_stages_passed:
        return None, "last stage not passed..."

    for agname in ag_self.agent_list:
        ag = ag_self.agent_list[agname]["agent"]
        assert isinstance(ag, ra.Agent)

        # only reset ags which are below this control agent
        if ag.layer >= ag_self.layer:
            continue

        all_stages_passed = all_stages_passed and ag.poll.Var

    if not all_stages_passed:
        return None, "prev stages not passed..."

    # all done. Now decide based on a counrter to either quit or reset and repeat
    if ag_self.repeats > 0:
        ag_self.repeats -= 1
        return False, f"Resetting the loop, {ag_self.repeats} to go"
    else:
        return True, "Quitting..."


def arm_to_quit_aov(ag_self: ra.Agent):
    if ag_self.poll.Var == True:
        # inform and log, confirm with other agents...
        return ra.StateLogics.Armed, "quitting..."
    elif ag_self.poll.Var == False:
        # action: invalidate all agents in this subs-stage,
        # so the cycle restart
        for agname in ag_self.agent_list:
            ag = ag_self.agent_list[agname]["agent"]
            assert isinstance(ag, ra.Agent)

            # only reset ags which are below this control agent
            if ag.layer >= ag_self.layer:
                continue

            ag.poll.force(None, immediate=False)

        return ra.StateLogics.Idle, "all ags reset..."


def quit_act_aoa(ag_self: ra.Agent):

    if ag_self.poll.Var:
        return ra.StateLogics.Done, "RA_QUIT"
    else:
        return ra.StateLogics.Idle, "RA_WHATEVER"


class WrascSequencer(ra.Agent):
    def __init__(
        self,
        poll_in=done_condition_poi,
        act_on_valid=arm_to_quit_aov,
        act_on_armed=quit_act_aoa,
        **kwargs,
    ):

        super().__init__(
            poll_in=poll_in,
            act_on_valid=act_on_valid,
            act_on_armed=act_on_armed,
            **kwargs,
        )

        self.dmAgentType = "sequencer_wrasc"


class PpmacMotorShell(object):
    """This class simply provides a way to access ppmac Motor structure using python objects.

    At run-time, the engine investigates its own members and poupulate them with corresponding values from ppmac.
    Care shall be taken not to make any variables with worng names until a pre-validation is added.

    Args:
        object ([type]): [description]
    """


if __name__ == "__main__":
    pass
