#!/usr/bin/env python
#
# $File: //ASP/Personal/afsharn/wrasc/examples/rascan2_ra.py $
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


""" Rascan 2 Reactive Agents library
"""

from wrasc import reactive_agent as ra
from inspect import getmembers
from wrasc import ppmac_ra as ppra
import examples.ppmac_code_templates as tls
from os import path


class OL_RDB_Mlim(ra.Device):
    """
    base_config
    then test_config configures for the rdb_capture test
    the move on mlim and open loop home on mlim
    then jog insteps using step_until and log, to attack position
    then jog all the way back to mlim and log limit runover using slide_on and log
    then slide_off and capture readback at limit flag fall and log

    then repeat for n times

    Args:
        ra ([type]): [description]
    """

    def __init__(self, tst=None, _VERBOSE_=1, **kwargs):
        self.dmDeviceType = "OLRDBCapt"
        super().__init__(**kwargs)

        step_res = tst["Mot_A"]["step_res"] = (
            1
            / tst["Mot_A"]["fullsteps_per_rev"]
            / tst["Mot_A"]["micro_steps"]
            * tst["Mot_A"]["overall_egu_per_rev"]
        )
        enc_res = tst["Mot_A"]["encoder_res"]
        tst["Mot_A"]["smalljog_steps"] = tst["Mot_A"]["smalljog_egu"] / step_res
        tst["Mot_A"]["HomeOffset"] = tst["Mot_A"]["HomeOffset_EGU"] / step_res
        tst["Mot_A"]["attackpos_enc"] = (
            tst["Mot_A"]["attackpos_egu"] + tst["Mot_A"]["HomeOffset_EGU"]
        ) / enc_res
        tst["Mot_A"]["JogSpeed"] = tst["Mot_A"]["JogSpeed_EGU"] / step_res / 1000
        tst["Mot_A"]["HomeVel"] = tst["Mot_A"]["HomeVel_EGU"] / step_res / 1000
        clearance_enc = tst["clearance_egu"] / enc_res

        self.test_ppmac = ppra.PPMAC(
            tst["ppmac_hostname"], backward=tst["ppmac_is_backward"]
        )
        # it is possible to use multiple gpascii channels,
        # but we don't have a reason to do so, yet!

        pp_glob_dict = ppra.load_pp_globals(tst["ppglobal_fname"])
        with open(tst["baseconfig_fname"]) as f:
            base_config = f.read().splitlines()
            f.close

        # using a default set of parameters to log for each motor
        default_pass_logs = ppra.expand_globals(
            tls.log_main_n_companion, pp_glob_dict, **tst["Mot_A"]
        )

        ################################################################################################################
        # folowing section is defining wrasc agents for specific jobs. nothing happens untill the agents get processed #
        ################################################################################################################

        # -1 - check configuration

        # -------- motor A
        config_cmds = ppra.expand_globals(base_config, pp_glob_dict, **tst["Mot_A"])
        self.ma_base_config_ag = ppra.WrascPmacGate(
            owner=self,
            verbose=_VERBOSE_,
            ppmac=self.test_ppmac,
            **tst["Mot_A"],
            # validate / download calibration
            cry_cmds=config_cmds,
            cry_retries=2,
            # phase the motor
            celeb_cmds="#{L1}$",
        )

        # to ensure plc type config files take effect,
        # the config may need to be applied more than one time.
        # this is because some statements refer to other settings
        # which may change during download.
        # Also, some native ppmac settings will AUTOMATICALLY change others
        # e.g. EncType resets many related variables to their "type" default
        #
        # TODO : maybe consider downloading only the non-matching criteria...
        # and try as many times? or skip exact statements if they are lready verified?

        # -------------------------------------------------------------------

        # -------------------------------------------------------------------
        # 0 - check configuration
        # also add axis confix if there are deviations from baseConfig
        rev_enc_cmd = (
            ["PowerBrick[L2].Chan[L3].EncCtrl=7"]
            if tst["Mot_A"]["encoder_reversed"]
            else ["PowerBrick[L2].Chan[L3].EncCtrl=3"]
        )
        current_stat = ppra.expand_globals(
            ["full_current(L1)=1"], pp_glob_dict, **tst["Mot_A"]
        )
        self.ma_test_config_ag = ppra.WrascPmacGate(
            owner=self,
            verbose=_VERBOSE_,
            ppmac=self.test_ppmac,
            **tst["Mot_A"],
            cry_cmds=tls.config_rdb_capt
            + rev_enc_cmd
            + current_stat
            + ["Motor[L1].HomeOffset = {HomeOffset}"],
            celeb_cmds=[
                "%100",
                "#{L1}hm j/",  # puposedly fail homing to clear homed flag
                "#{L7}kill",
            ],
        )
        # -------------------------------------------------------------------
        # 0.1 - Move to MLIM
        self.ma_go_mlim_ag = ppra.WrascPmacGate(
            owner=self,
            verbose=_VERBOSE_,
            ppmac=self.test_ppmac,
            **tst["Mot_A"],
            pass_conds=tls.is_on_mlim_inpos,
            cry_cmds="#{L1}j-",
            wait_after_celeb=tst["Mot_A"]["limit_settle_time"],
            celeb_cmds=["#{L1}j-", "#{L7}kill"],
        )
        # -------------------------------------------------------------------
        # 0.2 - Home sliding off the limit
        self.ma_home_on_mlim_ag = ppra.WrascPmacGate(
            owner=self,
            verbose=_VERBOSE_,
            ppmac=self.test_ppmac,
            **tst["Mot_A"],
            pass_conds=["Motor[L1].HomeComplete==1"] + tls.is_off_limit_inpos,
            cry_cmds="#{L1}hm",
            celeb_cmds=["#{L7}kill"],
            wait_after_celeb=tst["Mot_A"]["limit_settle_time"],
        )
        # -------------------------------------------------------------------
        # 1 - settles at staring point
        self.ma_start_pos_ag = ppra.WrascPmacGate(
            owner=self,
            verbose=_VERBOSE_,
            ppmac=self.test_ppmac,
            **tst["Mot_A"],
            pass_conds=[
                "Motor[L1].InPos==1",
                "#{L7}p > {attackpos_enc} + Motor[L7].CapturedPos",
            ],
        )

        # -------------------------------------------------------------------
        # 1.1 - Step towards the staring point

        # -------- motor A
        self.ma_jog_until_ag = ppra.WrascPmacGate(
            owner=self,
            verbose=_VERBOSE_,
            ppmac=self.test_ppmac,
            **tst["Mot_A"],
            pass_conds="Motor[L1].InPos==1",
            celeb_cmds=["#{L1}jog:{smalljog_steps}"],
            pass_logs=default_pass_logs,
            csv_file_path=path.join("autest_out", "ma_small_until.csv"),
            ongoing=True,
            poll_pr=(
                lambda ag_self: not ag_self.owner.ma_start_pos_ag.inhibited
                and ag_self.owner.ma_start_pos_ag.poll.Var is False
            ),
        )

        # step until will be active everytime the self.ma_start_pos_ag is not on hold
        # self.ma_jog_until_ag.poll_pr = (
        #     lambda ag_self: not self.ma_start_pos_ag.inhibited and self.ma_start_pos_ag.poll.Var is False
        # )

        # -------------------------------------------------------------------
        # 2 - Move onto the minus limit and wait to stabilise,

        # -------- motor A
        self.ma_slide_on_mlim_ag = ppra.WrascPmacGate(
            owner=self,
            verbose=_VERBOSE_,
            ppmac=self.test_ppmac,
            **tst["Mot_A"],
            #
            pass_conds=tls.is_on_mlim_inpos,
            cry_cmds=["#{L1}jog-"],
            #
            pass_logs=default_pass_logs,
            csv_file_path=path.join("autest_out", "ma_slide_on_mlim.csv"),
            #
            celeb_cmds=["#{L7}kill"],
            wait_after_celeb=tst["Mot_A"]["limit_settle_time"],
        )

        # -------------------------------------------------------------------
        # 3 - Arm Capture and slide off for capturing the falling edge

        # -------- motor A
        self.ma_slide_off_mlim_ag = ppra.WrascPmacGate(
            owner=self,
            verbose=_VERBOSE_,
            ppmac=self.test_ppmac,
            **tst["Mot_A"],
            #
            pass_conds=tls.is_off_limit_inpos,
            cry_cmds=[
                "Motor[L1].JogSpeed={HomeVel}",
                "#{L7}j:{SlideOff_Dir}{slideoff_steps}",
                "Motor[L7].CapturePos=1",
                # "#{L1}j:{SlideOff_Dir}{slideoff_steps}",
                "#{L1}j=0",
            ],
            SlideOff_Dir="+",
            #
            pass_logs=default_pass_logs,
            csv_file_path=path.join("autest_out", "ma_slide_off_mlim.csv"),
            # resetting the changes in this action
            celeb_cmds=[
                "Motor[L1].JogSpeed={JogSpeed}",
                "PowerBrick[L2].Chan[L3].CountError=0",
            ],
            wait_after_celeb=tst["Mot_A"]["jog_settle_time"],
        )

        # -------------------------------------------------------------------

        # now setup a sequencer
        self.inner_loop_ag = ppra.WrascRepeatUntil(verbose=_VERBOSE_)
        # one cycle is already done so total number of repeats - 1 shall be repeated by the sequencer
        self.inner_loop_ag.repeats = tst["loop_repeats"] - 1
        self.inner_loop_ag.all_done_ag = self.ma_slide_off_mlim_ag
        self.inner_loop_ag.reset_these_ags = [
            self.ma_start_pos_ag,
            self.ma_slide_on_mlim_ag,
            self.ma_slide_off_mlim_ag,
        ]
        # ----------------------------------------------------------------------

        # -------------------------------------------------------------------
        # -------------------------------------------------------------------
        self.kill_on_collision_ag = ppra.WrascPmacGate(
            owner=self,
            verbose=_VERBOSE_,
            ppmac=self.test_ppmac,
            ongoing=True,
            pass_conds=[
                # clearance is low
                f"#11p > #12p + {clearance_enc}",
                # and it is decreasing
                f"Motor[3].ActVel - Motor[4].ActVel > 0",
            ],
            celeb_cmds=[f"#3,4 kill"],
        )

        def reset_after_kill(ag_self: ra.Agent):
            """    
            This aoa checks for collission zone condition. 
            celeb commands are
            This is an ongoing check, therefore never gets Done.

            Args:
                ag_self (ra.Agent): [description]

            Returns:
                [type]: [description]
            """
            print("KILLLED TO PREVENT COLLISION")

            return ra.StateLogics.Idle, "back to idle"

        self.kill_on_collision_ag.act_on_armed = reset_after_kill

        ################################################################################################################
        # folowing section is defining wrasc agents for specific jobs. nothing happens untill the agents get processed #
        ################################################################################################################

        # -------------------------------------------------------------------
        # set the forced sequence rules

        self.ma_test_config_ag.poll_pr = (
            lambda ag_self: ag_self.owner.ma_base_config_ag.is_done
        )
        self.ma_go_mlim_ag.poll_pr = (
            lambda ag_self: ag_self.owner.ma_test_config_ag.is_done
        )
        self.ma_home_on_mlim_ag.poll_pr = (
            lambda ag_self: ag_self.owner.ma_go_mlim_ag.is_done
        )

        # setup the sequence default dependency (can be done automaticatlly)
        self.ma_start_pos_ag.poll_pr = (
            lambda ag_self: ag_self.owner.ma_home_on_mlim_ag.is_done
        )

        self.ma_slide_on_mlim_ag.poll_pr = (
            lambda ag_self: ag_self.owner.ma_start_pos_ag.is_done
        )
        self.ma_slide_off_mlim_ag.poll_pr = (
            lambda ag_self: ag_self.owner.ma_slide_on_mlim_ag.is_done
        )
        # ----------------------------------------------------------------------


