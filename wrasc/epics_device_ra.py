#!/usr/bin/env python
#
# $File: //ASP/Personal/afsharn/wrasc/wrasc/epics_device_ra.py $
# $Revision: #1 $
# $DateTime: 2020/08/09 22:35:08 $
# Last checked in by: $Author: afsharn $
#
# Description
# <description text>
#
# Copyright (c) 2019 Australian Synchrotron
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# Licence as published by the Free Software Foundation; either
# version 2.1 of the Licence, or (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public Licence for more details.
#
# You should have received a copy of the GNU Lesser General Public
# Licence along with this library; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA 02110-1301 USA.
#
# Contact details:
# nadera@ansto.gov.au
# 800 Blackburn Road, Clayton, Victoria 3168, Australia.
#


""" generic pure epics device
    intended to map the internal dpendency of an epice device.
    epics devices have their essential states available via PV's
    an example is rascan2 and epics motor-record. 
    this new epics_device may be used as straight forward iunterface to "extended" pmac motors
"""

from wrasc import reactive_agent as ra
from inspect import getmembers
import copy


def verify(ag_self: ra.Agent):
    # check if this is ok
    # matching the saved value
    # withing tolerance    
    
    if not ag_self.owner.activator_ag.poll.Var:
        return None, 'not activated'

    _in = ag_self.in_PV.value

    if ag_self.poll.SavedVar is not None:
        
        _new = _in
        _old = ag_self.poll.SavedVar
        
        try:
            _deviation =  abs(_new - _old)
        except:
            _deviation = 'N/A'

        if (type(_deviation) != str) and ag_self.poll.ErrTol is not None:
            changed = _deviation > ag_self.poll.ErrTol
        else:
            changed = (_new != _old)

        if changed:
            # difference is found, so returning None as the check
            # is invalid.
            # at the same time, invoke user choice if it is not done yet!
            ag_self.owner.user_choice_ag.act.unhold()
            return None, 'differs by {}'.format(_deviation)
    return _in, ''


def confirm_restoring(ag_self: ra.Agent):

    ag_owner = ag_self.owner # type EpicsExtendedMotor
 
    mres_changed = ag_owner.dot_mres_ag.poll.Var[1]!='NotChanged'

    motor_choice = ag_owner.user_choice_ag.poll.Var
    if motor_choice is None:
        return None, ''

    if ag_self.poll.NoRestore or mres_changed:
       ag_self.poll.force('DIFF', for_cycles=-1)
       usr_choice=input(f'{ag_self.name} value is {ag_self.in_PV.value} was {ag_self.poll.SavedVar} [ok]')
       return ra.StateLogics.Idle, ''

    if motor_choice =='aSk'[1]:
        usr_choice=input(f'restore {ag_self.name} from {ag_self.in_PV.value} to {ag_self.poll.SavedVar}? Restore/[Ignore and skip this motor]')
    elif motor_choice=='All'[0]:
        usr_choice='Restore'[0]
    else:
        usr_choice='Ignore'[0] 
    #usr_choice = 'Y'
    if usr_choice.upper() == 'Restore'[0]:
        return ra.StateLogics.Armed, 'confirmed'
    else:
        # no one field can be ignored. The whole motor is ignored now, so immediately force
        # user choice so that consequetive restore actions also ignore in the same cycle
        ag_owner.user_choice_ag.poll.force('Ignore'[0], for_cycles=-1, immediate=True)
        ag_self.poll.force('diff ignored', for_cycles=-1)
    return ra.StateLogics.Idle, ''


def restore(ag_self: ra.Agent):
    ag_self.in_PV.value = ag_self.poll.SavedVar
    return ra.StateLogics.Done, 'restored'


def put_out_pv(ag_self: ra.Agent):
    # mind this: pvc will not be invoked for process every cycle.
    if ag_self.out_PV.value != ag_self.poll.Var:
        ag_self.out_PV.put(ag_self.poll.Var)
    return ra.StateLogics.Done, ''


def reset_out_pv(ag_self: ra.Agent):
    ag_self.out_PV.value = 0
    return ra.StateLogics.Idle, ''


def no_dependecy(ag_self : ra.Agent):

    return (1,'no dependency')


def get_user_choice(ag_self: ra.Agent):
    
    if ag_self.owner.activator_ag.poll.Var != True:
        return (ra.StateLogics.Idle,'')

    ans = input(f'{ag_self.name}: restore All/None/[ask one by one]?').upper()
    if ans != 'A' and ans != 'N':
        ans = 'S'
    ag_self.poll.force(ans)
    return (ra.StateLogics.Done,'')


