#!/usr/bin/env python
#
# $File: //ASP/Personal/afsharn/wrasc/examples/dynap_ra.py $
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


""" Dynamic Aperture Reactive Agents library
"""

from wrasc import reactive_agent as ra
from inspect import getmembers


class DynAp(ra.Device):

    def __init__(self, unit=None, scan_ctrl_spmg=':MOTOR_Z.SPMG', scan_ctrl_prefix='SR08ID01ROB01', **kwargs):

        self.dmDeviceType = 'DYNAP'
        self.default_dev_prefix = ':DYNAP'
        self.default_dev_pvs = None

        super().__init__(**kwargs)

        # self.in_position_ag = ra.Agent(owner=self, poll_in=ra.get_in_pv, verbose=1)

        self.cs_number_ag = ra.Agent(owner=self, act_on_valid=ra.put_out_pv, act_on_invalid=ra.reset_out_pv, verbose=1)
        self.r_req_q20_ag = ra.Agent(owner=self, act_on_valid=ra.put_out_pv, act_on_invalid=ra.reset_out_pv, verbose=1)
        self.r_mask_q21_ag = ra.Agent(owner=self, act_on_valid=ra.put_out_pv, act_on_invalid=ra.reset_out_pv, verbose=1)

        if self.dev_prefix is None:
            self.dev_prefix = self.default_dev_prefix

        # just setting eprefix and dev_prefix if there was no pv_list in kwargs
        self.install_dev_pvs(**kwargs)

        # setting agent pv's for ALL Agents which are defined BEFORE this point
        self.set_ag_pvs()

        self.scan_spmg_ag = ra.Agent(owner=self, act_on_valid=ra.put_out_pv, act_on_invalid=ra.reset_out_pv, verbose=1)
        self.scan_spmg_ag.install_pvs(owner=self, outpvname=scan_ctrl_spmg, dev_prefix='', eprefix=scan_ctrl_prefix)

    def set_ag_pvs(self):

        names = [memb[0] for memb in getmembers(self)]
        ag_names = [nam for nam in names if nam.endswith('_ag')]
        pv_names = [':' + nam.strip('_ag').upper() for nam in ag_names]

        if self.eprefix is not None\
            and self.dev_prefix is not None\
            and len(pv_names) > 0:

            for pvname in pv_names:
                agname = pvname.strip(':').lower() + '_ag'
                # TODO : check: only set the PV names if they are not already set
                exec_str = "self.{0}.install_pvs(inpvname='{1}', outpvname='{1}', dev_prefix='{2}', eprefix='{3}')"\
                    .format(agname, pvname, self.dev_prefix, self.eprefix)
                exec(exec_str)


if __name__ == '__main__':
    pass

