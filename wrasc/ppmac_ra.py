from wrasc import reactive_agent as ra
from ppmac import GpasciiClient
from timeit import default_timer as timer
from time import sleep
import re
from io import StringIO
import csv
import os
import time

""" ppmac basic agent. 
This agent checks (watches) a list of statement conditions, 
and triggeres (acts) a triple list of actions. accordingly.

These have no retry or timeout mechanism internally. Some specialised agents can take care of progress and deadlocks



"""

macrostrs = ["{", "}"]

ppmac_func_dict = {"EXP2": "2**"}


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


def isPmacPointer(s: str):
    return (len(s) > 3 and s.lower()[-2:] == ".a") or (s.lower() == "sys.pushm")


def isPmacFunction(s: str):

    if s in ppmac_func_dict:
        return ppmac_func_dict[s]

    return False


def parse_vars(stat: str):

    # parse right or left soides of equation
    # to parametrised temlate and list of vars

    # pass_conds = [
    #     f"isclose( {cond.split('=')[0]}, {cond.split('=')[1]}, abs_tol=1e05)"
    #     for cond in cry_cmds
    # ]

    # sub macros here?

    all_vars = []
    # any_side: no change if it is a ppmacnumber, or an address

    for v in re.split(r"[\+\-\*\/=><! \(\)]", stat):
        if v and not isPmacNumber(v):

            if isPmacPointer(v):  # this is a pointer, treat this as quoted text
                stat = stat.replace(v, f"'{v}'")
                continue

            pyfunc = isPmacFunction(v)
            if pyfunc:  # this is a function, replace with python equivalent
                stat = stat.replace(v, pyfunc)
                continue

            all_vars.append(v)
            vars_index = len(all_vars) - 1
            stat = stat.replace(v, f"_var_{vars_index}")
        elif v.startswith("$"):
            # is a valid hex, replace with its decimal value
            stat = stat.replace(v, str(int(v[1:], 16)))

    # purge spaces (and other white spaces)

    return stat.replace(" ", ""), all_vars


def parse_cmds(cmds):

    if cmds is None:
        return None

    if isinstance(cmds, str):
        cmds = [cmds]

    if not isinstance(cmds, list):
        raise RuntimeError(f"bad command: {cmds}")

    # convert list to one string of lines
    cmds_out = []
    for cmd in cmds:
        # separate right and left side
        # need to add all possible online comands here too: "^:*" ?
        cmd_split = cmd.split("=")
        cmd_left = cmd_split[0]
        if len(cmd_split) > 1:
            # in case of jog==45 , right side would be
            cmd_right = cmd_split[-1]
            if (not isPmacNumber(cmd_right)) and any(i in cmd_right for i in "+-*/^"):
                # right side is ILLEGAL as a ppmac online command. Mark it as a macro for late evaluation
                cmd_right = macrostrs[0] + cmd_right + macrostrs[1]

            cmds_out.append(f"{cmd_left}={cmd_right}")
        else:
            cmds_out.append(cmd)

    return "\n".join(cmds_out)


def pars_conds(conds_list):

    # makes a list of variables on the watchlist which need to be fetched and relpaced with real-time values, real time.

    if conds_list is None:
        return []

    # make sure "pass_conds_parsed" is a list
    if isinstance(conds_list, str):
        conds_list = [conds_list]

    parsed_conds = list()
    # there are conditions to check.
    for cond in conds_list:
        assert isinstance(cond, str)
        # romve spaces to make the output predictable
        cond = cond.replace(" ", "")
        if not cond:
            continue

        l_template, l_vars = parse_vars(cond)
        parsed_conds.append([l_template, l_vars, cond])

    return parsed_conds


