from pandas.core.indexes.base import Index
from wrasc import reactive_agent as ra
from ppmac import GpasciiClient
from ppmac import PpmacToolMt


from timeit import default_timer as timer
from time import sleep
import re
from io import StringIO
import csv
import os
import time
import utils
from fractions import Fraction
from utils.pputils import *

""" ppmac basic agent. 
This agent checks (watches) a list of statement conditions, 
and triggeres (acts) a triple list of actions. accordingly.

These have no retry or timeout mechanism internally. Some specialised agents can take care of progress and deadlocks

Sequence:

poll, 
    do cry_cmds for recry times

if pass, 
    do celeb_cmds
then skip one cycle 
then skip more cycles until wait_after_celeb, if defined
then log if defined
and set id_done.

"""


def ppwr_poll_in(ag_self: ra.Agent):

    assert isinstance(ag_self, WrascPmacGate)
    ag_self: WrascPmacGate

    # if the agent is just came out of inhibit, then reset all retries!
    if not ag_self.act_on:
        if ag_self.cry_tries != 0:
            ag_self.cry_tries = 0

    # TODO: it is tricky here as a continuous poll is not always desired?

    # if there are no conditions to check, then it is a pass
    if not ag_self.pass_conds_parsed or len(ag_self.pass_conds_parsed) < 1:
        return ra.StateLogics.Valid, "no checks"

    # acquire left sides
    # TODO optimise this routine by:
    # sending all stats at once
    # and then processing the conditions one by one ... ?

    # TODO: add the capability of cry_before_check
    # to action cry_act, for pre_acts times before checking the conditions
    # conds shall return False before pre_tries are exhausted

    if ag_self.cry_tries < ag_self.cry_pretries:
        return False, "pre-tries not exhasuted, skiped checking conds."

    ag_self.receive_cond_parsed(ag_self.pass_conds_parsed)

    return ag_self.check_pass_conds()


def ppwr_act_on_valid(ag_self: ra.Agent):
    """
    user action can be injected here 
    """

    if ag_self.log_while_waiting and ag_self.pass_logs_parsed:
        ag_self.acquire_log()
        try:
            ag_self.log_to_file()
        except:
            raise RuntimeError(f"{ag_self.name}: writing log to file")

    assert isinstance(ag_self, WrascPmacGate)
    ag_self: WrascPmacGate

    if ag_self.poll.is_on_hold():
        return ra.StateLogics.Done, f"Done."

    # Arm for action if poll is changed to False or True
    if ag_self.poll.Var == True:
        return ag_self.celeb_act()

    elif ag_self.poll.Var == False:

        return ag_self.cry_act()
    else:
        return ra.StateLogics.Idle, "Invalid State"


def ppwr_act_on_armed(ag_self: ra.Agent):

    if ag_self.wait_after_celeb:
        elapsed = ra.timer() - ag_self.poll.ChangeTime
        if elapsed < ag_self.wait_after_celeb:
            return (
                ra.StateLogics.Armed,
                f"waiting {elapsed:.2f}/{ag_self.wait_after_celeb}sec",
            )
        else:
            # need to flick a deliberate change here, to reset the timer!
            ag_self.poll.ChangeTime = ra.timer()

    if ag_self.pass_logs_parsed:
        ag_self.acquire_log()
        try:
            ag_self.log_to_file()
        except:
            raise RuntimeError(f"{ag_self.name}: writing log to file")

    return ra.StateLogics.Done, "Done, act on hold."


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
    _header = re.sub(r"(?<=#\d)(p)", "_Pos", _header)
    _header = re.sub(r"(?<=#\d\d)(p)", "_Pos", _header)
    _header = re.sub(r"(?<=#\d)(v)", "_Vel", _header)
    _header = re.sub(r"(?<=#\d\d)(v)", "_Vel", _header)
    _header = re.sub(r"(?<=#\d)(f)", "_FE", _header)
    _header = re.sub(r"(?<=#\d\d)(f)", "_FE", _header)
    _header = re.sub(r"(?<=#\d)(d)", "_DesiredPos", _header)
    _header = re.sub(r"(?<=#\d\d)(d)", "_DesiredPos", _header)
    _header = re.sub(r"(?<=#\d)(t)", "_TargetPos", _header)
    _header = re.sub(r"(?<=#\d\d)(t)", "_TargetPos", _header)
    _header = re.sub(r"(?<=#\d)(g)", "_DistToGo", _header)
    _header = re.sub(r"(?<=#\d\d)(g)", "_DistToGo", _header)
    _header = re.sub(r"(#)(?=\d+)", "A", _header)
    _header = re.sub(r"(#)(?=\d\d)", "A", _header)

    return _header


