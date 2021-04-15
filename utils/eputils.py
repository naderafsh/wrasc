from ctypes import sizeof
from math import remainder
from wrasc.ppmac_ra import isPmacNumber
import utils as ut
import pytest
from epics import PV, caget, caput
import regex as re
from typing import List
from timeit import default_timer as timer
from time import CLOCK_THREAD_CPUTIME_ID, sleep, time
from inspect import getmembers


maths_sym_rx = r"[\+\-\*\/=><! \(\)]"

pv_num_types = ["time_double", "time_short", "time_long"]


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
    def __init__(self, prefix: str, infs_equal=True, default_tolerance=0) -> None:

        """[summary]


        Returns:
            [type]: [description]
        """
        self.pyname = None  # type: str

        self.prefix = prefix

        self.shortname = None  # type: str

        self.PV = None  # type: PV

        # additional variables

        self._expected_value = None
        self._tolerance = None

        # this flag indicates that the expected value can be set to actual
        # once fail is registered, so that this failure is not spread to consequential tests.
        # this flag shall be used externally
        # and shall be used with extreme care
        self.persistent_failure = None

        # error tolerance used to verify
        self.default_tolerance = default_tolerance

        self.saved_value = None
        self.verified = None
        self.fail_if_unexpected = False
        self.infs_equal = infs_equal

        # minimum incremental change
        self.inc_resolution = None

        self.timer = timer

        self.initialised = True

        # self.change(self, expected_value=None)

    def connection_callback(self, pvname: str, conn, pv):

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

    @property
    def expected_value(self):
        return self._expected_value

    @expected_value.setter
    def expected_value(self, set_val_tol):
        """[summary]

        Args:
            set_tup ([type]): [description]
        """
        # unpack
        if isinstance(set_val_tol, tuple):
            set_val, set_tol = set_val_tol
        else:
            #
            set_val = set_val_tol
            set_tol = None

        # assert type consistency
        if self.PV.type in [str]:
            assert isinstance(set_val, str)
            self._tolerance = None

        elif isinstance(set_val, str):
            assert set_val.startswith("$") or isPmacNumber(set_val)
            self._tolerance = set_tol
        else:
            # otherwise, a number:
            if set_val is not None:
                float(set_val)
            self._tolerance = set_tol

        # if set_value is None, it means there is no expected value
        if set_val is None:
            self.fail_if_unexpected = False
            self._expected_value = None
        else:
            # now that this value is literally set from outside:
            self.fail_if_unexpected = True
            self._expected_value = set_val

    @property
    def tolerance(self):
        if self._tolerance is None:
            self._tolerance = self.default_tolerance
        return self._tolerance

    @tolerance.setter
    def tolerance(self, set_tol):
        self._tolerance = set_tol
        if self.default_tolerance is None:
            self.default_tolerance = self._tolerance
        self.verified = False

    @property
    def value(self):
        return self.PV.value

    @value.setter
    def value(self, set_val):
        # TODO make this an array of timed values
        self.saved_value = self.PV.value
        self.PV.value = self.expected_value = set_val
        self.verified = False

    # def change(self, expected_value=None):

    #     needs_polling = False

    #     if expected_value:
    #         self._expected_value = expected_value
    #         needs_polling = True
    #         self.changed = True

    #     if needs_polling:
    #         self.PV.poll()

    def is_almost(self, expected_value: float, tolerance: None):

        if tolerance is None:
            tolerance = self.tolerance

        if (
            self.infs_equal
            and self.PV.value == float("inf")
            and self._expected_value == float("inf")
        ):
            return True
        elif (
            self.infs_equal
            and (-1 * self.PV.value == float("inf"))
            and (-1 * self._expected_value == float("inf"))
        ):
            return True
        else:
            return abs(self.PV.value - expected_value) <= tolerance

    def verify(self, expected_value=None, tolerance=None):

        if expected_value is None:
            expected_value = self.expected_value
        else:
            self.expected_value = expected_value

        if self.expected_value is None:
            # if there was no default, and no new expected value is supplied
            self.expected_value = self.value
            # setting expected changes it to fail if changed, revert it
            self.fail_if_unexpected = False

        bitwise_ = str(self.expected_value)
        if bitwise_.startswith("$"):
            val = int(self.value)
            bitwise_ = bitwise_.strip("$")
            # bitwise comparison
            for i in range(0, len(bitwise_) - 1):
                bitnum = len(bitwise_) - 1 - i
                if bitwise_[i] not in ["0", "1"]:
                    continue

                if ((val >> (bitnum - 1)) & 1) != int(bitwise_[i]):
                    self.verified = False
                    break
            self.verified = True

        elif self.PV.type in pv_num_types:
            self.verified = self.is_almost(self.expected_value, tolerance)

        elif self.PV.type in [str]:
            self.verified = self.PV.value == str(self.expected_value)
        else:
            raise RuntimeError(f" NEED TO ADD NEW TYPE TO VERIFY: {self.PV.type}")

        return self.verified

    def connecting(self, timeout=2):

        st = self.timer()

        while not self.done_connecting:
            sleep(0.01)
            if self.timer() - st > timeout:
                return False

        return self.PV.connected


