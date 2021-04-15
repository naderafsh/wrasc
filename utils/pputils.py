import regex as re


"""  ppmac utils
"""

macrostrs = ["{", "}"]

ppmac_func_dict = {"EXP2": "2**", "int": "int", "Fraction": "Fraction"}

regex_anynum = r"(?:[^a-z^A-Z])([+\-]?(?:0|[1-9]\d*)(?:\.\d*)?(?:[eE][+\-]?\d+)?)"
# "(?:[^a-z^A-Z])[+\-]?(?:0|[1-9]\d*)(?:\.\d*)?(?:[eE][+\-]?\d+)?"  # r"[+\-]?(?:0|[1-9]\d*)(?:\.\d*)?(?:[eE][+\-]?\d+)?"
regex_exp_notification = r"[+-]?\d+(?:\.\d*(?:[eE][+-]?\d+)?)"


def default_asic_chan(axis):
    return (axis - 1) // 4, (axis - 1) % 4


def stats_to_conds(cmd_stats):
    if isinstance(cmd_stats, str):
        cmd_stats = [cmd_stats]
    return [cond.replace("=", "==") if ("=" in cond) else cond for cond in cmd_stats]


def load_pp_globals(pp_global_filename):
    """loads ppmac global list form file and arranges a dictionary

    Args:
        pp_global_filename (str): [description]

    Returns:
        dict: ppmac globals in a dict
    """
    pp_glob_dict = dict()
    with open(pp_global_filename) as f:
        pp_global = f.read().splitlines()
        f.close

    for glob in pp_global:
        pp_glob = glob.split("\t")
        if pp_glob[1] == "Global":
            pp_glob_dict[pp_glob[2].split("(")[0]] = {
                "base": pp_glob[3],
                "count": int(pp_glob[4]),
            }
    return pp_glob_dict


def expand_globals(stats_in, pp_glob_dict, **vars):
    """ 
    converts statements with ppmac IDE handled globals back into ppmac native P-Vars
    also adds a compare equivalent for the statements list
    Args:
        pp_glob_dict (dict of dicts): [description]
        stats_in (list of strings): [description]

    Returns:
        list of strings: [description]
    """

    stats_out = []
    for stat in stats_in:
        stat_ = stat
        for glob, glob_fields in pp_glob_dict.items():
            if glob not in stat:
                continue

            # substitute global var
            if glob_fields["count"] > 1:
                # look for paranthesis and take care of index
                globals_in_stat = re.findall(rf"({glob})(\()(\w*)(\))", stat)
                for to_find in globals_in_stat:
                    to_replace = f"P({glob_fields['base']}+{to_find[2]})"
                    stat_ = stat_.replace("".join(to_find[:]), to_replace)
            else:
                stat_ = stat_.replace(glob, f"P{glob_fields['base']}")

        stats_out.append(stat_)

    return stats_out


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

    """parses a pmac statement 
    returns a template and a variable list.
    The variable are replaced by _var_{vars_index} in the template.

    example:
    input-> "EncTable[3].pEnc = Motor[3].PhasePos.a"
    output-> ("_var_0=='Motor[3].PhasePos.a'" , ['EncTable[3].pEnc'])
    
    Returns:
        (template, var list): a template and a variable list 
    """

    all_vars = []

    # first see if there are P-Var or I-Var references
    p_vars = re.findall(r"[pP]\([\w+]*\)", stat)
    for v in p_vars:
        all_vars.append(v)
        vars_index = len(all_vars) - 1
        stat = stat.replace(v, f"_var_{vars_index}")

    # find exponential notations and convert them.
    # ppmac doesn't understand 5e-3
    # only if it is not a quoteed string which may contain Acc24E3 !!!

    # TODO fix the hack
    stat = stat.replace("Acc24E", "Acc24_E_")
    stat = stat.replace("Acc65E", "Acc65_E_")

    exp_nums = re.findall(regex_anynum, stat)
    for v in exp_nums:
        if "e" in v.lower():
            stat = stat.replace(v, f"{float(v):.8f}")

    stat = stat.replace("Acc65_E_", "Acc65E")
    stat = stat.replace("Acc24_E_", "Acc24E")

    # split the statement
    for v in re.split(r"[\+\-\*\/=><! \(\)]", stat):

        if v.startswith("_"):
            # this is a variable, ignore
            pass

        elif v and not isPmacNumber(v):

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
    """pasres commands:
    finds and marks the macros on the right hand of commands

    Args:
        cmds ([type]): [description]

    Raises:
        RuntimeError: bad command syntax

    Returns:
        [type]: [description]
    """

    if cmds is None:
        return None

    if isinstance(cmds, str):
        cmds = [cmds]

    if not isinstance(cmds, list):
        raise RuntimeError(f"bad command: {cmds}")

    # convert list to one string of lines
    cmds_out = []
    buffer_mode = False
    for cmd in cmds:
        assert isinstance(cmd, str)

        # is the command oppening a buffer? if yes, that changes the context
        if cmd.upper().startswith("OPEN"):
            # if "open" in cmd:
            # remember this
            buffer_mode = True

        # Close commands shall be at the start of the line to be recognised
        if cmd.upper().startswith("CLOSE"):
            buffer_mode = False

        if buffer_mode:
            cmds_out.append(cmd)
            continue

        cmd_split = cmd.split("=")
        cmd_left = cmd_split[0]
        if len(cmd_split) > 1:
            # purge spaces and separate right and left side
            # need to add all possible online comands here too: "^:*" ?
            cmd_right = cmd_split[-1].replace(" ", "")
            if (not isPmacNumber(cmd_right)) and any(i in cmd_right for i in "+-*/^"):
                # right side is ILLEGAL as a ppmac online command. Mark it as a macro for late evaluation
                cmd_right = macrostrs[0] + cmd_right + macrostrs[1]

            cmds_out.append(f"{cmd_left}={cmd_right}")
        elif cmd:
            # don't add empty commands !
            cmds_out.append(cmd)
    # purge spaces in command strings

    if " " in cmds_out:
        print("changed here")

    return "\n".join(cmds_out)


