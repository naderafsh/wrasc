
from wrasc import reactive_agent as ra
from ppmac import GpasciiClient
from timeit import default_timer as timer
from time import sleep
import re

""" ppmac basic agent. 
This agent checks (watches) a list of statement conditions, 
and triggeres (acts) a triple list of actions. accordingly.

These have no retry or timeout mechanism internally. Some specialised agents can take care of progress and deadlocks



"""

macrostrs = ["{","}"]

def assert_pos_wf(xx:int, pos, tol):
    """

    retuns 
    1 - assert condition for motor xx at resting at position pos+_tol
    2 - default jog statement to move the motor there if not already there

    """
    if isinstance(pos,str) or isinstance(tol,str):
        tol = str(tol)
        pos = str(pos)
        pos_hi = f"{pos} + {tol}"
        pos_lo = f"{pos} - {tol}"
        target_pos = macrostrs[0] + pos + macrostrs[1]
    else:
        pos_hi = pos + tol
        pos_lo = pos - tol
        target_pos = pos
    return [f"#{xx}p < {pos_hi}",f"#{xx}p > {pos_lo}",f"Motor[{xx}].DesVelZero == 1",f"Motor[{xx}].InPos == 1"], [f"#{xx}j={target_pos}"]


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

def parse_vars(any_side : str):

    # parse right or left soides of equation 
    # to parametrised temlate and list of vars

    all_vars = []
    # any_side: no change if it is a ppmacnumber, or an address
    if not (isPmacNumber(any_side) or any_side.endswith('.a')):
        # there is at least a variable on the right, 
        # which needs to be evaluated.
        for v in re.split(r'[\+\-\*\/=><! ]', any_side):
            if v and not isPmacNumber(v):
                all_vars.append(v)
                vars_index = len(all_vars) - 1
                any_side = any_side.replace(v,f"_var_{vars_index}")

    return any_side, all_vars

def validate_cmd_str(cmds):

    if cmds is None:
        return None

    if isinstance(cmds,str):
       return cmds
    elif isinstance(cmds,list):
        # convert list to one string of lines
        return "\n".join(cmds)
    else:
        raise RuntimeError(f"bad command: {cmds}")
 
def validate_watch_list(watch_list):

    # makes a list of variables on the watchlist which need to be fetched and relpaced with real-time values, real time.

    if watch_list is None:
        return None

    # make sure "verifies" is a list
    if isinstance(watch_list, str):
        watch_list =[watch_list]

    conditions = list()
    # there are conditions to check.
    for statement in watch_list:
        assert isinstance(statement, str)

        l_template, l_vars = parse_vars(statement)
        conditions.append([l_template, l_vars, statement])


    return conditions

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

        l_template, l_vars, statement = condition

        for i, l_var in enumerate(l_vars):
            # acquire the variable to check
            tpl = ag_self.ppmac.send_receive_raw(l_var)

            if not tpl[1]:
                ag_self.poll.Var = None
                return ra.StateLogics.Invalid, "comms error"

            l_value_loaded = tpl[0][1].strip("\n").strip(" ").split("=")[-1]
        
            l_template = l_template.replace(f"_var_{i}",l_value_loaded)
            
        # value_loaded = tpl[0][1].strip("\n").strip(" ")
        # value_loaded = value_loaded.split("=")[-1]

        # if not isPmacNumber(value_ref):
        #     value_ref = f"'{value_ref}'"
        #     value_loaded = f"'{value_loaded}'"

        # verify_text = f"{value_loaded} {logic_op} {value_ref}"

        verify_text = l_template
        if eval(verify_text)==False:
            return False , f"False: {statement} "
    
    return True, "True"

