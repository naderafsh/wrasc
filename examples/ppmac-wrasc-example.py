from wrasc import reactive_agent as ra
from wrasc import ppmac_ra as ppra
from os import environ
from ppmac import GpasciiClient

_VERBOSE_ = 3

# test code
# Linux:  export PPMAC_TEST_IP="10.23.92.220"
# Win sc: $env:PPMAC_TEST_IP="10.23.92.220"

ppmac_test_IP = environ["PPMAC_TEST_IP"]

test_gpascii = GpasciiClient(ppmac_test_IP)


class stage_wrasc(dict):
    verify_str: str = ...
    try_str: str = ...
    celebrate_str: str = ...
    fetch_str: str = ...

    def __init__(
        self,
        verify_str=verify_str,
        try_str=try_str,
        celebrate_str=celebrate_str,
        fetch_str=fetch_str,
    ):
        pass


# verify strings are native ppmac
# but commands use macros in {} (defined by ppra.macrostrs) which need to be evaluated realtime.
verify_str, try_str = ppra.assert_pos_wf(4, "#3p", 1)
celebrate_str = None

xx = 4
pos_lo = "#3p"
pos_target = "{#3p + 1000}"
verify_str = [
    f"#{xx}p > {pos_lo}",
    f"Motor[{xx}].DesVelZero == 1",
    f"Motor[{xx}].InPos == 1",
]
try_str = f"#{xx}j={pos_target}"

s00_inip_ag = ppra.ppmac_wrasc(
    verbose=_VERBOSE_,
    ppmac=test_gpascii,
    poll_pr=lambda ag_self: True,
    verifiy_stats=verify_str,
    cry_cmds=try_str,
    celeb_cmds=celebrate_str,
)
# s00_inip_ag.poll_pr = lambda ag_self: True

verify_str, try_str = ppra.assert_pos_wf(3, "#4p + 1000", 1)
celebrate_str = None

s01_inip_ag = ppra.ppmac_wrasc(
    verbose=_VERBOSE_,
    ppmac=test_gpascii,
    verifiy_stats=verify_str,
    cry_cmds=try_str,
    celeb_cmds=celebrate_str,
)


(verify_str, try_str) = ppra.assert_pos_wf(4, 1000, 1)
celebrate_str = None

s02_inip_ag = ppra.ppmac_wrasc(
    verbose=_VERBOSE_,
    ppmac=test_gpascii,
    verifiy_stats=verify_str,
    cry_cmds=try_str,
    celeb_cmds=celebrate_str,
)

(verify_str, try_str) = ppra.assert_pos_wf(3, 1000, 1)

s03_inip_ag = ppra.ppmac_wrasc(
    verbose=_VERBOSE_,
    ppmac=test_gpascii,
    verifiy_stats=verify_str,
    cry_cmds=try_str,
    celeb_cmds=celebrate_str,
)

# setup the sequence default dependency (can be done automaticatlly)
s01_inip_ag.poll_pr = lambda ag_self: s00_inip_ag.poll.Var
s02_inip_ag.poll_pr = lambda ag_self: s01_inip_ag.poll.Var
s03_inip_ag.poll_pr = lambda ag_self: s02_inip_ag.poll.Var

# now setup a sequencer
quit_if_all_done_ag = ppra.sequencer_wrasc(verbose=_VERBOSE_)

quit_if_all_done_ag.repeat = True
quit_if_all_done_ag.last_layer_dependency_ag = s03_inip_ag

# ----------------------------------------------------------------------

# =====================================================================================
# input('press a key or break...')
# dm module called to compile and install agents
agents_sorted_by_layer = ppra.ra.compile_n_install({}, globals().copy(), "WORKSHOP01")
# input('press any key to start the process loop...')
# dm module takes control of the process loop
ppra.ra.process_loop(agents_sorted_by_layer, 100, cycle_period=1, debug=True)

test_gpascii.close
