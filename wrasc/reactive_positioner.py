#!/usr/bin/env python
#
# $File: //ASP/Personal/afsharn/SCS/reactive_positioner.py $
# $Revision: #7 $
# $DateTime: 2020/04/23 23:34:43 $
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

# TODO debug directive
_VERBOSE_ = 2


from epics import PV

import reactive_agent as ra




minimal_motor_fields = ['.DMOV', '.MOVN', '.RBV', '.TDIR', '.VAL', ':INIT.PROC', ':FORCE_UNINIT.PROC']
default_motor_fields = minimal_motor_fields + \
                       ['.DESC', '.HLM', '.LLM', '.LVIO', '.MSTA',  '.OFF', '.RBV', '.SPMG.SVAL', '.STOP', '.TDIR', '.TWF', '.TWR', '.TWV', '.VELO',
                        ':ELOSSRC.A', ':FERRORMAX', ':FAULT', ':HOME_FLAG_USER.SVAL',  ':HOMING',
                        ':INTERLOCKRESET.PROC', ':ON_HOME_LIMIT',  ':SAVE_USER', ':STOP.PROC',
                        ':USERHLS', ':USERLLS',
                        ':WRONGLIMITRESET.PROC',
                        # TODO check why :FAULTENABLE is not being found but is on the GUI!!!
                        ]


# ag definitions BEGIN
def severity_aoa(ag_self: ra.SeverityAg):

    assert isinstance(ag_self.owner, Motor)

    if ag_self.action_str.startswith(':') or ag_self.action_str.startswith('.'):
        ag_self.owner.pv_by_name[ag_self.action_str].value = 1
        return ra.StateLogics.Done, ag_self.action_str
    elif ag_self.action_str in ['action_home_it', 'homing_unsuccessful']:
        # TODO group action is needed here...
        #  homing is usually too complex for this single axis positioner to do...
        #  call back or indicate this need by adding ag_self to a list ?
        # flag individual homing:
        ag_self.owner.do_homing_now = True
        # TODO this is crap code: unhold this as long as usuccessful!
        ag_self.owner.pose_for_homing_ag.poll.unhold()

        return ra.StateLogics.Idle, ag_self.action_str + ' waiting for external action...'
    else:
        return ra.StateLogics.Idle, 'no actions for ' + ag_self.action_str


def can_init_poi(ag_self: ra.Agent):

    assert isinstance(ag_self.owner, Motor)

    _list = ag_self.owner.severity_ag.status_record.max_severity_errors
    if len(_list) > ra.stat_name_index:
        _r = (_list[0][ra.stat_name_index] == 'Uninitialized')
        return _r, ''


def vel_poi(ag_self: ra.Agent):

    assert isinstance(ag_self.owner, Motor)

    # first degree estimate of the velocity, is based on command:
    # DONE need to know direction of motion here !!
    _moving = ag_self.owner.pv_by_name['.MOVN'].value
    _done_moving = ag_self.owner.pv_by_name['.DMOV'].value

    if (_moving == 0) and (_done_moving == 1):
        _r = 0
    elif _moving:
        _vel_commanded = ag_self.owner.pv_by_name['.VELO'].value
        _actVel = ag_self.owner.rbv_ag.poll.Diff / ag_self.owner.rbv_ag.poll.DiffTime if ag_self.owner.rbv_ag.poll.Diff else 0
        # _actDirection = ra.np.sign(_actVel)
        # DONE use ag_self.owner.pv_by_name['.TDIR'].value instead of actual
        _actDirection = ag_self.owner.pv_by_name['.TDIR'].value

        _r = _vel_commanded * _actDirection
    else:
        _r = 0
    return _r, ''


def rbv_poi(ag_self: ra.Agent):
    
    assert isinstance(ag_self.owner, Motor)

    _r = None
    return_message = '!'
    try:
        _r = ag_self.owner.pv_by_name['.RBV'].value
        # DONE to avoid circular dependency: move inErr calculation on to an action of rbv_error
        return_message = ''
    finally:
        return _r, return_message


def tweak_val_poi(ag_self: ra.Agent):
    """ Current signed tweak """

    assert isinstance(ag_self.owner, Motor)

    if ag_self.owner.vel_ag.poll.Var != 0:
        _r = ra.np.copysign(ag_self.owner.pv_by_name['.TWV'].value, ag_self.owner.vel_ag.poll.Var)
    else:
        _r = ag_self.poll.Var
    return _r, ''