def expand_pmac_stats(stats, **vars):

    # this function expands the ppmac statements for the channel parmeters
    # parameters shall be in the form of L1 ... L10 or {whatever}
    # all of the variables shall be supplies via **vars
    #
    # this allows to scale the templates for different channel configuration

    # first, some type checking

    if not stats:
        return stats

    if isinstance(stats, str):
        stats = [stats]

    assert isinstance(stats, list)

    stats_out = []
    # expand the stats one by one
    for stat in stats:
        assert isinstance(stat, str)

        # ignore line comments
        if stat.lstrip().startswith("//"):
            continue

        # support base L# format by reverting L# to {L#}
        stat = re.sub(r"(\[)(?=L\d)", "[{", stat)
        stat = re.sub(r"(?<=L\d)(\])", "}]", stat)

        try:
            stats_out.append(stat.format(**vars))
        except KeyError:
            # if there is a macro which can't be found in vars, then leave it!
            stats_out.append(stat)
        except ValueError:
            # this is probably more serious...
            stats_out.append(stat)
        except IndexError:
            # this is probably a syntax issue,
            # e.g. something other than a variable is passed as a macro
            # e.g. {0.2} is passed
            # raise RuntimeError(f"syntax error in ppmac statement: {stat} ")

            stats_out.append(stat)

    return stats_out


def ppwr_poll_in(ag_self: ra.Agent):

    assert isinstance(ag_self, WrascPmacGate)
    ag_self: WrascPmacGate

    # TODO: it is tricky here as a continuous poll is not always desired?
    if not ag_self.pass_conds_parsed or len(ag_self.pass_conds_parsed) < 1:
        ag_self.poll.Var = True
        return ra.StateLogics.Valid, "no checks"

    # acquire left sides

    for condition in ag_self.pass_conds_parsed:
        # take templates and variables from inside the
        # condisions and verify the statement

        verify_text, statement = ag_self.check_cond(condition)

        if verify_text is None:
            return ra.StateLogics.Invalid, "comms error"

        one_sided_verify_text = verify_text.replace("==", " - (") + ")"

        # TODO improve this, the whole scheme shall bwork on a numpy is_close instead of isequal:
        # depending on the lvar, round off or not!
        left_side = condition[1][0]
        qual = left_side.lower().split(".")[-1]
        if qual.endswith("speed"):
            _precision = 1e-6
        elif qual.endswith("gain"):
            _precision = 1.0e-7
        elif qual.endswith("pwmsf"):
            _precision = 1  # probably wrong
        elif qual.endswith("maxint"):
            _precision = 0.0625
        else:
            _precision = 1e-16

        try:
            if abs(eval(one_sided_verify_text)) > _precision:
                # if eval(verify_text) == False:
                # no need to check the rest of the conditions
                return (
                    False,
                    f"No pass - {statement}: {one_sided_verify_text} > {_precision}",
                )
        except:
            # arithmentic error, check literal statement
            if eval(verify_text) == False:
                # no need to check the rest of the conditions
                return False, f"No Pass - {statement}: {verify_text} "

    # now that it is going to be True, calculate the logs.
    # they will be saved to file via actions:

    vals = [ag_self.poll.Time]
    for condition in ag_self.pass_logs_parsed:
        # acquire log statements
        verify_text, statement = ag_self.check_cond(condition)

        if verify_text:
            # store eval(verify_text) in the logs dict:
            if isPmacNumber(verify_text):
                vals.append(eval(verify_text))
            else:
                # text value
                vals.append(verify_text)
    if len(vals) > 1:
        ag_self.csvcontent += ",".join(map(str, vals)) + "\n"

    return True, "True"


