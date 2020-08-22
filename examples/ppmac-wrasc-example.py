from wrasc import reactive_agent as ra
from wrasc import ppmac_ra as ppra
from os import environ
from ppmac import GpasciiClient

_VERBOSE_ = 3

#test code
# Linux:  export PPMAC_TEST_IP="10.23.92.220"
# Win sc: $env:PPMAC_TEST_IP="10.23.92.220"

ppmac_test_IP = environ["PPMAC_TEST_IP"]

test_gpascii = GpasciiClient(ppmac_test_IP)

# stage 0: #3 and #4 shall be at 1000 +- 10 counts

# verify strings are native ppmac
# but commands use macros in {} (defined by ppra.macrostrs) which need to be evaluated realtime.
verify_str, try_str = ppra.assert_pos_wf(4,"#3p",1)
celebrate_str = None

xx = 4
pos_lo = "#3p"
pos_target = "{#3p + 1000}"
verify_str = [f"#{xx}p > {pos_lo}",f"Motor[{xx}].DesVelZero == 1",f"Motor[{xx}].InPos == 1"]
try_str = f"#{xx}j={pos_target}"

s00_inip_ag = ppra.ppmac_wrasc(test_gpascii, verifiy_stats=verify_str, cry_cmds=try_str, celeb_cmds=celebrate_str, verbose=_VERBOSE_)
s00_inip_ag.poll_pr = lambda ag_self: True

verify_str, try_str = ppra.assert_pos_wf(3,"#4p + 1000",1) 
celebrate_str = None

s01_inip_ag = ppra.ppmac_wrasc(test_gpascii, verifiy_stats=verify_str, cry_cmds=try_str, celeb_cmds=celebrate_str, verbose=_VERBOSE_)
s01_inip_ag.poll_pr = lambda ag_self: s00_inip_ag.poll.Var

(verify_str, try_str) = ppra.assert_pos_wf(4,1000,1)
celebrate_str = None

s02_inip_ag = ppra.ppmac_wrasc(test_gpascii, verifiy_stats=verify_str, cry_cmds=try_str, celeb_cmds=celebrate_str, verbose=_VERBOSE_)
s02_inip_ag.poll_pr = lambda ag_self: s01_inip_ag.poll.Var

(verify_str, try_str) = ppra.assert_pos_wf(3,1000,1)

s03_inip_ag = ppra.ppmac_wrasc(test_gpascii, verifiy_stats=verify_str, cry_cmds=try_str, celeb_cmds=celebrate_str, verbose=_VERBOSE_)
s03_inip_ag.poll_pr = lambda ag_self: s02_inip_ag.poll.Var

#-------------------------------------------------------------------
def done_condition_poi(ag_self: ra.Agent):
    
    # check "done" condition.
    # set the sequence by setting the prohibits
    # this agent remains invalid until the process is all done 
    # and then uses 

    all_stages_passed = ag_self.last_layer_dependency_ag.poll.Var

    if not all_stages_passed:
        return None, "supervising..."

    for agname in ag_self.agent_list:
        ag = ag_self.agent_list[agname]['agent']
        assert isinstance(ag,ra.Agent)

        # only reset ags which are below this control agent
        if ag.layer >= ag_self.layer:
            continue
        
        all_stages_passed = all_stages_passed and ag.poll.Var

    if not all_stages_passed:
        return None, "supervising..."


    # all done. Now decide based on a counrter to either quit or reset and repeat
    if ag_self.repeat:
        return False, 'Resetting the loop to repeat'
    else:
        return True, 'Quitting...'

def arm_to_quit_aov(ag_self: ra.Agent):
    if ag_self.poll.Var == True:
        # inform and log, confirm with other agents...
        return ra.StateLogics.Armed, 'quitting...'
    elif ag_self.poll.Var == False:
        # action: invalidate all agents in this subs-stage, 
        # so the cycle restart
        for agname in ag_self.agent_list:
            ag = ag_self.agent_list[agname]['agent']
            assert isinstance(ag,ra.Agent)

            # only reset ags which are below this control agent
            if ag.layer >= ag_self.layer:
                continue

            ag.poll.force(None, immediate=False)

        return ra.StateLogics.Idle, 'all ags reset...'       

def quit_act_aoa(ag_self: ra.Agent):

    if ag_self.poll.Var:
        return ra.StateLogics.Done, 'RA_QUIT'
    else:        
        return ra.StateLogics.Idle, 'RA_WHATEVER'

def control_action(ag_self: ppra.ra.Agent):

    return ra.StateLogics.Idle, "idling"

quit_if_all_done_ag = ra.Agent(verbose=_VERBOSE_, poll_in=done_condition_poi, act_on_valid=arm_to_quit_aov, act_on_armed=quit_act_aoa)
quit_if_all_done_ag.repeat = True
quit_if_all_done_ag.last_layer_dependency_ag = s03_inip_ag

#----------------------------------------------------------------------

#=====================================================================================
# input('press a key or break...')
# dm module called to compile and install agents
agents_sorted_by_layer = ppra.ra.compile_n_install({}, globals().copy(), "WORKSHOP01")
# input('press any key to start the process loop...')
# dm module takes control of the process loop
ppra.ra.process_loop(agents_sorted_by_layer, 100, cycle_period=1, debug=True)

test_gpascii.close