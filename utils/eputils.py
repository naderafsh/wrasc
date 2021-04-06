from wrasc.ppmac_ra import isPmacNumber
import utils as ut
import pytest
from epics import PV, caget, caput
import regex as re


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


if __name__ == "__main__":
    pass