def ppwr_act_on_valid(ag_self: ra.Agent):
    """
    The best act here is to Arm when an action is known.
    Because there are two different actions are known here, it is best to reset the
    act status to idle whenever the poll status is changed.
    """

    # Arm for action if poll is changed to False or True
    if (ag_self.poll.Var == True) :

        # stop checking the condition. Stage is now passed.
        ag_self.poll.hold(for_cycles=-1, reset_var=False)

        if ag_self.celeb_cmds:
            resp = ag_self.ppmac.send_receive_raw(ag_self.expand_cmd_str(ag_self.celeb_cmds)) 

        return ra.StateLogics.Done, "Done and retained."

    elif ag_self.poll.Var == False:

        # condition is not met, so the we need to keep checking, and probably sending a fixer action
        # check how many times this is repeated
        # this is a way of managing reties:
        # once the agent gets armed, it will not be released until externally poked back?

        if ag_self.poll.NoChangeCount > 1:
            return ra.StateLogics.Idle, "Retries exhausted"
        
        if ag_self.cry_cmds:
            resp = ag_self.ppmac.send_receive_raw(ag_self.expand_cmd_str(ag_self.cry_cmds))
            return ra.StateLogics.Idle, "Fix action"
            
        return ra.StateLogics.Idle, "No action !!!"
  

def ppwr_act_on_invalid(ag_self: ra.Agent):
    if ag_self.fetch_cmds:
        ag_self.ppmac.send_receive_raw(ag_self.expand_cmd_str(ag_self.fetch_cmds))
    return ra.StateLogics.Idle, "reacted to invalid"



class ppmac_wrasc(ra.Agent):
    
    ppmac = ... # type : GpasciiClient
    
    def __init__(self, ppmac:GpasciiClient=None, verifiy_stats=None, 
    fetch_cmds=None, celeb_cmds=None, cry_cmds=None,
    poll_in=ppwr_poll_in, act_on_invalid=ppwr_act_on_invalid, act_on_valid=ppwr_act_on_valid,
    **kwargs):
        
        if not ppmac or (not isinstance(ppmac, GpasciiClient)):
            self.dmAgentType = 'uninitialised'
            return
            
        self.ppmac = ppmac

        self.verifies = validate_watch_list(verifiy_stats)

        self.fetch_cmds = validate_cmd_str(fetch_cmds)
        self.celeb_cmds = validate_cmd_str(celeb_cmds)
        self.cry_cmds = validate_cmd_str(cry_cmds)
        self.fetch_cmds = validate_cmd_str(fetch_cmds)

        if not self.ppmac.connected:
            self.ppmac.connect()
            time_0 = timer()
            time_out = 2 # sec
    
            while not self.ppmac.connected:
    
                if timer() < time_0 + time_out:
                    raise TimeoutError(f"GpasciiClient connection timeout: {self.ppmac.host}")
                sleep(0.1)

        # if you are here, then we have an agent to intialise

        super().__init__(poll_in=poll_in,act_on_invalid=act_on_invalid, act_on_valid=act_on_valid,
         **kwargs)
        self.dmAgentType = 'ppmac_wrasc'

        # compile statement lists
    def setup(self, **kwargs):
        super().setup(**kwargs)

    def expand_cmd_str(self, cmds_str):

        # expand {} macros with actual values from ppmac

        macro_list = re.findall(f"(?:{macrostrs[0]})(.*?)(?:{macrostrs[1]})",cmds_str)

        for condition in validate_watch_list(macro_list):

            l_template, l_vars, statement = condition
            
            for i, l_var in enumerate(l_vars):
                # acquire the variable to check
                tpl = self.ppmac.send_receive_raw(l_var)

                if not tpl[1]:
                    raise RuntimeError(f"comms with ppmac at {self.ppmac.host}")

                l_value_loaded = tpl[0][1].strip("\n").strip(" ").split("=")[-1]
            
                l_template = l_template.replace(f"_var_{i}",l_value_loaded)
            
            rt_val = eval(l_template)
            replace = macrostrs[0] + statement + macrostrs[1]
            cmds_str = cmds_str.replace(f"{replace}", f"{rt_val}")
        
        return cmds_str


if __name__ == "__main__":
    pass