def ppwr_act_on_valid(ag_self: ra.Agent):
    """
    The best act here is to Arm when an action is known.
    Because there are two different actions are known here, it is best to reset the
    act status to idle whenever the poll status is changed.

    This will ARM if an act_on_armed method is defined. This is for users to hook their custom methods
    """

    assert isinstance(ag_self, WrascPmacGate)
    ag_self: WrascPmacGate

    # Arm for action if poll is changed to False or True
    if ag_self.poll.Var == True:

        # if already put on hold
        if ag_self.poll.is_on_hold():
            return ra.StateLogics.Done, f"Done."

        # do celeb commands if they exist
        if ag_self.celeb_cmds_parsed:
            resp = ag_self.ppmac.send_receive_raw(
                ag_self.eval_cmd(ag_self.celeb_cmds_parsed)
            )
        else:
            resp = ""

        # if this is a staged-pass then
        # stop checking the condition. Stage is now passed.
        # this will also trigger transition to Done state the next cycle.
        if not ag_self.ongoing:
            ag_self.poll.hold(for_cycles=-1, reset_var=False)
            # TODO Remove this test code
            ag_self.act.hold(for_cycles=1, reset_var=False)

        # now log a line to cvs if there is one
        if ag_self.csvcontent and ag_self.csv_file_name:

            with open(ag_self.csv_file_name, "w+") as file:
                file.write(ag_self.csvcontent)
            ag_self.cvscontent = None

        # arm if an arm action is defined (by user). Otherwise Done
        if ag_self.act_on_armed:
            return (
                ra.StateLogics.Armed,
                f"passing to external aoa: {resp}",
            )

        return ra.StateLogics.Done, f"celeb: {resp}"

    elif ag_self.poll.Var == False:

        # condition is not met, so the we need to keep checking, and probably sending a fixer action
        # check how many times this is repeated
        # this is a way of managing reties:
        # once the agent gets armed, it will not be released until externally poked back?

        if ag_self.cry_cmds_parsed:

            if ag_self.cry_tries >= ag_self.cry_retries:
                return (
                    ra.StateLogics.Idle,
                    f"retries exhausted {ag_self.cry_tries}/{ag_self.cry_retries}",
                )

            ag_self.cry_tries = ag_self.cry_tries + 1
            resp = ag_self.ppmac.send_receive_raw(
                ag_self.eval_cmd(ag_self.cry_cmds_parsed)
            )
            return (
                ra.StateLogics.Idle,
                f"Fix action {ag_self.cry_tries}/{ag_self.cry_retries}",
            )

        return ra.StateLogics.Idle, "No action"


def ppwr_act_on_invalid(ag_self: ra.Agent):

    assert isinstance(ag_self, WrascPmacGate)
    ag_self: WrascPmacGate

    ag_self.cry_tries = 0

    if ag_self.fetch_cmds_parsed:
        ag_self.ppmac.send_receive_raw(ag_self.eval_cmd(ag_self.fetch_cmds_parsed))
    return ra.StateLogics.Idle, "reacted to invalid"


def normalise_header(_header):

    _header = re.sub(r"[\.]", "_", _header)
    _header = re.sub(r"[[\]]", "", _header)
    _header = re.sub(r"[(\)]", "", _header)
    _header = re.sub(r"Motor", "M", _header)
    _header = re.sub(r"(?<=#\d)(p)", "_HashPos", _header)
    _header = re.sub(r"(?<=#\d\d)(p)", "_HashPos", _header)
    _header = re.sub(r"(#)(?=\d+)", "A", _header)
    _header = re.sub(r"(#)(?=\d\d)", "A", _header)

    return _header


class Conditions(object):
    def __init__(self, value=None):
        self.value = pars_conds(value)

    def __get__(self, instance, owner):
        return self.value

    def __set__(self, instance, value):
        self.value = pars_conds(value)