class Conditions(object):
    def __init__(self, value=None):
        self.value = parse_stats(value)

    def __get__(self, instance, owner):
        return self.value

    def __set__(self, instance, value):
        self.value = parse_stats(value)


class PPMAC:
    """Adapter for different gpascii drivers
    only two base functions are provided:
    connect 
    send_receive_raw

    Args:
        backward (bool): sets the driver to use the ultra slow but backward compatible PpmacToolMt
        host (str): url
    """

    def __init__(self, host, debug=False, backward=False) -> None:

        self.host = host

        if not backward:
            self.gpascii = GpasciiClient(host=self.host, debug=debug)
        else:
            self.gpascii = PpmacToolMt(host=self.host)

        self.connected = False

    def connect(self):
        self.gpascii.connect()
        self.connected = self.gpascii.connected

    def send_receive_raw(self, command, timeout=5):
        """send and then receive a series of commands in sequence

        Args:
            command (str): \n separated string of commands
            timeout (int, optional): [description]. Defaults to 5.

        Returns:
            [type]: [description]
        """

        command = re.sub("([\n][\n]+)", "\n", command.rstrip("\n").lstrip("\n"))
        n_to_receive = command.count("\n") + 1 if command else 0

        # skip if command is empty
        if not n_to_receive:
            # construct an empty respond here and leave
            return ["", ""], True, ""

        if isinstance(self.gpascii, GpasciiClient):

            # TODO turn this to a decorator
            # split commamnds if more than limit
            N_MAX_CMD = 10000

            resp = []
            success = True
            errmsg = ""

            n_begin = 0
            n_end = min(n_begin + N_MAX_CMD, n_to_receive)
            while n_end > n_begin:
                command_ = "\n".join(command.split("\n")[n_begin:n_end])
                resp_, success, errmsg = self.gpascii.send_receive_raw(
                    cmds=command_, timeout=timeout
                )
                resp += resp_

                if not success:
                    return resp, success, errmsg
                n_begin = n_end
                n_end = n_begin + min(N_MAX_CMD, n_to_receive - n_begin)

            return resp, success, errmsg

        if isinstance(self.gpascii, PpmacToolMt):
            # check if there are only one command

            success, returned_lines = self.gpascii.send_receive(
                command, timeout=timeout
            )

            if len(returned_lines) < 2:
                # command had no response, e.g. #4$
                returned_lines.append("")

            if success:
                error_msg = None

                if n_to_receive == len(returned_lines):
                    # in case of multiple commands,
                    # commands are not included in the reponse
                    cmd_response = [command, "\n".join(returned_lines)]

                else:
                    cmd_response = returned_lines
                wasSuccessful = True
            else:
                error_msg = returned_lines[1]
                cmd_response = [returned_lines[0], error_msg]
                wasSuccessful = False

            # wasSuccessful = True if success > 0 else False

            return cmd_response, wasSuccessful, error_msg

    def send_list_receive_dict(self, cmd_list, timeout=5):

        if not isinstance(self.gpascii, GpasciiClient):
            return None, None, None

        cmd_str = "\n".join(str(e) for e in cmd_list)
        cmd_resp, wasSuccessful, error_msg = self.send_receive_raw(cmd_str)

        if not wasSuccessful:
            # there are some errors but we can't through away the whole response!
            return None, False, error_msg

        ret_list = cmd_resp[1].split("\n")

        # extract the values
        ret_key_val = [
            stat.lower().strip("\n").strip(" ").strip("'").split("=")
            for stat in ret_list
        ]

        ppmac_key_val = dict()

        for i, keyval in enumerate(ret_key_val):

            # first, verify if the returned cmd (key) matches sent cmd

            if len(keyval) == 2:
                if keyval[0] == cmd_list[i]:
                    ppmac_key_val[cmd_list[i]] = {
                        "val": keyval[1],
                        "time": time.time(),
                    }
                else:
                    # returned key is different, e.g. p(8190+2) returns p8192
                    # check if this is the case, and
                    invalid_vars = re.sub(r"[iqpdl]\d+", "", keyval[0])
                    if invalid_vars:
                        return None, False, f"mistmatch in ppmac response: {error_msg}"
                    valid_var_num = re.findall(r"(?:[iqpdl])(\d+)", keyval[0])[0]
                    evalstr = f"{cmd_list[i][1:]} - {valid_var_num}"
                    if not eval(evalstr) == 0:
                        return None, False, f"wrong variable index!! : {evalstr}"
                    # it's ok to pass use the original command for this one
                    ppmac_key_val[cmd_list[i]] = {
                        "val": keyval[-1],
                        "time": time.time(),
                    }

            # if the key is not yet found
            elif len(cmd_list) > i:
                ppmac_key_val[cmd_list[i]] = {
                    "val": keyval[-1],
                    "time": time.time(),
                }

        return ppmac_key_val, wasSuccessful, error_msg

    def close(self):
        self.gpascii.close()


