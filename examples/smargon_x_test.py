
import os
from time import sleep
import yaml as ym
import regex as re

""" example context managed powerpmac read"""
from ppmac import GpasciiClient

ppmac_test_IP = os.environ["PPMAC_TEST_IP"]
p4_root = "/beamline/perforce"
source_file_path = os.path.normpath(r"opa/mx1/ctrls/SR03BM01MCS22/Project/PMAC Script Language/PLC Programs")

def stage_and_verify(ppmac=None, cmds=None, manual_learning=False, verify_conds=None, base_dir="", stage_name=None, base_ext=".ppmc"):
   
    stage_counter = 0

    assert isinstance(cmds, list)
    if stage_name:
        _filename = "stage_" + stage_name
    elif len(cmds) == 1:
        _filename = cmds[0][0:40]
    else:
        raise RuntimeError("stage name is not defined. (multiple commands) ")
    stage_counter += 1

    _filename = _filename.replace(" ", "_").replace(",", "-").replace(".", "-")
    _filename = re.sub('[^\w\s-]', '', _filename).strip()
    legit_filename = re.sub('[-\s]+', '-', _filename)
    base_filename = os.path.join(base_dir, legit_filename)
    ref_filename = base_filename + base_ext + ".ref"
    dump_filename = base_filename + base_ext + ".loaded"

    tpl = []
    for cmd in cmds:
        tpl += ppmac.send_receive_raw(cmd)[0]

    if manual_learning:

        # overwrite the ref file
        with open(ref_filename, 'w+') as reffile:
            ym.dump(tpl, reffile, default_flow_style=False)
            reffile.close()        

    elif os.path.exists(ref_filename):

        with open(ref_filename, 'r') as reffile:
            loaded_ref = ym.load(reffile, Loader=ym.FullLoader)
            reffile.close()
        
        if tpl != loaded_ref:
            with open(dump_filename, 'w+') as reffile:
                ym.dump(tpl, reffile, default_flow_style=False)
                reffile.close()            
            raise RuntimeError("ERROR encountered staging " + stage_name + " stage. Compare " + dump_filename + " vs " + ref_filename)
    else:
        raise RuntimeError("No reference file for stage" + stage_name)

    if verify_conds is None:
        return stage_name + " -- staged and confirmed."
    
    # the stage commands respons is matching, now verify the conditions

    assert isinstance(verify_conds, list)

    for condition in verify_conds:
        assert isinstance(condition, list)
        assert len(condition) == 3
        cmd, logic_op, value_ref = condition

        tpl = ppmac.send_receive_raw(cmd)
        value_loaded = tpl[0][1].strip("\n").strip(" ")
        value_loaded = value_loaded.split("=")[-1]

        if type(value_ref) == str:
            value_ref = f"'{value_ref}'"
            value_loaded = f"'{value_loaded}'"

        verify_text = f"{value_loaded} {logic_op} {value_ref}"

        assert eval(verify_text) is True

    return f"{stage_name} -- staged, confirmed and {len(verify_conds)} conditions verified."

#  export PPMAC_TEST_IP="10.23.92.220"

with GpasciiClient(ppmac_test_IP) as smargon:
    smargon.connect()
    # while True:

    # setp 1 : preparation of the test


    def load_from_file(plc_file_name = "") :

        manual_learning = True
        
        plc_file = os.path.join(p4_root, source_file_path, plc_file_name)

        if not os.path.exists(plc_file):
            raise RuntimeError(f"loading file not found: {plc_file}")

        with open(plc_file, 'r') as plcfile:
            plc_code = plcfile.read()
            cmds = [plc_code]
            plcfile.close

        print(stage_and_verify(smargon, stage_name=f"loading {plc_file_name}", cmds=cmds, manual_learning=manual_learning))
    
    load_from_file("30_test_set.plc")
    load_from_file("31_test_unset.plc")

    manual_learning = True

    cmds = ["LIST PLC 30,0,100", "LIST PLC 31,0,100", "Motor[3].AuxFault", "Motor[3].JogSpeed", "Motor[3].DesVelZero"]
    verifies = [["#3p", ">", 980]]
    print(stage_and_verify(smargon, stage_name="initial", cmds=cmds, manual_learning=manual_learning, verify_conds=verifies))

    # setp 2 : loop
    
    manual_learning = True

    cmds = ["enable PLC 30"]
    verifies =[["Motor[3].pAuxFault", "==", "Acc65E[0].DataReg[0].a"]]
    print(stage_and_verify(smargon, stage_name="set_protection", cmds=cmds, manual_learning=manual_learning, verify_conds=verifies))

    manual_learning = False

    exit(0)
    cmds = ["#3 j: -1100", "Motor[3].pAuxFault"]
    print(stage_and_verify(smargon, stage_name="set_move", cmds=cmds, manual_learning=manual_learning))



print("complete.")