def mres_verify(ag_self: ra.Agent):
    # special verify for mres   
    
    if not ag_self.owner.activator_ag.poll.Var:
        return None, 'not activated'

    _in = ag_self.in_PV.value

    if ag_self.poll.SavedVar is not None\
        and ag_self.poll.ErrTol is not None:
        _new = _in
        _old = ag_self.poll.SavedVar
        _deviation =  abs(_new - _old)
        if _deviation > ag_self.poll.ErrTol:
            # difference is found, but will not return invalid.
            # The new value is just indicated
            ag_self.owner.user_choice_ag.act.unhold()
            return (_in,'Changed'), 'MRES differs by {}'.format(_deviation)
    return (_in,'NotChanged'), ''

def restore_rrbv(ag_self: ra.Agent):

    ag_owner = ag_self.owner # type EpicsExtendedMotor
 
    if ag_owner.dot_mres_ag.poll.Var[1]=='NotChanged':

        print('restoring rrbv')

        # caput(pvprefix+'.'+'SET','Set')
        # time.sleep(0.5)
        # caput(pvprefix+'.'+'FOFF','Frozen')
        # time.sleep(0.5)
        # caput(pvprefix + '.' + 'DVAL',restoreDVAL)                            
        # time.sleep(0.5)
        # caput(pvprefix+'.'+'FOFF','Variable')
        # time.sleep(0.5)
        # caput(pvprefix+'.'+'SET','Use')


    ag_self.in_PV.value = ag_self.poll.SavedVar
    return ra.StateLogics.Done, 'restored'

_VERBOSE_ = 4