class WrascPmacGate(ra.Agent):

    ppmac = ...  # type : PPMAC

    fetch_cmds = ...  # type : list
    fetch_cmd_parsed = ...  # type : str
    cry_cmds = ...  # type : list
    cry_cmd_parsed = ...  # type : str
    celeb_cmds = ...  # type : list
    celeb_cmd_parsed = ...  # type : str

    pass_conds = ...  # type : list
    pass_conds_parsed = ...  # type : list

    pass_logs = ...  # type : list
    pass_logs_parsed = ...  # type : list

    ongoing = ...  # type : bool

    def __init__(
        self,
        ppmac: PPMAC = None,
        fetch_cmds=[],
        pass_conds=[],
        cry_cmds=[],
        cry_retries=1,
        cry_pretries=0,
        celeb_cmds=[],
        pass_logs=[],
        csv_file_path=None,
        log_while_waiting=False,
        ongoing=False,
        wait_after_celeb=None,
        **kwargs,
    ):

        self.kwargs = {}
        self.pp_globals = {}

        self.wait_after_celeb = None
        self.ongoing = False

        self.fetch_cmds = []
        self.pass_conds = []
        self.cry_cmds = []
        self.cry_retries = 1
        self.cry_tries = 0
        self.cry_pretries = 0
        self.celeb_cmds = []
        self.pass_logs = []

        self.pass_logs_parsed = []
        self.csv_file_name = None
        self.log_while_waiting = False
        # if you are here, then we have an agent to intialise

        super().__init__(
            poll_in=ppwr_poll_in,
            act_on_invalid=ppwr_act_on_invalid,
            act_on_valid=ppwr_act_on_valid,
            act_on_armed=ppwr_act_on_armed,
            fetch_cmds=fetch_cmds,
            pass_conds=pass_conds,
            cry_cmds=cry_cmds,
            cry_retries=cry_retries,
            cry_pretries=cry_pretries,
            celeb_cmds=celeb_cmds,
            pass_logs=pass_logs,
            csv_file_path=csv_file_path,
            log_while_waiting=log_while_waiting,
            ongoing=ongoing,
            wait_after_celeb=wait_after_celeb,
            **kwargs,
        )

        if not ppmac or (not isinstance(ppmac, PPMAC)):
            self.dmAgentType = "uninitialised"
            return

        self.dmAgentType = "ppmac_wrasc"

        self.ppmac = ppmac  # type : PPMAC

        if not self.ppmac.connected:
            self.ppmac.connect()
            time_0 = timer()
            time_out = 2  # sec

            while not self.ppmac.connected:

                if timer() < time_0 + time_out:
                    raise TimeoutError(f"PPMAC connection timeout: {self.ppmac.host}")
                sleep(0.1)

    def setup(
        self,
        fetch_cmds=None,
        pass_conds=None,
        cry_cmds=None,
        cry_retries=None,
        cry_pretries=None,
        celeb_cmds=None,
        pass_logs=None,
        csv_file_path=None,
        log_while_waiting=None,
        ongoing=None,
        wait_after_celeb=None,
        **kwargs,
    ):

        """
        sets up class parameters:
        fetch_mds: commands to run when pass values are invalid. These might be establidhsing connection
        pass_conds: pass conditions as list of texts. A pass_cond=True always passes. 
        In case of [] or None or not passing, cry_cmds will be used to create verification condition:
         "=" in statements will be replaced by "==". non-statement commands will be ignored.
        """

        if kwargs:
            # merge with existing
            self.kwargs = {**self.kwargs, **kwargs}

        if wait_after_celeb:
            self.wait_after_celeb = wait_after_celeb

        if ongoing:
            self.ongoing = ongoing

        # every one of cmds and conds pass this point,
        # so its best to esxpand them here

        self.fetch_cmds = expand_pmac_stats(
            fetch_cmds if fetch_cmds else self.fetch_cmds, **self.kwargs
        )
        self.fetch_cmds_parsed = parse_cmds(self.fetch_cmds)

        self.cry_cmds = expand_pmac_stats(
            cry_cmds if cry_cmds else self.cry_cmds, **self.kwargs
        )
        self.cry_cmds_parsed = parse_cmds(self.cry_cmds)

        self.celeb_cmds = expand_pmac_stats(
            celeb_cmds if celeb_cmds else self.celeb_cmds, **self.kwargs
        )
        self.celeb_cmds_parsed = parse_cmds(self.celeb_cmds)

        if cry_retries:
            self.cry_retries = cry_retries

        if cry_pretries:
            self.cry_pretries = cry_pretries

        # TODO fix: this makes an arbitrary pass_cond when cry_cmds are changed
        # via setup, i.e. no NEW pass_conds are supplied.
        # dirty fix is to check if there are only pass_conds parsed, then
        # don't change them.

        if (not self.pass_conds) and (not pass_conds) and (cry_cmds):
            # an empty pass-cond (but not a None) means: check for all of the command statements:
            pass_conds = stats_to_conds(cry_cmds)

        self.pass_conds = expand_pmac_stats(
            pass_conds if pass_conds else self.pass_conds, **self.kwargs
        )
        self.pass_conds_parsed = parse_stats(self.pass_conds)

        # pass_logs_parsed need to be fetched with pass_conds_parsed, stored, and logged at celeb.
        self.pass_logs = expand_pmac_stats(
            pass_logs if pass_logs else self.pass_logs, **self.kwargs
        )
        self.pass_logs_parsed = parse_stats(self.pass_logs)

        if csv_file_path:
            self.csv_file_name = csv_file_path

            # setup the headers, they get written when (and only if) the first set of readings are ready
            if self.pass_logs_parsed:
                headers = ["Time"] + list(list(zip(*self.pass_logs_parsed))[2])
                # remove and reshape special caharacters headers

                headers = [normalise_header(header) for header in headers]

                self.csvcontent = ",".join(map(str, headers)) + "\n"

                if self.csvcontent and self.csv_file_name:

                    # time_stamp the filename
                    self.csv_file_stamped = utils.time_stamp(self.csv_file_name)

                    # if file exists, make a backup of the existing file
                    # do not leave until the file doesn't exist!
                    n_copies = 0
                    while os.path.exists(self.csv_file_stamped):
                        name, ext = os.path.splitext(self.csv_file_stamped)
                        modif_time_str = time.strftime(
                            "%y%m%d_%H%M",
                            time.localtime(os.path.getmtime(self.csv_file_stamped)),
                        )
                        n_copies_str = f"({n_copies})" if n_copies > 0 else ""
                        try:
                            os.rename(
                                self.csv_file_stamped,
                                f"{name}_{modif_time_str}{n_copies_str}{ext}",
                            )
                        except FileExistsError:
                            # forget it... the file is already archived...
                            # TODO or you need to be too fussy and break the execution for this?
                            n_copies += 1

                    open(self.csv_file_stamped, "w+")
            else:
                # self.log_vals = []
                self.csvcontent = None

        if log_while_waiting:
            self.log_while_waiting = log_while_waiting

        # TODO change this crap[ solution
        # floating digits used for == comparison
        self.ndigits = 6

        super().setup(**self.kwargs)

        return self

    def eval_cmd(self, cmds_str):

        """ evaluates {} macros with actual values from ppmac
        this is done at the very late stage i.e. as late as possible.
       
        Raises:
            RuntimeError: [description]

        Returns:
            [type]: [description]
        """

        # NO NEED TO purge spaces
        # cmds_str = cmds_str.replace(" ", "")

        # find all of the macros which are previously marked by {} at parse time
        macro_list = re.findall(f"(?:{macrostrs[0]})(.*?)(?:{macrostrs[1]})", cmds_str)
        # evaluate the macro's first.
        # These are the "right side" statements in a command,
        # which ppmac can not resolve in an online command as opposed to a plc or a program.
        for stat in parse_stats(macro_list):

            l_template, statement = self.check_cond(stat)

            if l_template is None:
                raise RuntimeError(f"comms with ppmac at {self.ppmac.host}")

            rt_val = eval(l_template)
            evaluated_stat = macrostrs[0] + statement + macrostrs[1]
            cmds_str = cmds_str.replace(evaluated_stat, f"{rt_val}")

        return cmds_str

    def check_cond(self, condition):
        """
        Evaluates the condition/statement, by fethcing all macro variables from ppmac

        Args:
            condition ([type]): [description]

        Returns:
            (str,str): evaluated_stat.lower(), statement
        """

        if self.ppmac_key_val:
            # offline info already exists... check further?
            return self.check_cond_offline(condition)

        evaluated_stat, l_vars, statement = condition

        for i, l_var in enumerate(l_vars):
            # acquire the variable to check
            tpl = self.ppmac.send_receive_raw(l_var)

            if not tpl[1]:
                # self.poll.Var = None
                # effectively make it invalid!!
                raise RuntimeError(
                    f"ppmac returned error on statement {statement} command {l_var}"
                )
                # evaluated_stat = "NaN"
                # break

            ret_val = tpl[0][1].strip("\n").strip(" ").strip("'").split("=")[-1]

            if not isPmacNumber(ret_val):
                # treat this return as string
                ret_val = f"'{ret_val}'"

            elif ret_val.startswith("$"):
                # check if it is a valid hex
                ret_val = str(int(ret_val[1:], 16))

            evaluated_stat = evaluated_stat.replace(f"_var_{i}", ret_val)
        # ppmac is a non case sensitive system, so return comparison statement in lower case

        return (
            evaluated_stat.lower() if "'" in evaluated_stat else evaluated_stat,
            statement,
        )

    def receive_cond_parsed(self, stats_parsed):
        """
        receive all stats in pass_conds_parsed
        """

        # extract all stats
        var_list_of_lists = [elem[1] for elem in stats_parsed]
        cmd_list = [item.lower() for sublist in var_list_of_lists for item in sublist]

        self.ppmac_key_val, success, err_msg = self.ppmac.send_list_receive_dict(
            cmd_list
        )

        if not success:
            # indicate failed acquisition by setting the dict to None
            self.ppmac_key_val = None
            # raise RuntimeError(f"{err_msg} in {cmd_list}")

    def check_cond_offline(self, condition):
        """
        Evaluates the condition/statement, by fethcing all macro variables from ppmac

        Args:
            condition ([type]): [description]

        Returns:
            (str,str): evaluated_stat.lower(), statement
        """

        evaluated_stat, l_vars, statement = condition

        for i, l_var in enumerate(l_vars):

            l_var = l_var.lower()  # type: str
            if l_var not in self.ppmac_key_val:
                print("gooz")

            ret_val = self.ppmac_key_val[l_var]["val"]

            if "fraction" in condition[0].lower():
                # choss
                _ = condition[0].lower()

            if not isPmacNumber(ret_val):
                # treat this return as string
                ret_val = f"'{ret_val}'"

            elif ret_val.startswith("$"):
                # check if it is a valid hex
                ret_val = str(int(ret_val[1:], 16))

            evaluated_stat = evaluated_stat.replace(f"_var_{i}", ret_val)
        # ppmac is a non case sensitive system, so return comparison statement in lower case
        return (
            evaluated_stat.lower() if "'" in evaluated_stat else evaluated_stat,
            statement,
        )

    def check_pass_conds(self):

        for condition in self.pass_conds_parsed:
            # take templates and variables from inside the
            # condisions and verify the statement

            verify_text, statement = self.check_cond(condition)

            if verify_text is None:
                # major comms error, do not try the rest of the conditions?
                return ra.StateLogics.Invalid, "comms error"

            if verify_text == "err":
                # this condition had some issues with syntax, continue with the rest
                verify_text = verify_text

            if (verify_text.count("==") == 1) and ("'" not in verify_text):
                one_sided_verify_text = verify_text.replace("==", " - (") + ")"
                # TODO improve this, the whole scheme shall work on a numpy is_close instead of isequal:
                # depending on the lvar, round off or not!
                left_side = condition[1][0]  # type: str
                qual = left_side.lower().split(".")[-1]
                if qual.endswith("speed"):
                    precision = 1e-6
                elif qual.endswith("gain"):
                    precision = 1.0e-7
                elif qual.endswith("pwmsf"):
                    precision = 1  # probably wrong
                elif qual.endswith("maxint"):
                    precision = 0.0625
                elif qual.endswith("scalefactor"):
                    precision = 1e-16
                elif qual.endswith("freq"):
                    precision = 0.5
                else:
                    precision = 1e-16

                try:
                    if abs(eval(one_sided_verify_text)) > precision:
                        # if eval(verify_text) == False:
                        # no need to check the rest of the conditions

                        return (
                            False,
                            f"{statement}: {one_sided_verify_text} > {precision}",
                        )
                    continue
                except:
                    pass
            # arithmentic error, check literal statement
            if eval(verify_text) == False:
                # no need to check the rest of the conditions
                return False, f"{statement}: {verify_text} "

        return True, "True"

    @property
    def is_done(self):

        """ True if the agent actions are complete
        Always True for agents with ongoing variable set

        Returns:
            [type]: [description]
        """

        if self.ongoing or self.act.Var:
            return True
        else:
            return False

    def reset(self):
        self.poll.force(None, immediate=False)
        self.act.force(None, immediate=True)

    def acquire_log(self):
        """
        acquire pass_log_parsed conditions and put them in cvscontent
        """

        # now that it is going to be True, calculate the logs.
        # they will be saved to file via actions:

        vals = [self.poll.Time]
        self.receive_cond_parsed(self.pass_logs_parsed)
        for condition in self.pass_logs_parsed:
            # acquire log statements

            # if self.name.startswith("ma_on_") and condition[0].startswith("_var_0-05"):
            #     print("delete_this")

            verify_text, statement = self.check_cond(condition)

            if verify_text:
                # store eval(verify_text) in the logs dict:
                if isPmacNumber(verify_text):
                    vals.append(eval(verify_text))
                else:
                    # text value
                    vals.append(verify_text)
        if len(vals) > 1:
            self.csvcontent += ",".join(map(str, vals)) + "\n"

        return True

    def log_to_file(self):
        # now log a line to cvs if there is one

        if self.csvcontent and self.csv_file_stamped:

            with open(self.csv_file_stamped, "a+") as file:
                file.write(self.csvcontent)

            self.csvcontent = ""

    def celeb_act(self):

        # do celeb commands if they exist
        if self.celeb_cmds_parsed:
            resp = self.ppmac.send_receive_raw(self.eval_cmd(self.celeb_cmds_parsed))
        else:
            resp = ""

        # in any case reset cry_tries = 0
        self.cry_tries = 0

        # if this is a staged-pass then
        # stop checking the condition. Stage is now passed.
        # this will also trigger transition to Done state the next cycle.
        if not self.ongoing:
            self.poll.hold(for_cycles=-1, reset_var=False)

        return ra.StateLogics.Armed, f"armed: {resp}"

    def cry_act(self):
        # condition is not met, so the we need to keep checking, and probably sending a fixer action
        # check how many times this is repeated
        # this is a way of managing reties:
        # once the agent gets armed, it will not be released until externally poked back?

        if self.cry_cmds_parsed:

            if self.cry_tries >= self.cry_retries:
                return (
                    ra.StateLogics.Idle,
                    f"retries exhausted {self.cry_tries}/{self.cry_retries}",
                )

            self.cry_tries = self.cry_tries + 1
            resp = self.ppmac.send_receive_raw(self.eval_cmd(self.cry_cmds_parsed))
            if not resp[1]:
                # error in command or comms
                pass

            return (
                ra.StateLogics.Idle,
                f"Fix action {self.cry_tries}/{self.cry_retries} {resp[2]}",
            )

        return ra.StateLogics.Idle, "No action"


