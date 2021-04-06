from wrasc.ppmac_ra import isPmacNumber
import utils as ut
import pytest
from epics import PV, caget, caput
import regex as re
from typing import List
from timeit import default_timer as timer
from time import sleep, time
from inspect import getmembers


maths_sym_rx = r"[\+\-\*\/=><! \(\)]"


def parse_vars(stat):

    template = stat
    maths_split = re.split(maths_sym_rx, stat)
    var_list = []
    vars_index = 0
    for item in maths_split:
        # is this item blank?
        if not item:
            continue
        if isPmacNumber(item):
            continue

        var_list.append(item)
        template = template.replace(item, f"_var_{vars_index}")
        vars_index += 1

    return template, var_list


def eval_stat(template, long_var_list):
    ret_val_list = []
    evaluated_stat = template
    for vars_index, long_var in enumerate(long_var_list):
        ret_val = caget(long_var, as_string=True)
        if not isPmacNumber(ret_val):
            # treat this return as string
            ret_val = f"'{ret_val}'"

        evaluated_stat = evaluated_stat.replace(f"_var_{vars_index}", ret_val)

        ret_val_list.append(ret_val)

    return evaluated_stat.lower() if "'" in evaluated_stat else evaluated_stat


def check_eval_stat(eveluated_stat, precision=0.01):

    # see if numerical evaluation with tolerance leads to a definitive answer
    if (eveluated_stat.count("==") == 1) and ("'" not in eveluated_stat):
        one_sided_verify_text = eveluated_stat.replace("==", " - (") + ")"
        try:
            err = abs(eval(one_sided_verify_text))
            return err < precision, err

        except:
            pass

    # now try an exact match
    try:
        if eval(eveluated_stat):
            return True, "match"
        else:
            return False, "mismatch"
    except:
        return False, None


class SmartEpics:
    def __init__(self, prefix=None) -> None:
        self.prefix = prefix
        self.pass_list = []
        pass

    def check(self, conditions: list, verbose=True):
        """check a list of conditions and return True if all of them pass.
           individual results are available in .pass_list


        Args:
            prefix (str): [if not supplied, will default to last prefix supplied]
            stat_list (list of str): statements using PV names, python maths, and '~' for prefix. A None condition returtns True.

        Returns:
            [boolean]: [True if all conditions are True]
        """
        if not conditions:
            return True

        if verbose:
            print(f"\nchecking {len(conditions)} conditions... ")

        self.pass_list = []
        # first, parse the statements to separate variables from constants and operators
        for statement in conditions:
            if not statement:
                continue
            template, var_list = parse_vars(statement)
            long_var_list = []
            # complete the shorthanded vars in var_list
            for var in var_list:
                if "~" in var:
                    assert self.prefix
                    long_var = str(var).replace("~", self.prefix)
                long_var_list.append(long_var)
            # now fetch all the vars

            eveluated_stat = eval_stat(template, long_var_list)

            passed, err = check_eval_stat(eveluated_stat)
            self.pass_list.append(passed)

            if verbose:
                print(f"  {statement}, {passed}, err={err}")

        n_not_passed = len([p for p in self.pass_list if not p])

        if verbose:
            if n_not_passed > 0:
                print(f"{n_not_passed} conditions NOT passed.")

            print("-------------------\n")

        return all(self.pass_list)