class WrascPmacGate(ra.Agent):

    ppmac = ...  # type : GpasciiClient

    fetch_cmds = ...  # type : list
    fetch_cmd_parsed = ...  # type : str
    cry_cmds = ...  # type : list
    cry_cmd_parsed = ...  # type : str
    celeb_cmds = ...  # type : list
    celeb_cmd_parsed = ...  # type : str

    pass_cond = ...  # type : list
    pass_cond_parsed = ...  # type : list

    pass_logs = ...  # type : list
    pass_logs_parsed = ...  # type : list

    ongoing = ...  # type : bool

    def __init__(
        self,
        ppmac: GpasciiClient = None,
        fetch_cmds=[],
        pass_conds=[],
        cry_cmds=[],
        cry_retries=1,
        celeb_cmds=[],
        pass_logs=[],
        csv_file_name=None,
        **kwargs,
    ):
        self.pp_globals = {}

        self.ongoing = False

        self.fetch_cmds = []
        self.pass_conds = []
        self.cry_cmds = []
        self.cry_retries = 1
        self.cry_tries = 0
        self.celeb_cmds = []
        self.pass_logs = []

        if not ppmac or (not isinstance(ppmac, GpasciiClient)):
            self.dmAgentType = "uninitialised"
            return

        self.ppmac = ppmac  # type : GpasciiClient

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

        self.pass_logs_parsed = []
        self.csv_file_name = None
        # if you are here, then we have an agent to intialise

        super().__init__(
            poll_in=ppwr_poll_in,
            act_on_invalid=ppwr_act_on_invalid,
            act_on_valid=ppwr_act_on_valid,
            fetch_cmds=fetch_cmds,
            pass_conds=pass_conds,
            cry_cmds=cry_cmds,
            cry_retries=cry_retries,
            celeb_cmds=celeb_cmds,
            pass_logs=pass_logs,
            csv_file_name=csv_file_name,
            **kwargs,
        )
        self.dmAgentType = "ppmac_wrasc"

    def setup(
        self,
        fetch_cmds=None,
        pass_conds=None,
        cry_cmds=None,
        cry_retries=None,
        celeb_cmds=None,
        pass_logs=None,
        csv_file_name=None,
        ongoing=None,
        **kwargs,
    ):

        if ongoing:
            self.ongoing = ongoing

        # every one of cmds and conds pass this point,
        # so its best to esxpand them here

        self.pass_conds = expand_pmac_stats(
            pass_conds if pass_conds else self.pass_conds, **kwargs
        )
        self.pass_conds_parsed = pars_conds(self.pass_conds)

        # pass_logs_parsed need to be fetched with pass_conds_parsed, stored, and logged at celeb.
        self.pass_logs = expand_pmac_stats(
            pass_logs if pass_logs else self.pass_logs, **kwargs
        )
        self.pass_logs_parsed = pars_conds(self.pass_logs)

        if csv_file_name:
            self.csv_file_name = csv_file_name

        # setup the headers, they get written when (and only if) the first set of readings are ready
        if self.pass_logs_parsed:
            headers = ["Time"] + list(list(zip(*self.pass_logs_parsed))[2])
            # remove and reshape special caharacters headers

            headers = [normalise_header(header) for header in headers]

            self.csvcontent = ",".join(map(str, headers)) + "\n"

            if self.csvcontent and self.csv_file_name:

                # if file exists, make a backup of the existing file
                # do not leave until the file doesn't exist!
                n_copies = 0
                while os.path.exists(self.csv_file_name):
                    name, ext = os.path.splitext(self.csv_file_name)
                    modif_time_str = time.strftime(
                        "%y%m%d_%H%M",
                        time.localtime(os.path.getmtime(self.csv_file_name)),
                    )
                    n_copies_str = f"({n_copies})" if n_copies > 0 else ""
                    try:
                        os.rename(
                            self.csv_file_name,
                            f"{name}_{modif_time_str}{n_copies_str}{ext}",
                        )
                    except FileExistsError:
                        # forget it... the file is already archived...
                        # TODO or you need to be too fussy and break the execution for this?
                        n_copies += 1

                open(self.csv_file_name, "w+")
        else:
            # self.log_vals = []
            self.csvcontent = None

        self.fetch_cmds = expand_pmac_stats(
            fetch_cmds if fetch_cmds else self.fetch_cmds, **kwargs
        )
        self.fetch_cmds_parsed = parse_cmds(self.fetch_cmds)

        self.cry_cmds = expand_pmac_stats(
            cry_cmds if cry_cmds else self.cry_cmds, **kwargs
        )
        self.cry_cmds_parsed = parse_cmds(self.cry_cmds)

        self.celeb_cmds = expand_pmac_stats(
            celeb_cmds if celeb_cmds else self.celeb_cmds, **kwargs
        )
        self.celeb_cmds_parsed = parse_cmds(self.celeb_cmds)

        if cry_retries:
            self.cry_retries = cry_retries

        # TODO change this crap[ solution
        # floating digits used for == comparison
        self.ndigits = 6

        super().setup(**kwargs)

    def eval_cmd(self, cmds_str):

        # evaluate {} macros with actual values from ppmac
        # this is done at the very late stage i.e. as late as possible.
        # As opposed to this one,

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
                l_template = "Err"
                break
                # return ra.StateLogics.Invalid, "comms error"

            ret_val = tpl[0][1].strip("\n").strip(" ").strip("'").split("=")[-1]

            if not isPmacNumber(ret_val):
                # treat this return as string
                ret_val = f"'{ret_val}'"

            elif ret_val.startswith("$"):
                # check if it is a valid hex
                ret_val = str(int(ret_val[1:], 16))

            l_template = l_template.replace(f"_var_{i}", ret_val)
        # ppmac is a non case sensitive system, so return comparison statement in lower case
        return l_template.lower(), statement

    @property
    def is_done(self):

        if self.ongoing or self.act.Var:
            return True
        else:
            return False