def max_scan_vel_poi(ag_self: ra.Agent):
    """
    Max scan velocity, at which the reported position will be within position tolerance
    (roughly taken from MRES?), for max out-of-sync time
    """

    assert isinstance(ag_self.owner, Motor)

    _tweak_value = ag_self.owner.pv_by_name['.TWV'].value
    _position_tol = ag_self.owner.pos_prec_ag.poll.Var
    _max_sync_time = ag_self.owner.max_sync_time_ag.poll.Var
    _max_scan_vel = _position_tol / _max_sync_time

    if _tweak_value / _max_scan_vel < _max_sync_time * 2:  # sec
        # max scan vel is too small anyways. better to just do step scan.
        _max_scan_vel = 0
    return _max_scan_vel, ''


def rbv_err_poi(ag_self: ra.Agent):

    assert isinstance(ag_self.owner, Motor)

    return ag_self.owner.max_sync_time_ag.poll.Var * ag_self.owner.vel_ag.poll.Var, ''


def rbv_err_aov(ag_self: ra.Agent):
    """

    :type ag_self: ra.Agent
    """

    assert isinstance(ag_self.owner, Motor)

    ag_self.owner.rbv_ag.poll.Err = ag_self.poll.Var
    return ag_self.act.Var, ''


def tweak_check(ag_self: ra.Agent):

    assert isinstance(ag_self.owner, Motor)

    return_message = ''
    """override/correct inVar to values within limits"""
    twv = ag_self.poll.Var[0]
    twv_abs_min = ag_self.owner.pos_prec_ag.poll.Var * 2  # TODO hardcoded (kind of)
    if abs(twv) < twv_abs_min:
        twv = ra.np.copysign(twv_abs_min, twv)
        return_message += ', twv changed to twv_abs_min '

    max_tw_time = 30  # sec # TODO hardcoded
    # DONE prevent setting velocity too small, perhaps using a max tewak time parameter
    vel_abs_min = abs(twv / max_tw_time)
    vel = ag_self.poll.Var[1]
    if abs(vel) < vel_abs_min:
        vel = ra.np.copysign(vel_abs_min, vel)
        return_message += ', vel changed to vel_abs_min'

    r = [twv, vel]
    return r, return_message


def tweak_aoi(ag_self: ra.Agent):
    """reset the tweak value to its "saved" value"""

    assert isinstance(ag_self.owner, Motor)

    if ag_self.saved_value is not None:
        ag_self.owner.pv_by_name['.TWV'].value = abs(ag_self.saved_value['twv'])
        ag_self.owner.pv_by_name['.VELO'].value = abs(ag_self.saved_value['velo'])
        ag_self.saved_value = None
        return ra.OutStates.Done, 'reset tweak vals'

    return ra.OutStates.Idle, ''


def tweak_aov(ag_self: ra.Agent):
    """This agent is intended to set the TWV, and
    tweak left or right based on requested signed tweak value

    inVar in this case is the requested signed tweak value, which
     can be set (forced) from other agents... """

    assert isinstance(ag_self.owner, Motor)

    if ag_self.poll.Var[0] != 0:
        # new value, new command!?
        ag_self.saved_value = {'twv': ag_self.owner.pv_by_name['.TWV'].value, 'velo': ag_self.owner.pv_by_name['.VELO'].value}

        ag_self.owner.pv_by_name['.TWV'].value = abs(ag_self.poll.Var[0])
        ag_self.owner.pv_by_name['.VELO'].value = abs(ag_self.poll.Var[1])
        ag_self.owner.pv_by_name['.STOP'].value = 1
        ag_self.act.hold(for_seconds=1, reset_var=False)
        return ra.StateLogics.Armed, 'set to tweak...'
    else:
        return None, ''


def tweak_aoa(ag_self: ra.Agent):

    assert isinstance(ag_self.owner, Motor)

    if ag_self.poll.Var[0] < 0:
        ag_self.owner.pv_by_name['.TWR'].value = 1
    else:
        ag_self.owner.pv_by_name['.TWF'].value = 1
    # poll.hold until it is forced on
    ag_self.poll.hold(for_cycles=-1, reset_var=True)
    return ra.StateLogics.Done, 'tweak is activated'