def parse_stats(stat_list):

    """parses pmac statements into template and variables, 
    so the variables can be fetched from ppmac to evaluate the statement based on real-time ppmac values.

    Returns:
        [type]: [description]
    """

    if stat_list is None:
        return []

    # make sure "pass_conds_parsed" is a list
    if isinstance(stat_list, str):
        stat_list = [stat_list]

    parsed_conds = list()
    # there are conditions to check.
    for cond in stat_list:
        assert isinstance(cond, str)
        # romve spaces to make the output predictable
        cond = cond.replace(" ", "")
        if not cond:
            continue

        l_template, l_vars = parse_vars(cond)
        parsed_conds.append([l_template, l_vars, cond])

    return parsed_conds


def expand_pmac_stats(stats, **vars):

    """    this function expands the ppmac statements for the channel parmeters
    parameters shall be in the form of L1 ... L10 or {whatever}
    all of the variables shall be supplies via **vars
    
    this allows to scale the templates for different channel configuration


    Raises:
        RuntimeError: [description]

    Returns:
        [type]: [description]
    """

    # first, some type checking

    if not stats:
        return stats

    if isinstance(stats, str):
        stats = [stats]

    assert isinstance(stats, list)

    stats_out = []
    # expand the stats one by one
    for stat_org in stats:
        stat = stat_org
        assert isinstance(stat, str)

        # ignore line comments
        if stat.lstrip().startswith("//"):
            continue

        # support base L# format by reverting L# to {L#}

        # find L# except the ones already in {}
        l_vars = re.findall(r"(?<=[^\w{])(L\d)(?:[^\w{])", stat)

        for lvar in set(l_vars):
            # put L# in curley brackets
            stat = (
                stat.replace(lvar, macrostrs[0] + lvar + macrostrs[1])
                .replace(macrostrs[0] + macrostrs[0], macrostrs[0])
                .replace(macrostrs[1] + macrostrs[1], macrostrs[1])
            )

        try:
            stats_out.append(stat.format(**vars))
        except KeyError:
            # if there is a macro which can't be found in vars, then leave it!
            stats_out.append(stat)
            print(f"unresolved parameters; left for late binding:\n{stat_org}")
        except ValueError:
            # this is probably more serious...
            stats_out.append(stat)
            # TODO this is a hack: PLC code actually can contain {} so...!!!
            # print(f"ValueError possible invalid phrase in parameters:\n{stat_org}\n")
        except IndexError:
            # this is probably a syntax issue,
            # e.g. something other than a variable is passed as a macro
            # e.g. {0.2} is passed
            # raise RuntimeError(f"syntax error in ppmac statement: {stat} ")

            stats_out.append(stat)
            raise IndexError(f"syntax error in parameters:\n{stat_org}")

    return stats_out


if __name__ == "__main__":
    pass