# -------------------------------------------------------------------
def done_condition_poi(ag_self: ra.Agent):

    """[summary] poll in method
        check "done" condition.
        set the sequence by setting the prohibits
        this agent remains invalid until the process is all done
        and then uses

    Returns:
        [type]: [description]
    """

    assert isinstance(ag_self, WrascRepeatUntil)
    ag_self: WrascRepeatUntil

    all_stages_passed = ag_self.all_done_ag.is_done  # poll.Var

    if not all_stages_passed:
        return (
            None,
            f"awating {ag_self.all_done_ag.name}...{ag_self.repeats + 1} to go",
        )

    for agname in ag_self.agent_list:
        ag = ag_self.agent_list[agname]["agent"]  # type : ra.Agent
        assert isinstance(ag, ra.Agent)

        # only reset ags which are below this control agent
        if ag.layer >= ag_self.layer:
            continue

        all_stages_passed = all_stages_passed and (
            ag.is_done or ag.inhibited
        )  # ag.poll.Var
        if not all_stages_passed:
            return None, f"awaiting {ag.name} ...{ag_self.repeats + 1} to go"

    # all done. Now decide based on a counrter to either quit or reset and repeat
    if ag_self.repeats > 0:
        return False, f"Resetting the loop"
    else:
        return True, "loop exhausted..."