def move_to_aov(ag_self: ra.Agent):
    """This agent is intended to set the .VELO, and
    move to left or right based on requested signed tweak value

    inVar in this case is the requested signed tweak value, which
     can be set (forced) from other agents... """

    assert isinstance(ag_self.owner, Motor)

    if ag_self.poll.Var[1] > 0:
        # new value, new command!?
        ag_self.owner.pv_by_name['.VELO'].value = ag_self.poll.Var[1]
        ag_self.owner.pv_by_name['.STOP'].value = 1
        ag_self.act.hold(for_seconds=1, reset_var=False)
        return ra.StateLogics.Armed, 'set to move'
        # return False to indicate the agent is armed for action, but not done
    else:

        return ra.StateLogics.Idle, 'invalid request'


def move_to_aoa(ag_self: ra.Agent):

    assert isinstance(ag_self.owner, Motor)

    ag_self.owner.pv_by_name['.VAL'].value = ag_self.poll.Var[0]
    # poll.hold until it is forced on
    ag_self.poll.hold(for_cycles=-1, reset_var=True)

    return ra.StateLogics.Done, 'moving'


def pose_for_homing_poi(ag_self: ra.Agent):

    assert isinstance(ag_self.owner, Motor)

    homing_is_setup, msg = ag_self.owner.setup_homing()

    if not homing_is_setup:
        return ra.StateLogics.Invalid, msg

    # return preparation here ############################################
    if not ag_self.owner.do_homing_now:
        _r = {'homing_backoff_pos': None,
              'is_on_homing_position': None,
              'do_homing_now': ag_self.owner.do_homing_now
              }
        return _r, ''

    if 'moving' in ag_self.owner.status_ag.poll.Var:
        return ra.StateLogics.Invalid, ''

    if ag_self.owner.is_rotary:
        on_homing_position = True
        homing_backoff_pos = None
    elif ag_self.owner.homing_flag_user.value == 'Home switch/index':

        # TODO hardcoded move back timne
        homing_search_seconds = 5
        homing_backoff_pos = 0 - homing_search_seconds * ag_self.owner.homing_velocity_dial.value

        on_homing_position = abs(ag_self.owner.rbv_ag.poll.Var - homing_backoff_pos) < 5 * ag_self.owner.pos_prec_ag.poll.Var
    else:
        homing_backoff_pos = ag_self.owner.rbv_ag.poll.Var + ag_self.owner.homing_direction \
                             * (ag_self.owner.pv_by_name['.HLM'].value - ag_self.owner.pv_by_name['.LLM'].value)
        # on_homing_position = (ag_self.owner.on_homing_limit.value == 1)
        on_homing_position = (ag_self.owner.homing_limit_user.value == 1)

    _r = {'homing_backoff_pos': homing_backoff_pos,
          'is_on_homing_position': on_homing_position,
          'do_homing_now': ag_self.owner.do_homing_now
          }

    return _r, ''


def pose_for_homing_aov(ag_self: ra.Agent):

    assert isinstance(ag_self.owner, Motor)

    if not ag_self.poll.Var['do_homing_now']:
        return ra.StateLogics.Done, 'not homing'
    if ag_self.poll.Var['is_on_homing_position']:
        ag_self.poll.hold(for_cycles=-1)
        return ra.StateLogics.Done, 'on homing position'

    target = ag_self.poll.Var['homing_backoff_pos']
    # if there is a valid homing backoff target ten move to that
    if target:
        # now save and remove the soft limits

        ag_self.owner.saved_homing_soft_limit = ag_self.owner.homing_soft_limit.value
        if target * ag_self.owner.homing_direction > ag_self.owner.saved_homing_soft_limit * ag_self.owner.homing_direction:
            ag_self.owner.homing_soft_limit.value = ag_self.owner.saved_homing_soft_limit + ag_self.owner.homing_direction * 10000

        ag_self.owner.move_to_ag.poll.force([target, 10])
        return ra.StateLogics.Armed, ''

    return ra.StateLogics.Idle, ''


def pose_for_homing_aoa(ag_self: ra.Agent):

    assert isinstance(ag_self.owner, Motor)

    if ag_self.poll.Var['is_on_homing_position']:
        # preparation is done. in hold it.
        ag_self.poll.hold(for_cycles=-1)

        # now restore the soft limits
        ag_self.owner.homing_soft_limit.value = ag_self.owner.saved_homing_soft_limit

        return ra.StateLogics.Done, 'on homing position'
    else:
        # TODO timeout here
        return ra.StateLogics.Armed, ''

# ag definitions END


severity_ready_5 = 5
limit_severity_10 = 10
homing_severity_30 = 0
amp_severity_100 = 100