# -------------------------------------------------------------------
def done_condition_poi(ag_self: ra.Agent):

    # check "done" condition.
    # set the sequence by setting the prohibits
    # this agent remains invalid until the process is all done
    # and then uses

    assert isinstance(ag_self, WrascRepeatUntil)
    ag_self: WrascRepeatUntil

    all_stages_passed = ag_self.all_done_ag.is_done  # poll.Var

    if not all_stages_passed:
        return None, "last stage not passed..."

    for agname in ag_self.agent_list:
        ag = ag_self.agent_list[agname]["agent"]  # type : ra.Agent
        assert isinstance(ag, ra.Agent)

        # only reset ags which are below this control agent
        if ag.layer >= ag_self.layer:
            continue

        all_stages_passed = all_stages_passed and ag.is_done  # ag.poll.Var

    if not all_stages_passed:
        return None, "prev stages not passed..."

    # all done. Now decide based on a counrter to either quit or reset and repeat
    if ag_self.repeats > 0:
        return False, f"Resetting the loop"
    else:
        return True, "loop exhausted..."


def arm_to_quit_aov(ag_self: ra.Agent):

    assert isinstance(ag_self, WrascRepeatUntil)
    ag_self: WrascRepeatUntil

    if ag_self.poll.Var == True:
        # inform and log, confirm with other agents...
        return ra.StateLogics.Armed, "out."
    elif ag_self.poll.Var == False:
        # action: invalidate all agents in this subs-stage,
        # so the cycle restart
        for ag in ag_self.reset_these_ags:

            assert isinstance(ag, ra.Agent)

            # only reset ags which are below this control agent

            ag.poll.force(None, immediate=False)
            ag.act.force(None, immediate=True)

        ag_self.repeats -= 1

        return ra.StateLogics.Valid, f"{ag_self.repeats + 1} to go"


def quit_act_aoa(ag_self: ra.Agent):

    assert isinstance(ag_self, WrascRepeatUntil)
    ag_self: WrascRepeatUntil

    if not ag_self.quit_if_done:
        ag_self.repeats = 30
        ag_self.poll.force(None, immediate=False)
        ag_self.act.force(None, immediate=True)
        return ra.StateLogics.Done, "RA_WHATEVER"

    if ag_self.poll.Var:
        return ra.StateLogics.Done, "RA_QUIT"
    else:
        return ra.StateLogics.Idle, "RA_WHATEVER"


class WrascRepeatUntil(ra.Agent):
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

        self.all_done_ag = None
        self.reset_these_ags = []
        self.quit_if_done = True
        self.repeats = 0


default_asic = lambda axis: (axis - 1) // 4
default_chan = lambda axis: (axis - 1) % 4
default_companion = lambda axis: axis + 8


def default_asic_chan(axis):
    return (axis - 1) // 4, (axis - 1) % 4


class axis:
    def __init__(self, amp_number, **kwargs):
        super().__init__()

        self.motor_n = amp_number
        self.prim_asic, self.prim_chan = default_asic_chan(self.motor_n)

        self.second_asic = self.prim_asic
        self.second_chan = self.prim_chan

        self.companion_axis = default_companion(self.motor_n)

        self.setup(**kwargs)

    def setup(self, JogSpeed=None):

        if JogSpeed:
            self.JogSpeed = JogSpeed

    def LVars(self):

        return {
            "L1": self.motor_n,
            "L2": self.prim_asic,
            "L3": self.prim_chan,
            "L4": self.second_asic,
            "L5": self.second_chan,
            # 0 basis motor used in BroickLV structure e.g. BrickLV.Chan[L6].TwoPhaseMode=1
            "L6": self.motor_n - 1,
            # companion axis
            "L7": self.companion_axis,
        }

    def expand_stats(self, stats):
        return expand_pmac_stats(stats, **self.LVars())


class PpmacMotorShell(object):
    """This class simply provides a way to access ppmac Motor structure using python objects.

    At run-time, the engine investigates its own members and poupulate them with corresponding values from ppmac.
    Care shall be taken not to make any variables with worng names until a pre-validation is added.

    Args:
        object ([type]): [description]
    """


if __name__ == "__main__":
    pass