def arm_to_quit_aov(ag_self: ra.Agent):
    """action on valid: arm to 
    either reset the self.reset_these_ags list of agents, 
    or quit wrasc if repeat times exceed self.repeats

    Args:
        ag_self (ra.Agent): [description]

    Returns:
        [type]: [description]
    """

    assert isinstance(ag_self, WrascRepeatUntil)
    ag_self: WrascRepeatUntil

    if ag_self.poll.Var == True:
        # inform and log, confirm with other agents...
        return ra.StateLogics.Armed, "Done and out."
    elif ag_self.poll.Var == False:
        # action: invalidate all agents in this subs-stage,
        # so the cycle restart
        for ag in ag_self.reset_these_ags:

            assert isinstance(ag, ra.Agent)

            # only reset ags which are below this control agent
            ag.reset()

        ag_self.repeats -= 1

        return ra.StateLogics.Valid, f"{ag_self.repeats + 1} to go"


def quit_act_aoa(ag_self: ra.Agent):
    """ act on armed:

    quit if agent value is True, else go Idle again

    (incomplete) if quit_if_done is not set, then do n more repeats

    Args:
        ag_self (ra.Agent): [description]

    Returns:
        [type]: [description]
    """

    assert isinstance(ag_self, WrascRepeatUntil)
    ag_self: WrascRepeatUntil

    if not ag_self.quit_if_done:
        ag_self.repeats = 30
        ag_self.reset()
        return ra.StateLogics.Done, "RA_WHATEVER"

    if ag_self.poll.Var:
        return ra.StateLogics.Done, "RA_QUIT"
    else:
        return ra.StateLogics.Idle, "RA_WHATEVER"