# motor class definition
class Motor(ra.Device):

    msta_bit_enum = {
        0: ['positive_actual_vel'],
        2: ['plus_limit_switch', limit_severity_10],
        3: ['home_limit_switch'],
        5: ['closed-loop'],
        7: ['at_home_pos'],
        11: ['supports_closed_loop'],
        8: ['encoder_connected'],

        1: ['not_done', 5, 'no_action', 1],
        10: ['moving', 7.5, 'no_action', 0],

        13: ['minus_limit_switch', limit_severity_10],
        14: ['not_homed', homing_severity_30, 'action_home_it', 1],
        6: ['slip/stall', 20, ':STOP.PROC'],
        12: ['comms/protection', 60],
        9: ['hw/protection', 90]
    }

    fault_bit_enum = {
        6: ['interlock', 40],  # ':INTERLOCKRESET.PROC'
        8: ['uninitialized', 50, ':INIT.PROC'],
        0: ['encoder_loss', 70, ':ELOSSRC.A'],
        5: ['wrong_limit', 80], #':WRONGLIMITRESET.PROC'
        1: ['amp_fault', amp_severity_100, ':AMPFAULTRESET'],
        2: ['macro_mech', amp_severity_100]
    }

    status_ref_dict = {
        '.MSTA': msta_bit_enum,
        ':FAULT': fault_bit_enum,
        ':USERHLS': {0: ['USERHLS', limit_severity_10, '.TWR']},
        ':USERLLS': {0: ['USERLLS', limit_severity_10, '.TWF']},
        ':KILLED': {0: ['KILLED', 1, ':STOP.PROC']},
        '.LVIO': {0: ['soft_limit', limit_severity_10]},
        ':HM_STATE': {7.0: ['homing_not_finished', homing_severity_30, 'homing_unsuccessful', 1]},
        ':HM_STATUS': {
            0.0: ['homing_status_Idle'],
            1.0: ['homing_status_Homing', homing_severity_30, 'homing_wait'],
            2.0: ['homing_status_Aborted', homing_severity_30, 'homing_unsuccessful'],
            3.0: ['homing_status_Timeout', homing_severity_30, 'homing_unsuccessful'],
            4.0: ['homing_status_FFErr', homing_severity_30, 'homing_unsuccessful'],
            5.0: ['homing_status_Limit', homing_severity_30, 'homing_unsuccessful'],
            6.0: ['homing_status_Incomplete', homing_severity_30, 'homing_unsuccessful'],
            7.0: ['homing_status_Invalid', homing_severity_30, 'homing_unsuccessful']
            # TODO restore severity to 30 to develop homing
        }
    }

    default_motor_fields = frozenset(default_motor_fields)

    def __init__(self, unit=None, is_rotary=False, **kwargs):

        super().__init__(**kwargs)
        self.dmDeviceType = 1

        self.master_config = {'msta_bit_enum': self.msta_bit_enum,
                       'fault_bit_enum': self.fault_bit_enum,
                       'status_ref_dict': self.status_ref_dict,
                       'default_motor_fields': self.default_motor_fields}

        self.is_rotary = is_rotary

        if self.auto_install_pvs is None:
            # user has not forced this value
            self.auto_install_pvs = True

        if unit:
            self.unit = unit

        self.default_dev_pvs = default_motor_fields
        # DONE (Low priority) remove the overriding method and use generic device method
        self.install_dev_pvs(**kwargs)

        # another method of adding PV's as objects of the motor....

        self.status_ag = ra.Agent(owner=self, first_name='status_ag', poll_in=ra.status_poi, verbose=_VERBOSE_)

        self.fault_ag = ra.Agent(owner=self, first_name='fault_ag', poll_in=ra.bit_stat, verbose=_VERBOSE_)
        self.fault_ag.stat_pv = ':FAULT'
        self.fault_ag.ref_list = self.fault_bit_enum

        self.can_init_ag = ra.Agent(owner=self, first_name='can_init_ag', poll_in=can_init_poi, verbose=_VERBOSE_)

        self.severity_ag = ra.SeverityAg(owner=self, first_name='severity_ag',
                                         poll_in=ra.severity_poi, act_on_valid=ra.severity_aov,
                                         act_on_armed=severity_aoa,
                                         verbose=_VERBOSE_)

        """       ----------------------------     """

        self.vel_ag = ra.Agent(owner=self, first_name='vel_ag', poll_in=vel_poi, unit=(self.unit + '/s'))

        self.rbv_ag = ra.Agent(owner=self, first_name='rbv_ag', poll_in=rbv_poi, unit=self.unit)

        self.tweak_val_ag = ra.Agent(owner=self, first_name='tweak_ag', poll_in=tweak_val_poi, unit=self.unit)

        self.max_scan_vel_ag = ra.Agent(owner=self, first_name='max_scan_vel_ag', poll_in=max_scan_vel_poi)

        self.pos_prec_ag = ra.Agent(owner=self, first_name='pos_prec_ag', initial_value=0.001, unit=self.rbv_ag.unit)
        # TODO hardcoded

        self.max_sync_time_ag = ra.Agent(owner=self, first_name='max_sync_time_ag', initial_value=0.1, unit='s')
        # TODO hardcoded

        self.rbv_err_ag = ra.Agent(owner=self, first_name='rbv_err_ag'
                                   , poll_in=rbv_err_poi
                                   , act_on_valid=rbv_err_aov
                                   , unit=self.rbv_ag.unit
                                   )

        self.tweak_ag = ra.Agent(owner=self, first_name='tweak_ag'
                                 # , poll_in=tweak_in
                                 # , act_on_invalid=tweak_aoi
                                 , act_on_valid=tweak_aov
                                 , act_on_armed=tweak_aoa
                                 , unit=self.rbv_ag.unit
                                 )
        self.tweak_ag.poll.hold(for_cycles=-1, reset_var=True)

        self.move_to_ag = ra.Agent(owner=self, first_name='move_to_ag',
                                   act_on_valid=move_to_aov,
                                   act_on_armed=move_to_aoa,
                                   unit=self.rbv_ag.unit)
        self.move_to_ag.poll.hold(for_cycles=-1, reset_var=True)

        #
        """Homing section"""

        self.pose_for_homing_ag = ra.Agent(owner=self, first_name='pose_for_homing_ag', verbose=_VERBOSE_)

        self.pose_for_homing_ag.setup(poll_in=pose_for_homing_poi,
                                       act_on_valid=pose_for_homing_aov,
                                       act_on_armed=pose_for_homing_aoa
                                       )
        self.pose_for_homing_ag.poll.hold(for_cycles=-1)


        """ Motor Record section """


        """ homing preparation 
        """

        pvs = [
            self.homing_velocity_dial,
            self.dir_flipped,
            self.dir_negative_user,
            self.homing_flag_user,
            self.save_position_proc,
            self.on_homing_limit,
            self.jog_velocity_set

        ] \
        = map(self.get_pv_by_name, \
              [':HOMEVEL',
               ':DIRFLIPPED',
               '.DIR',
               ':HOME_FLAG_USER.SVAL',
               ':SAVE_RAW.PROC',
               ':ON_HOME_LIMIT',
               '.VELO']
                )

        self.homing_soft_limit = None
        self.homing_limit_user = None
        self.homing_direction = None

        self.setup_homing()

        return

    def setup_homing(self):

        # these are orphan PV's. If there is no need for Agent functionality, just PV's
        #
        #############################################
        pvs = [
            self.homing_velocity_dial,
            self.dir_flipped,
            self.dir_negative_user,
            self.homing_flag_user,
            self.save_position_proc,
            self.on_homing_limit,
            self.jog_velocity_set
        ]

        # make sure all the information is available via pv's
        if any(pv is None for pv in pvs):
            return False, "PVs missing"

        self.homing_direction = ra.np.copysign(1, -self.homing_velocity_dial.value) \
                                         * (-1 if self.dir_flipped.value == 1 else 1)

                                         # * (-1 if self.dir_negative_user.value == 1 else 1)

        if self.is_rotary:
            # motor doesnt need to be moved... try homing from where you are

            self.homing_soft_limit = None
            self.homing_limit_user = None

        elif self.homing_direction == -1:
            self.homing_soft_limit = self.pv_by_name['.LLM']
            self.homing_limit_user = self.pv_by_name[':USERLLS']
            if self.homing_flag_user.value == 'High limit':
                return False, 'home direction and limit not consistent'
        elif self.homing_direction == 1:
            self.homing_soft_limit = self.pv_by_name['.HLM']
            self.homing_limit_user = self.pv_by_name[':USERHLS']
            if self.homing_flag_user.value == 'Low limit':
                return False, 'home direction and limit not consistent'

        return True, 'homing is setup'





# end of script