class OL_Rdb_Lim2Lim(ra.Device):
    """
    base_config
    then test_config configures for the rdb_capture test
    the move on mlim and open loop home on mlim
    then jog insteps using step_until and log, to attack position
    then jog all the way back to mlim and log limit runover using slide_on and log
    then slide_off and capture readback at limit flag fall and log

    then repeat for n times

    Args:
        ra ([type]): [description]
    """

    def __init__(self, tst=None, _VERBOSE_=1, **kwargs):
        self.dmDeviceType = "OLRDBCapt"
        super().__init__(**kwargs)

        step_res = tst["Mot_A"]["step_res"] = (
            1
            / tst["Mot_A"]["fullsteps_per_rev"]
            / tst["Mot_A"]["micro_steps"]
            * tst["Mot_A"]["overall_egu_per_rev"]
        )
        enc_res = tst["Mot_A"]["encoder_res"]
        tst["Mot_A"]["smalljog_steps"] = tst["Mot_A"]["smalljog_egu"] / step_res
        tst["Mot_A"]["bigjog_steps"] = tst["Mot_A"]["bigjog_egu"] / step_res

        tst["Mot_A"]["jog_step_ratio"] = (
            tst["Mot_A"]["bigjog_egu"] / tst["Mot_A"]["smalljog_egu"]
        )
        tst["Mot_A"]["HomeOffset"] = tst["Mot_A"]["HomeOffset_EGU"] / step_res
        tst["Mot_A"]["attackpos_enc"] = (
            tst["Mot_A"]["attackpos_egu"] + tst["Mot_A"]["HomeOffset_EGU"]
        ) / enc_res
        tst["Mot_A"]["JogSpeed"] = tst["Mot_A"]["JogSpeed_EGU"] / step_res / 1000
        tst["Mot_A"]["HomeVel"] = tst["Mot_A"]["HomeVel_EGU"] / step_res / 1000

        tst["Mot_A"]["fullrange_steps"] = tst["Mot_A"]["fullrange_egu"] / step_res

        clearance_enc = tst["clearance_egu"] / enc_res

        self.test_ppmac = ppra.PPMAC(
            tst["ppmac_hostname"], backward=tst["ppmac_is_backward"]
        )
        # it is possible to use multiple gpascii channels,
        # but we don't have a reason to do so, yet!

        pp_glob_dict = ppra.load_pp_globals(tst["ppglobal_fname"])
        with open(tst["baseconfig_fname"]) as f:
            base_config = f.read().splitlines()
            f.close

        # using a default set of parameters to log for each motor
        default_pass_logs = ppra.expand_globals(
            tls.log_main_n_companion, pp_glob_dict, **tst["Mot_A"]
        )

        ################################################################################################################
        # folowing section is defining wrasc agents for specific jobs. nothing happens untill the agents get processed #
        ################################################################################################################

        # -1 - check configuration
        # -------- motor A
        config_cmds = ppra.expand_globals(base_config, pp_glob_dict, **tst["Mot_A"])
        self.ma_base_config_ag = ppra.WrascPmacGate(
            owner=self,
            verbose=_VERBOSE_,
            ppmac=self.test_ppmac,
            **tst["Mot_A"],
            # validate / download calibration
            cry_cmds=config_cmds,
            cry_retries=2,
            # phase the motor
            celeb_cmds="#{L1}$",
        )

        # to ensure config files with high level language aspects take effect,
        # the config may need to be applied more than one time.
        # this is because some statements refer to other settings
        # which may change during download.
        # Also, some native ppmac settings will AUTOMATICALLY change others
        # e.g. EncType resets many related variables to their "type" default
        #
        # TODO : maybe consider downloading only the non-matching criteria...
        # and try as many times? or skip exact statements if they are lready verified?

        # -------------------------------------------------------------------

        # -------------------------------------------------------------------
        # 0 - check configuration
        # also add axis confix if there are deviations from baseConfig
        rev_enc_cmd = (
            ["PowerBrick[L2].Chan[L3].EncCtrl=7"]
            if tst["Mot_A"]["encoder_reversed"]
            else ["PowerBrick[L2].Chan[L3].EncCtrl=3"]
        )
        current_stat = ppra.expand_globals(
            ["full_current(L1)=1"], pp_glob_dict, **tst["Mot_A"]
        )
        self.ma_test_config_ag = ppra.WrascPmacGate(
            owner=self,
            verbose=_VERBOSE_,
            ppmac=self.test_ppmac,
            **tst["Mot_A"],
            cry_cmds=tls.config_rdb_capt
            + rev_enc_cmd
            + current_stat
            + ["Motor[L1].HomeOffset = {HomeOffset}"],
            celeb_cmds=[
                "%100",
                "#{L1}hm j/",  # puposedly fail homing to clear homed flag
                "#{L7}kill",
            ],
        )
        # -------------------------------------------------------------------
        # 0.1 - Move to MLIM
        self.ma_go_mlim_ag = ppra.WrascPmacGate(
            owner=self,
            verbose=_VERBOSE_,
            ppmac=self.test_ppmac,
            **tst["Mot_A"],
            pass_conds=tls.is_on_mlim_inpos,
            cry_cmds="#{L1}j-",
            wait_after_celeb=tst["Mot_A"]["limit_settle_time"],
            celeb_cmds=["#{L1}j-", "#{L7}kill"],
        )
        # -------------------------------------------------------------------
        # 0.2 - Home sliding off the limit
        self.ma_home_on_mlim_ag = ppra.WrascPmacGate(
            owner=self,
            verbose=_VERBOSE_,
            ppmac=self.test_ppmac,
            **tst["Mot_A"],
            pass_conds=["Motor[L1].HomeComplete==1"] + tls.is_off_limit_inpos,
            cry_cmds="#{L1}hm",
            celeb_cmds=["#{L7}kill"],
            wait_after_celeb=tst["Mot_A"]["limit_settle_time"],
        )
        # -------------------------------------------------------------------
        # 1 - Move onto the plus limit and wait to stabilise,

        # -------- motor A
        self.ma_slide_on_plim_ag = ppra.WrascPmacGate(
            owner=self,
            verbose=_VERBOSE_,
            ppmac=self.test_ppmac,
            **tst["Mot_A"],
            #
            pass_conds=tls.is_on_plim_inpos,
            # cry_cmds=["#{L1}jog+"],
            #
            pass_logs=default_pass_logs,
            csv_file_path=path.join("autest_out", "ma_slide_on_plim.csv"),
            #
            celeb_cmds=["#{L7}kill"],
            wait_after_celeb=tst["Mot_A"]["limit_settle_time"],
        )

        # -------- motor A
        self.ma_jog_pos_ag = ppra.WrascPmacGate(
            owner=self,
            verbose=_VERBOSE_,
            ppmac=self.test_ppmac,
            **tst["Mot_A"],
            wait_after_celeb=tst["Mot_A"]["jog_settle_time"],
            #
            pass_logs=default_pass_logs,
            csv_file_path=path.join("autest_out", "ma_jog_pos.csv"),
        )

        self.ma_jog_neg_ag = ppra.WrascPmacGate(
            owner=self,
            verbose=_VERBOSE_,
            ppmac=self.test_ppmac,
            **tst["Mot_A"],
            wait_after_celeb=tst["Mot_A"]["jog_settle_time"],
            #
            pass_logs=default_pass_logs,
            csv_file_path=path.join("autest_out", "ma_jog_neg.csv"),
        )

        self.ma_slide_off_plim_ag = ppra.WrascPmacGate(
            owner=self,
            verbose=_VERBOSE_,
            ppmac=self.test_ppmac,
            **tst["Mot_A"],
            #
            pass_conds=tls.is_off_limit_inpos,
            cry_cmds=[
                "Motor[L1].JogSpeed={HomeVel}",
                "#{L7}j:{SlideOff_Dir}{slideoff_steps}",
                "Motor[L7].CapturePos=1",
                "#{L1}j={fullrange_steps}",
            ],
            SlideOff_Dir="-",
            cry_retries=1,
            #
            pass_logs=default_pass_logs,
            csv_file_path=path.join("autest_out", "ma_slide_off_plim.csv"),
            # resetting the changes in this action
            celeb_cmds=[
                "Motor[L1].JogSpeed={JogSpeed}",
                "PowerBrick[L2].Chan[L3].CountError=0",
            ],
            wait_after_celeb=tst["Mot_A"]["jog_settle_time"],
        )

        # -------------------------------------------------------------------
        # 2 - Move onto the minus limit and wait to stabilise,

        # -------- motor A
        self.ma_slide_on_mlim_ag = ppra.WrascPmacGate(
            owner=self,
            verbose=_VERBOSE_,
            ppmac=self.test_ppmac,
            **tst["Mot_A"],
            #
            pass_conds=tls.is_on_mlim_inpos,
            # cry_cmds=["#{L1}jog-"],
            #
            pass_logs=default_pass_logs,
            csv_file_path=path.join("autest_out", "ma_slide_on_mlim.csv"),
            #
            celeb_cmds=["#{L7}kill"],
            wait_after_celeb=tst["Mot_A"]["limit_settle_time"],
        )

        # -------------------------------------------------------------------
        # 3 - Arm Capture and slide off for capturing the falling edge

        # -------- motor A
        self.ma_slide_off_mlim_ag = ppra.WrascPmacGate(
            owner=self,
            verbose=_VERBOSE_,
            ppmac=self.test_ppmac,
            **tst["Mot_A"],
            #
            pass_conds=tls.is_off_limit_inpos,
            cry_cmds=[
                "Motor[L1].JogSpeed={HomeVel}",
                "#{L7}j:{SlideOff_Dir}{slideoff_steps}",
                "Motor[L7].CapturePos=1",
                # "#{L1}j:{SlideOff_Dir}{slideoff_steps}",
                "#{L1}j=0",
            ],
            SlideOff_Dir="+",
            #
            pass_logs=default_pass_logs,
            csv_file_path=path.join("autest_out", "ma_slide_off_mlim.csv"),
            # resetting the changes in this action
            celeb_cmds=[
                "Motor[L1].JogSpeed={JogSpeed}",
                "PowerBrick[L2].Chan[L3].CountError=0",
            ],
            wait_after_celeb=tst["Mot_A"]["jog_settle_time"],
        )

        # -------------------------------------------------------------------
        self.kill_on_collision_ag = ppra.WrascPmacGate(
            owner=self,
            verbose=_VERBOSE_,
            ppmac=self.test_ppmac,
            ongoing=True,
            pass_conds=[
                # clearance is low
                f"#11p > #12p + {clearance_enc}",
                # and it is decreasing
                f"Motor[3].ActVel - Motor[4].ActVel > 0",
            ],
            celeb_cmds=[f"#3,4 kill"],
        )

        def reset_after_kill(ag_self: ra.Agent):
            """    
            This aoa checks for collission zone condition. 
            celeb commands are
            This is an ongoing check, therefore never gets Done.

            Args:
                ag_self (ra.Agent): [description]

            Returns:
                [type]: [description]
            """
            print("KILLLED TO PREVENT COLLISION")

            return ra.StateLogics.Idle, "back to idle"

        self.kill_on_collision_ag.act_on_armed = reset_after_kill

        ################################################################################################################
        # folowing section is defining wrasc agents for specific jobs. nothing happens untill the agents get processed #
        ################################################################################################################

        # -------------------------------------------------------------------
        # set the forced sequence rules

        self.ma_test_config_ag.poll_pr = (
            lambda ag_self: ag_self.owner.ma_base_config_ag.is_done
        )
        self.ma_go_mlim_ag.poll_pr = (
            lambda ag_self: ag_self.owner.ma_test_config_ag.is_done
        )
        self.ma_home_on_mlim_ag.poll_pr = (
            lambda ag_self: ag_self.owner.ma_go_mlim_ag.is_done
        )

        # self.ma_start_pos_ag.poll_pr = lambda ag_self: False

        self.ma_jog_pos_ag.poll_pr = lambda ag_self: True

        # everything below the first line are excluded from dependency compilation
        # due to a BUG in reactive_agent ! otherwise the forwards and back would
        # create an illegal circular dependency
        # setup the sequence default dependency (can be done automaticatlly)
        self.ma_slide_on_plim_ag.poll_pr = (
            lambda ag_self: ag_self.owner.ma_home_on_mlim_ag.is_done
        )

        self.ma_slide_off_plim_ag.poll_pr = (
            lambda ag_self: ag_self.owner.ma_slide_on_plim_ag.is_done
        )

        self.ma_slide_on_mlim_ag.poll_pr = (
            lambda ag_self: ag_self.owner.ma_slide_off_plim_ag.is_done
        )
        self.ma_slide_off_mlim_ag.poll_pr = (
            lambda ag_self: ag_self.owner.ma_slide_on_mlim_ag.is_done
        )

        # ----------------------------------------------------------------------

    def jog_agent(self, jog_dest, is_positive_jog):

        if is_positive_jog:
            ineq = ">" + str(jog_dest) + " - 10"
            jog_agent = self.ma_jog_pos_ag
        else:
            ineq = "<" + str(jog_dest) + " + 10"
            jog_agent = self.ma_jog_neg_ag

        jog_agent.setup(
            cry_cmds="#{L1}jog=" + str(jog_dest), pass_conds="#{L1}p" + ineq,
        )

        return jog_agent