class EPV:
    def __init__(self, prefix,) -> None:

        """[summary]


        Returns:
            [type]: [description]
        """
        self.pyname = None

        self.prefix = prefix

        self.shortname = None

        self.PV = None

        # additional variables

        self.expected_value = None

        # minimum incremental change
        self.inc_resolution = None

        # error tolerance used to verify
        self.default_tolerance = None

        self.timer = timer

        self.initialised = True

        # self.change(self, expected_value=None)

    def connection_callback(self, pvname, conn, pv):

        assert self.fullname == pvname
        self.done_connecting = conn

    def connect(
        self,
        shortname,
        callback=None,
        form="time",
        verbose=False,
        auto_monitor=None,
        count=None,
        connection_callback=None,
        connection_timeout=None,
        access_callback=None,
    ) -> bool:

        """[summary]


        Returns:
            [type]: [description]
        """

        if not self.initialised:
            return False
        self.done_connecting = None
        self.shortname = shortname

        self.fullname = self.prefix + self.shortname
        if not connection_callback:
            connection_callback = self.connection_callback

        self.PV = PV(
            self.fullname,
            callback,
            form,
            verbose,
            auto_monitor,
            count,
            connection_callback,
            connection_timeout,
            access_callback,
        )

    def change(self, expected_value=None):

        needs_polling = False

        if expected_value:
            self.expected_value = expected_value
            needs_polling = True
            self.changed = True

        if needs_polling:
            self.PV.poll()

    def is_almost(self, expected_value: float, tolerance: None):

        if not tolerance:
            tolerance = self.default_tolerance

        return abs(self.PV.value - expected_value) < tolerance

    def verify(self, expected_value, tolerance: None):

        if self.PV.type is float:
            return self.is_almost(expected_value, tolerance)

        elif self.PV.type is str:
            return self.PV.value == str(expected_value)

    def connecting(self, timeout=2):

        st = self.timer()

        while not self.done_connecting:
            sleep(0.01)
            if self.timer() - st > timeout:
                return False

        return self.PV.connected


class EpicsMotor:
    def __init__(self, prefix) -> None:
        """[summary]




        Args:
            prefix ([type]): [description]
        """

        self.prefix = prefix

        # self.bdst = list(map(et.EPV, [self.prefix] * 1))

        """ naming conventions:
                    if var name islower then 
                    shortname = shortname.upper()

        """

        self.usregu_pvs = [
            self._d_rbv,
            self._d_val,
            self._d_velo,
            self._d_vmax,
            self._d_twv,
            self._d_off,
            self._d_hlm,
            self._d_llm,
        ] = list(map(EPV, [self.prefix] * 8))

        self.dot_epvs = [
            self._d_bdst,
            self._d_bvel,
            self._d_dmov,
            self._d_dval,
            self._d_escf,
            self._d_eres,
            self._d_hls,
            self._d_jar,
            self._d_egu,
            self._d_lls,
            self._d_mscf,
            self._d_mres,
            self._d_msta,
            self._d_rdbd,
            self._d_rdif,
        ] = list(map(EPV, [self.prefix] * 15))

        self.non_dot_epvs = [
            self._c_kill_d_proc,
            self._c_InPos_d_RVAL,
            self._c_PhaseFound_d_RVAL,
            self._c_ConfigLock_d_RVAL,
        ] = list(map(EPV, [self.prefix] * 4))

        self.epv_count = 0
        self.all_epvs = set([])
        # now, use a search in self members to initialise shortnames!
        for mem in getmembers(self):
            if mem[0].startswith("__"):
                continue
            if isinstance(mem[1], EPV):
                # an epv member of this motor is found,
                # now connect it

                epv = mem[1]  # type et.EPV
                epv.pyname = mem[0]
                shortname = mem[0].replace("_d_", ".").replace("_c_", ":")
                if shortname.islower():
                    # this is a hidden convention:
                    shortname = shortname.upper()

                # print(f"connecting {mem[0]} variable to PV {shortname}")
                epv.connect(shortname)
                self.epv_count += 1
                self.all_epvs.add(epv)

        self.printable_list = []

        for epv in self.all_epvs:  # type ExtendedPV
            if epv.connecting(timeout=3):
                self.printable_list.append([f"{epv.PV.pvname}", "connected"])
            else:
                self.printable_list.append([f"{epv.PV.pvname}", "timed out"])

        self.default_egu = self._d_egu.PV.value
        self.con_epvs = set([epv for epv in self.all_epvs if epv.PV.connected])
        self.egu_epvs = set()  # a new copy

        for epv in self.con_epvs:
            if not epv.PV.units:
                continue

            if self.default_egu in epv.PV.units:
                self.egu_epvs.add(epv)


if __name__ == "__main__":
    pass