class WrascRepeatUntil(ra.Agent):
    """ A repeat Until special Reactive Agent

    Args:
        ra ([type]): [description]
    """

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

        self.dmAgentType = "RepeatUntil_RA"

        self.all_done_ag = None
        self.reset_these_ags = []
        self.quit_if_done = True
        self.repeats = 0


default_asic = lambda axis: (axis - 1) // 4
default_chan = lambda axis: (axis - 1) % 4
default_companion = lambda axis: axis + 8


class axis:
    def __init__(self, amp_number, **kwargs):
        super().__init__()

        self.motor_n = amp_number
        self.prim_asic, self.prim_chan = default_asic_chan(self.motor_n)

        self.second_asic = self.prim_asic
        self.second_chan = self.prim_chan

        self.companion_axis = default_companion(self.motor_n)

        self.reverse_encoder = False

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


def ags_done(ag_list, all_done):
    if all_done:
        return all([ag.is_done for ag in ag_list])
    else:
        return any([ag.is_done for ag in ag_list])


def do_ags(ag_list, cycle_period=0.25, all_done=True, verbose=None):
    """process a list of ppra agents until all are done

    Args:
        ag_self (ppra.WrascPmacGate): [description]

    Returns:
        [type]: [description]
    """

    if not isinstance(ag_list, list):
        ag_list = [ag_list]

    for ag in ag_list:
        ag: WrascPmacGate
        ag.reset()
        if verbose:
            ag.verbose = verbose

    time_0 = timer()
    next_infer_time = time_0 + cycle_period

    while not ags_done(ag_list, all_done):

        while next_infer_time < timer():
            next_infer_time += cycle_period
        next_act_time = next_infer_time + cycle_period / (2)
        lead_time = next_infer_time - timer()
        if lead_time > 0:
            time.sleep(lead_time)
            print(".", end="")
        else:
            print("i", end="")

        for ag_self in ag_list:
            ag_self: WrascPmacGate
            ag_self._in_proc()

            desc = ""
            if ag_self.verbose > 1:
                desc = ag_self.annotate()[1]
                print(f"{ag_self.name}: {desc}")

        run_time = timer() - time_0

        lead_time = next_act_time - timer()
        if lead_time > 0:
            time.sleep(lead_time)
            print(".", end="")
        else:
            print("o", end="")

        for ag_self in ag_list:
            ag_self: WrascPmacGate
            ag_self._out_proc()


if __name__ == "__main__":
    pass
