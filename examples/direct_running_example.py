def do_agent(ag_self: ppra.WrascPmacGate):
    """process an individual ppra agent, separately

    Args:
        ag_self (ppra.WrascPmacGate): [description]

    Returns:
        [type]: [description]
    """
    tpl = None, None
    while not ag_self.is_done:
        _ = ag_self._in_proc()
        tpl = ag_self._out_proc()
        sleep(0.25)

    # reset agent anyways?

    return tpl


def reset_agent(ag_self: ppra.WrascPmacGate):
    ag_self.poll.force(None, immediate=False)
    ag_self.act.force(None, immediate=True)


do_agent(ol_test.ma_base_config_ag)
do_agent(ol_test.ma_test_config_ag)
do_agent(ol_test.ma_go_mlim_ag)
do_agent(ol_test.ma_home_on_mlim_ag)

while not ol_test.ma_slide_on_plim_ag.is_done:

    while not ol_test.ma_slide_on_plim_ag.poll.Var:
        # run forward
        do_agent(ol_test.ma_step_forward_ag)
        ol_test.ma_slide_on_plim_ag._in_proc()
        if ol_test.ma_slide_on_plim_ag.poll.Var:
            break
        do_agent(ol_test.ma_step_back_ag)
        reset_agent(ol_test.ma_step_forward_ag)
        reset_agent(ol_test.ma_step_back_ag)

    tpl = ol_test.ma_slide_on_plim_ag._out_proc()

do_agent(ol_test.ma_slide_off_plim_ag)