class SmarGonTestAgents(ra.Device):
    def __init__(self, tst=None, out_path="sg_out", _VERBOSE_=1, **kwargs):
        self.dmDeviceType = "OLRDBCapt"
        self.smargon_ppmac = ppra.PPMAC(tst["ppmac_hostname"], backward=True)

        default_pass_logs = [
            # readback capture via companion axis
            "Motor[3].CapturedPos",
            "Motor[4].CapturedPos",
            # readback and step position at stop position
            "#3p",
            "#4p",
            # test condition parameter
            "Motor[3].JogSpeed",
            "Motor[4].JogSpeed",
            # position references
            "Motor[3].HomePos",
            "Motor[4].HomePos",
            # Check these for errors
            "Motor[3].TriggerNotFound",
            "Motor[4].TriggerNotFound",
            "Gate3[0].Chan[2].CountError",
            "Gate3[0].Chan[3].CountError",
            "Motor[3].DacLimit",
            "Motor[4].DacLimit",
        ]

        self.out_path = out_path

        super().__init__(**kwargs)

        # -------------------------------------------------------------------
        # Jog outer motor
        # -------- motorB
        # self.jog_outer_ag = ppra.WrascPmacGate(
        #     owner=self,
        #     verbose=_VERBOSE_,
        #     ppmac=self.smargon_ppmac,
        #     **tst["Mot_Outer"],
        #     wait_after_celeb=tst["Mot_Outer"]["jog_settle_time"],
        #     #
        #     pass_logs=default_pass_logs,
        #     csv_file_path=path.join(self.out_path, "jog_outer_ag.csv"),
        # )

        # self.jog_inner_ag = ppra.WrascPmacGate(
        #     owner=self,
        #     verbose=_VERBOSE_,
        #     ppmac=self.smargon_ppmac,
        #     **tst["Mot_Inner"],
        #     wait_after_celeb=tst["Mot_Inner"]["jog_settle_time"],
        #     #
        #     pass_logs=default_pass_logs,
        #     csv_file_path=path.join(self.out_path, "jog_inner_ag.csv"),
        # )

        # if not on the switch, and already Captured postition then protect
        # 0 - check configuration
        # also add axis confix if there are deviations from baseConfig
        self.setaux_inner_ag = ppra.WrascPmacGate(
            owner=self,
            verbose=_VERBOSE_,
            ppmac=self.smargon_ppmac,
            **tst["Mot_Inner"],
            cry_cmds=[
                "Motor[L1].pAuxFault = Acc65E[0].DataReg[0].a",
                "Motor[L1].AuxFaultBit = 8",
                "Motor[L1].AuxFaultLevel = 0",
            ],
        )

        # -------- motor A
        self.slide_inner_on_aux_ag = ppra.WrascPmacGate(
            owner=self,
            verbose=_VERBOSE_,
            ppmac=self.smargon_ppmac,
            **tst["Mot_Inner"],
            #
            pass_conds=["Motor[L1].AuxFault > 0",],
            cry_cmds=["#{L1}jog-"],
            #
            pass_logs=default_pass_logs,
            csv_file_path=path.join(self.out_path, "slide_inner_on_aux_ag.csv"),
            #
            celeb_cmds=["#{L1}j/"],
            wait_after_celeb=tst["Mot_Inner"]["limit_settle_time"],
        )

        self.setaux_capture_inner_ag = ppra.WrascPmacGate(
            owner=self,
            verbose=_VERBOSE_,
            ppmac=self.smargon_ppmac,
            **tst["Mot_Inner"],
            cry_cmds=[
                "Motor[L1].pCaptFlag = Motor[L1].pAuxFault",
                "Motor[L1].CaptFlagBit = 8",  # + 0 //8 for bit 0
                "Motor[L1].AuxFaultLevel = 0",
            ],
            # and reset the Aux protection off
            celeb_cmds=[
                "Motor[L1].pAuxFault = 0",
                "Motor[L1].AuxFaultBit = 0",
                "Motor[L1].AuxFaultLevel = 0",
                "Motor[L1].CaptureMode = 1",
            ],
        )

        self.slide_inner_off_aux_ag = ppra.WrascPmacGate(
            owner=self,
            verbose=_VERBOSE_,
            ppmac=self.smargon_ppmac,
            **tst["Mot_Inner"],
            #
            pass_conds=["Motor[L1].AuxFault==0", "Motor[L1].InPos>0",],
            cry_cmds=[
                "Motor[L1].JogSpeed={HomeVel}",
                "#{L1}j:{SlideOff_Dir}{slideoff_egu}^0",
                "Motor[L1].CapturePos=1",
            ],
            SlideOff_Dir="+",
            #
            pass_logs=default_pass_logs,
            csv_file_path=path.join(self.out_path, "slide_inner_off_aux.csv"),
            # resetting the changes in this action
            celeb_cmds=[
                # and resets the encoder count errors
                "Gate3[L2].Chan[L3].CountError=0",
            ],
            wait_after_celeb=tst["Mot_Inner"]["jog_settle_time"],
        )

        self.reset_capture_inner_ag = ppra.WrascPmacGate(
            owner=self,
            verbose=_VERBOSE_,
            ppmac=self.smargon_ppmac,
            **tst["Mot_Inner"],
            cry_cmds=[
                "Motor[L1].CaptureMode = 0",
                "Motor[L1].pCaptFlag = Acc24E3[L2].Chan[L3].Status.a",
                "Motor[L1].pCaptPos = Acc24E3[L2].Chan[L3].HomeCapt.a",
                "Motor[L1].CaptFlagBit = 20",
                # don't capture if its not done at flag fall:
                "Motor[L1].CapturePos = 0",
                # and restore JogSpeed
                "Motor[L1].JogSpeed={JogSpeed}",
            ],
        )


if __name__ == "__main__":
    pass

