from inspect import getmembers, isdatadescriptor
from os import path

from wrasc import reactive_agent as ra
from wrasc import ppmac_ra as ppra
import motion_modules.ppmac_code_templates as tls


class OLRdbLim2Lim(ra.Device):
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

    def __init__(self, tst=None, _VERBOSE_=1, motor_id="Mot_A", **kwargs):
        self.dmDeviceType = "OLRDBCapt"
        super().__init__(**kwargs)

        self.motor_id = motor_id

        self.test_ppmac = ppra.PPMAC(
            tst["ppmac_hostname"], backward=tst["ppmac_is_backward"]
        )

        pp_glob_dict = ppra.load_pp_globals(tst["ppglobal_fname"])

        if path.exists(tst["baseconfig_fname"]):
            with open(tst["baseconfig_fname"]) as f:
                base_config = f.read().splitlines()

            # using a default set of parameters to log for each motor
            default_pass_logs = ppra.expand_globals(
                tls.log_main_n_companion, pp_glob_dict, **tst[self.motor_id]
            )

        pp_glob_dict = ppra.load_pp_globals(tst["ppglobal_fname"])

        if path.exists(tst["sysconfig_fname"]):
            with open(tst["sysconfig_fname"]) as f:
                system_config = f.read().splitlines()

        ################################################################################################################
        # folowing section is defining wrasc agents for specific jobs. nothing happens untill the agents get processed #
        ################################################################################################################

        # -2 - check configuration
        # -------- motor A
        system_cmds = ppra.expand_globals(
            system_config, pp_glob_dict, **tst[self.motor_id]
        )
        self.system_config_ag = ppra.WrascPmacGate(
            owner=self,
            verbose=_VERBOSE_,
            ppmac=self.test_ppmac,
            **tst[self.motor_id],
            # validate / download calibration
            pass_conds=ppra.stats_to_conds(system_cmds),
            cry_cmds=system_cmds,
            cry_retries=2,
        )

        # -1 - check configuration
        # -------- motor A
        config_cmds = ppra.expand_globals(
            base_config, pp_glob_dict, **tst[self.motor_id]
        )
        self.ma_base_config_ag = ppra.WrascPmacGate(
            owner=self,
            verbose=_VERBOSE_,
            ppmac=self.test_ppmac,
            **tst[self.motor_id],
            # validate / download base configuration
            pass_conds=ppra.stats_to_conds(config_cmds),
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
            if tst[self.motor_id]["encoder_reversed"]
            else ["PowerBrick[L2].Chan[L3].EncCtrl=3"]
        )
        current_stat = ppra.expand_globals(
            ["full_current(L1)=1"], pp_glob_dict, **tst[self.motor_id]
        )
        self.ma_test_config_ag = ppra.WrascPmacGate(
            owner=self,
            verbose=_VERBOSE_,
            ppmac=self.test_ppmac,
            **tst[self.motor_id],
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
            **tst[self.motor_id],
            pass_conds=tls.is_on_mlim_inpos,
            cry_cmds="#{L1}j-",
            wait_after_celeb=tst[self.motor_id]["limit_settle_time"],
            celeb_cmds=["#{L1}j-", "#{L7}kill"],
        )
        # -------------------------------------------------------------------
        # 0.2 - Home sliding off the limit
        self.ma_home_on_mlim_ag = ppra.WrascPmacGate(
            owner=self,
            verbose=_VERBOSE_,
            ppmac=self.test_ppmac,
            **tst[self.motor_id],
            pass_conds=["Motor[L1].HomeComplete==1"] + tls.is_off_limit_inpos,
            cry_cmds="#{L1}hm",
            celeb_cmds=["#{L7}kill", "Motor[L7].HomePos=Motor[L7].Pos"],
            wait_after_celeb=tst[self.motor_id]["limit_settle_time"],
        )
        # -------------------------------------------------------------------
        # 1 - Move onto the plus limit and wait to stabilise,

        # -------- motor A
        self.ma_slide_on_plim_ag = ppra.WrascPmacGate(
            owner=self,
            verbose=_VERBOSE_,
            ppmac=self.test_ppmac,
            **tst[self.motor_id],
            #
            pass_conds=tls.is_on_plim_inpos,
            # cry_cmds=["#{L1}jog+"],
            #
            pass_logs=default_pass_logs,
            csv_file_path=path.join(tst["csv_out_folder"], "ma_slide_on_plim.csv"),
            #
            celeb_cmds=["#{L7}kill"],
            wait_after_celeb=tst[self.motor_id]["limit_settle_time"],
        )

        # -------- motor A
        self.ma_jog_pos_ag = ppra.WrascPmacGate(
            owner=self,
            verbose=_VERBOSE_,
            ppmac=self.test_ppmac,
            **tst[self.motor_id],
            wait_after_celeb=tst[self.motor_id]["jog_settle_time"],
            #
            pass_logs=default_pass_logs,
            csv_file_path=path.join(tst["csv_out_folder"], "ma_jog_pos.csv"),
        )

        self.ma_jog_neg_ag = ppra.WrascPmacGate(
            owner=self,
            verbose=_VERBOSE_,
            ppmac=self.test_ppmac,
            **tst[self.motor_id],
            wait_after_celeb=tst[self.motor_id]["jog_settle_time"],
            #
            pass_logs=default_pass_logs,
            csv_file_path=path.join(tst["csv_out_folder"], "ma_jog_neg.csv"),
        )

        self.ma_slide_off_plim_ag = ppra.WrascPmacGate(
            owner=self,
            verbose=_VERBOSE_,
            ppmac=self.test_ppmac,
            **tst[self.motor_id],
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
            csv_file_path=path.join(tst["csv_out_folder"], "ma_slide_off_plim.csv"),
            # resetting the changes in this action
            celeb_cmds=[
                "Motor[L1].JogSpeed={JogSpeed}",
                "PowerBrick[L2].Chan[L3].CountError=0",
            ],
            wait_after_celeb=tst[self.motor_id]["jog_settle_time"],
        )

        # -------------------------------------------------------------------
        # 2 - Move onto the minus limit and wait to stabilise,

        # -------- motor A
        self.ma_slide_on_mlim_ag = ppra.WrascPmacGate(
            owner=self,
            verbose=_VERBOSE_,
            ppmac=self.test_ppmac,
            **tst[self.motor_id],
            #
            pass_conds=tls.is_on_mlim_inpos,
            # cry_cmds=["#{L1}jog-"],
            #
            pass_logs=default_pass_logs,
            csv_file_path=path.join(tst["csv_out_folder"], "ma_slide_on_mlim.csv"),
            #
            celeb_cmds=["#{L7}kill"],
            wait_after_celeb=tst[self.motor_id]["limit_settle_time"],
        )

        # -------------------------------------------------------------------
        # 3 - Arm Capture and slide off for capturing the falling edge

        # -------- motor A
        self.ma_slide_off_mlim_ag = ppra.WrascPmacGate(
            owner=self,
            verbose=_VERBOSE_,
            ppmac=self.test_ppmac,
            **tst[self.motor_id],
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
            csv_file_path=path.join(tst["csv_out_folder"], "ma_slide_off_mlim.csv"),
            # resetting the changes in this action
            celeb_cmds=[
                "Motor[L1].JogSpeed={JogSpeed}",
                "PowerBrick[L2].Chan[L3].CountError=0",
            ],
            wait_after_celeb=tst[self.motor_id]["jog_settle_time"],
        )

        # -------------------------------------------------------------------
        self.kill_on_collision_ag = ppra.WrascPmacGate(
            owner=self,
            verbose=_VERBOSE_,
            ppmac=self.test_ppmac,
            ongoing=True,
            pass_conds=False,
            # [
            #     # clearance is low
            #     f"#11p > #12p + {clearance_enc}",
            #     # and it is decreasing
            #     f"Motor[3].ActVel - Motor[4].ActVel > 0",
            # ],
            celeb_cmds=[f"#3,4 kill"],
        )

        self.prog10_code = "OPEN PROG 10\nLINEAR\nABS\nTM(Q70)\nA(Q71)B(Q72)C(Q73)X(Q77)Y(Q78)Z(Q79)\nDWELL0\nCLOSE".splitlines()
        self.plc10_code = 'disable plc 10\nopen plc 10\nif (Plc[3].Running==0)\n{\n    cmd "&1p q81=d0 q82=d1 q83=d2 q84=d3 q85=d4 q86=d5 q87=d6 q88=d7 q89=d8"\n}\nclose\nenable plc 10'.splitlines()
        self.limit_cond = "Motor[6].pLimits=0".splitlines()

        self.set_initial_setup_ag = ppra.WrascPmacGate(
            owner=self,
            verbose=_VERBOSE_,
            ppmac=self.test_ppmac,
            pass_conds=[],  # means pass anyways
            celeb_cmds=self.prog10_code + self.plc10_code,
        )

        self.set_wpKey_ag = ppra.WrascPmacGate(
            owner=self,
            verbose=_VERBOSE_,
            ppmac=self.test_ppmac,
            cry_cmds=["sys.WpKey=$AAAAAAAA"],
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

        self.system_config_ag.poll_pr = (
            lambda ag_self: ag_self.owner.set_wpKey_ag.is_done
        )

        self.ma_base_config_ag.poll_pr = (
            lambda ag_self: ag_self.owner.system_config_ag.is_done
        )

        self.ma_test_config_ag.poll_pr = (
            lambda ag_self: ag_self.owner.ma_base_config_ag.is_done or True
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
            ineq = ">" + str(jog_dest) + " - 0.001"
            jog_agent = self.ma_jog_pos_ag
        else:
            ineq = "<" + str(jog_dest) + " + 0.001"
            jog_agent = self.ma_jog_neg_ag

        jog_agent.setup(
            cry_cmds="#{L1}jog=" + str(jog_dest), pass_conds="#{L1}p" + ineq,
        )

        return jog_agent


if __name__ == "__main__":
    pass