class EpicsMotor:
    def __init__(
        self, prefix, default_wait=0.5, base_settings=None, is_float_motrec=True
    ) -> None:
        """[summary]




        Args:
            prefix ([type]): [description]
        """
        self.base_settings = base_settings

        self.travel_range = float(self.base_settings["fullrange_egu"])
        self.in_pos_band = float(self.base_settings["InPosBand"])
        self.is_float_motrec = is_float_motrec

        self.prefix = prefix

        self.default_wait = default_wait

        # self.bdst = list(map(et.EPV, [self.prefix] * 1))

        """ naming conventions:
                    if var name islower then 
                    shortname = shortname.upper()

        """

        self.dot_epvs = [
            self._d_bdst,
            self._d_dval,
            self._d_rscf,
            self._d_eres,
            self._d_jar,
            self._d_egu,
            self._d_mscf,
            self._d_mres,
            self._d_dir,
            self._d_rdbd,
            self._d_rmp,
            self._d_rep,
        ] = list(map(EPV, [self.prefix] * 12))

        self.dialegu_epvs = [self._d_dval, self._d_drbv] = list(
            map(EPV, [self.prefix] * 2)
        )

        self.usregu_epvs = [
            self._d_rbv,
            self._d_val,
            self._d_velo,
            self._d_vmax,
            self._d_bvel,
            self._d_twv,
            self._d_off,
            self._d_hlm,
            self._d_llm,
            self._d_rdif,
        ] = list(map(EPV, [self.prefix] * 10))

        self.status_epvs = [
            self._d_dmov,
            self._d_hls,
            self._d_lls,
            self._d_msta,
            self._d_lvio,
            self._c_InPos_d_RVAL,
            self._c_PhaseFound_d_RVAL,
            self._c_ConfigLock_d_RVAL,
        ] = list(map(EPV, [self.prefix] * 8))

        self.control_s = [
            self._c_kill_d_proc,
            self._d_jogf,
            self._d_jogr,
            self._c_homing,
            self._d_set,
            self._d_stop,
            self._d_foff,
            self._d_rdbd,
        ] = list(map(EPV, [self.prefix] * 8))

        self.pmac_extra_s = [self._c_ferror, self._c_ferrormax] = list(
            map(EPV, [self.prefix] * 2)
        )

        if not self.is_float_motrec:
            self._d_mscf = None

        self.epv_count = 0
        self.all_epvs = set([])
        # now, use a search in self members to initialise shortnames!
        for mem in getmembers(self):
            if mem[0].startswith("__"):
                continue
            if isinstance(mem[1], EPV):
                # an epv member of this motor is found,
                # now connect it

                epv = mem[1]  # type: EPV
                epv.pyname = mem[0]
                shortname = mem[0].replace("_d_", ".").replace("_c_", ":")

                assert shortname
                if shortname.islower():
                    # this is a hidden convention:
                    shortname = shortname.upper()

                # print(f"connecting {mem[0]} variable to PV {shortname}")
                epv.connect(shortname)
                self.epv_count += 1
                self.all_epvs.add(epv)

        self.printable_list = []

        for epv in self.all_epvs:  # type: ExtendedPV
            if epv.connecting(timeout=3):
                self.printable_list.append([f"{epv.PV.pvname}", "connected"])
            else:
                self.printable_list.append([f"{epv.PV.pvname}", "timed out"])

        self.default_egu = self._d_egu.PV.value  # type: str
        self.connected_epvs = set([epv for epv in self.all_epvs if epv.PV.connected])
        self.egu_epvs = set()  # a new copy

        for epv in self.connected_epvs:
            if not epv.PV.units:
                continue

            if self.default_egu in epv.PV.units:
                self.egu_epvs.add(epv)
        self.set_def_tol()

        self._set_additional_epv_sets()

    def _set_additional_epv_sets(self):
        self.user_setting_s = [
            self._d_twv,
        ]

        self.val_and_rbv_s = [self._d_val, self._d_rbv, self._d_rdif]

        self.usr_coord_setting_s = [
            self._d_mres,
            self._d_mscf,
            self._d_off,
        ]

        self.velo_s = [
            self._d_velo,
            self._d_vmax,
            self._d_bvel,
        ]

        self.soft_lim_s = [
            self._d_hlm,
            self._d_llm,
        ]

        self.extra_s = [
            self._d_bdst,
            self._d_bvel,
        ]

        self.verify_epvs = set(
            self.usr_coord_setting_s
            + self.velo_s
            + self.usregu_epvs
            + self.status_epvs
            + self.pmac_extra_s,
        )

    def set_def_tol(self):

        for epv in self.usregu_epvs:
            if epv.PV.units == self.default_egu:
                # egu values
                epv.default_tolerance = self._d_mres.PV.value * 2
            elif epv.PV.units.startswith(self.default_egu):
                # velocity values
                epv.default_tolerance = self._d_mres.PV.value * 2 * 1 / 0.01  # sec
            else:
                # what else?
                pass

    def is_usr_dir_reversed(self):
        return ((1 if self._d_dir.value == 0 else -1) * self._d_mscf.value) < 0

    def move(
        self,
        pos_inc=0,
        timeout=None,
        override_slims=False,
        expect_success=True,
        dial_direction=False,
        block_until_done=True,
    ):

        if dial_direction and self.is_usr_dir_reversed():
            pos_inc = -pos_inc

        self.pos_setpoint = self._d_rbv.value + pos_inc

        if override_slims:
            if self._d_hlm.value < self.pos_setpoint:
                self._d_hlm.value = (
                    self.pos_setpoint + 100 * self._d_hlm.default_tolerance + 0.1
                )
            if self._d_llm.value > self.pos_setpoint:
                self._d_llm.value = (
                    self.pos_setpoint - 100 * self._d_llm.default_tolerance - 0.1
                )

        self._d_val.value = self.pos_setpoint
        if expect_success:

            self._d_rdif.expected_value = (0, self.in_pos_band)
            self._d_rbv.expected_value = (self.pos_setpoint, self.in_pos_band)
            self._d_msta.expected_value = "$x00xx0xx0xxx0xxx"
            self._d_lls.expected_value = 0
            self._d_hls.expected_value = 0
            self._d_lvio.expected_value = 0

        else:
            self._d_val.fail_if_unexpected = False

        self._d_dmov.expected_value = 1

        if not block_until_done:
            return

        # and wait until dmov or timeout:
        if not timeout:
            # set timneout based on velocity
            timeout = abs(pos_inc / self._d_velo.value) + 2 * 0.1 + 1

        sleep(0.1)
        start_time = time()
        back_str = ""
        timed_out = False
        while not self._d_dmov.value:
            elapsed_time = time() - start_time

            if elapsed_time > timeout:
                print(f"  timeout", end="")
                timed_out = True
                break

            print(back_str, end="")
            sleep(0.05)
            elapsed_time_str = f"{elapsed_time:6.2f}"
            print(elapsed_time_str, end="", flush=True)
            back_str = "\b" * len(elapsed_time_str)
        print("", end=" ")

        return not timed_out

    def reset_expected_values(self, epvs=None):
        """resets all expected values to current values and sets them to non-strick
            so that fail_if_unexpected will be false
        """
        if not epvs:
            epvs = self.connected_epvs

        for epv in epvs:
            assert isinstance(epv, EPV)
            epv._expected_value = epv.value
            epv.fail_if_unexpected = False

    if __name__ == "__main__":
        pass


if __name__ == "__main__":
    pass