class EpicsExtendedMotor(ra.Device):

    def __init__(self, unit=None, **kwargs):
        self.dmDeviceType = 'EpicsExtendedMotor'
        self.default_dev_prefix = ':TEST'
        self.default_dev_pvs = None

        super().__init__(**kwargs)

        """ this class creates PV's based on its named agents. Conventions are:
        PV names are all CAPITAL
        agents with prefix dot_ are treated as inter-record fields, hence starting with .
        agends with prefix colon_ are considered extra fields, hence starting with : 
        """
                
        self.activator_ag = ra.Agent(owner=self, verbose=_VERBOSE_)
        self.activator_ag.poll_in = lambda ag_self: (True,'active')
        
        self.user_choice_ag = ra.Agent(owner=self, act_on_invalid=get_user_choice, verbose=_VERBOSE_)
        self.user_choice_ag.act.hold(for_cycles=-1)

        # actual motor fields from here:

        # first check the no restores        
        self.dot_lvio_ag = ra.Agent(owner=self, poll_in=verify, act_on_invalid=confirm_restoring, act_on_armed=restore, verbose=_VERBOSE_)
        self.dot_lvio_ag.poll.ErrTol = 0.5
        self.dot_lvio_ag.poll.NoRestore = True

        self.dot_movn_ag = ra.Agent(owner=self, poll_in=verify, act_on_invalid=confirm_restoring, act_on_armed=restore, verbose=_VERBOSE_)
        self.dot_movn_ag.poll.ErrTol = 0.5
        self.dot_movn_ag.poll.NoRestore = True

        self.dot_mres_ag = ra.Agent(owner=self, poll_in=mres_verify, act_on_invalid=confirm_restoring, act_on_armed=restore, verbose=_VERBOSE_)
        self.dot_mres_ag.poll.ErrTol = 1e-16
        self.dot_mres_ag.poll.NoRestore = True

        self.dot_eres_ag = ra.Agent(owner=self, poll_in=verify, act_on_invalid=confirm_restoring, act_on_armed=restore, verbose=_VERBOSE_)
        self.dot_eres_ag.poll.ErrTol = 1e-16
        self.dot_eres_ag.poll.NoRestore = True

        # Restore these, if mres is NOT changed: 
        self.dot_dir_ag = ra.Agent(owner=self, poll_in=verify, act_on_invalid=confirm_restoring, act_on_armed=restore, verbose=_VERBOSE_)
        self.dot_dir_ag.poll.ErrTol = 0.5


        self.dot_off_ag = ra.Agent(owner=self, poll_in=verify, act_on_invalid=confirm_restoring, act_on_armed=restore, verbose=_VERBOSE_)
        self.dot_off_ag.poll.ErrTol = 0.001
        self.dot_off_ag.poll_pr = lambda ag_self: ag_self.owner.dot_dir_ag.known

        self.dot_rrbv_ag = ra.Agent(owner=self, poll_in=verify, act_on_invalid=confirm_restoring, act_on_armed=restore_rrbv, verbose=_VERBOSE_)
        self.dot_rrbv_ag.poll_pr = lambda ag_self: ag_self.owner.dot_off_ag.known

        self.dot_rbv_ag = ra.Agent(owner=self, poll_in=verify, act_on_invalid=confirm_restoring, act_on_armed=restore, verbose=_VERBOSE_)
        self.dot_rbv_ag.poll_pr = lambda ag_self: ag_self.owner.dot_off_ag.known

        # first set of PV's are level0
        # self.dot_rrbv_ag = ra.Agent(owner=self, pre_in=get_in_pv, verbose=_VERBOSE_)
        # self.dot_mres_ag = ra.Agent(owner=self, pre_in=get_in_pv, verbose=_VERBOSE_)

        self.colon_uninit_ag = ra.Agent(owner=self, poll_in=verify, act_on_invalid=confirm_restoring, act_on_armed=restore, verbose=_VERBOSE_)
        self.colon_uninit_ag.poll.NoRestore = True


        def spmg_pr(ag_self: ra.Agent):
            
            ag_owner = ag_self.owner # type EpicsExtendedMotor
            pr = ag_owner.dot_rbv_ag.known and \
                ag_owner.dot_off_ag.known

            return pr

        self.dot_spmg_ag = ra.Agent(owner=self, poll_pr=spmg_pr, poll_in=verify, act_on_invalid=confirm_restoring, act_on_armed=restore, verbose=_VERBOSE_)
        


        # self.dot_rbv_ag = ra.Agent(owner=self, pre_in=get_in_pv, verbose=_VERBOSE_)

        # # now define dependencies:
        # self.dot_movn_ag.poll_in = no_dependecy
        # self.dot_dir_ag.poll_in = no_dependecy
        # self.dot_mres_ag.poll_in = no_dependecy

        # self.dot_rbv_ag.poll_in = lambda ag_self: (
        #     ag_self.owner.dot_mres_ag.poll.Var 
        #     + ag_self.owner.dot_dir_ag.poll.Var 
        #     + ag_self.owner.dot_rrbv_ag.poll.Var 
        #     ,'depends on user coord'
        #     )

        # self.dot_val_ag = ra.Agent(act_on_valid=put_out_pv, act_on_invalid=reset_out_pv, verbode=_VERBOSE_)
        # self.init_ag = ra.Agent(act_on_valid=put_out_pv, act_on_invalid=reset_out_pv, verbode=_VERBOSE_)
        # self.force_uninit_ag = ra.Agent(act_on_valid=put_out_pv, act_on_invalid=reset_out_pv, verbode=_VERBOSE_)

        def temp(ag_self: ra.Agent):

            r = (ag_self.owner.activator_ag.known) \
                and \
                (ag_self.owner.user_choice_ag.poll.Var=='Ignored'[0] \
                    or \
                ag_self.owner.dot_spmg_ag.known
                )

            return (r,'all done')

        def deactivate(ag_self: ra.Agent):
            if ag_self.poll.Var and ag_self.poll.Changed:

                ag_self.owner.activator_ag.poll.hold(for_cycles=-1)
                ag_self.owner.activator_ag.poll.force(False, for_cycles=-1, immediate=True)
                return ra.StateLogics.Done, ''
                
            return ag_self.act.Var, ''

        self.deactivator_ag = ra.Agent(owner=self, poll_in=temp, act_on_valid=deactivate, verbose=_VERBOSE_)

        # just setting eprefix and dev_prefix if there was no pv_list in kwargs
        self.install_dev_pvs(**kwargs)

        # setting agent pv's
        self.set_ag_pvs()

    def set_ag_pvs(self):

        names = [memb[0] for memb in getmembers(self)]
        ag_names = [nam for nam in names if nam.endswith('_ag') \
            and (nam.startswith('colon_') or nam.startswith('dot_')) ]
        #  while extra fields need  a ':'
        pv_names = [ nam.replace('_ag','').replace('colon_',':',1).replace('dot_','.',1).upper() for nam in ag_names]
        # motor record fields are marked with _ spo :_ shall be relaced with .

        if self.eprefix is not None\
            and self.dev_prefix is not None\
            and len(pv_names) > 0:

            for pvname in pv_names:
                agname = pvname.replace('.','dot_',1).replace(':','colon_',1).lower() + '_ag'
                exec_str = "self.{0}.install_pvs(inpvname='{1}', outpvname='{1}', dev_prefix='{2}', eprefix='{3}')"\
                    .format(agname, pvname, self.dev_prefix, self.eprefix)
                exec(exec_str)

                # and set saved values:

    def set_saved_value(self, pvname='', value_str=''):

        agname = pvname.replace('.','dot_',1).replace(':','colon_',1).lower() + '_ag'

        names = [memb[0] for memb in getmembers(self)]
        if agname in names:
            # TODO this is a sticky point. Types of members can be known only after PV's are installed
            try:
                value = float(value_str)
            except ValueError:
                value = value_str

            exec_str = f"self.{agname}.poll.SavedVar={value}"
            exec(exec_str)

            return True

        return False

if __name__ == '__main__':
    pass

