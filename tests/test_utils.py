import utils as ut
import pytest


epics_motor_field_fs = [
    [r"SR\d\d", ""],  # Section designator, starts with "SR"
    [r"ID\d\d", ""],  # ID designator starts with "ID"
    [r"[A-Z]{3}\d\d[:]{1}", ""],  # Device designator, ends with ":"
    [r"[\w_]+", ""],  # Motor () designator
    [r"[.:]{1}[\w]+", ""],  # Motor field, starts with either "." or ":"
]


def test_sh_no_ditto():

    # first shorthand without dittos. it is dangerously flexible!
    sh_noditto = ut.ShortHand(group_formats=epics_motor_field_fs)

    assert (
        sh_noditto.full_expression
        == r"(SR\d\d)*(ID\d\d)*([A-Z]{3}\d\d[:]{1})*([\w_]+)*([.:]{1}[\w]+)*"
    )
    assert len(sh_noditto.text_groups) == 5

    # attempting a shorthand conversation prior to a complete sentence is illegal
    with pytest.raises(Exception) as e_info:
        assert sh_noditto.long("ID04DEV04:MOT_04.IPV") == "SR05ID04DEV04:MOT_04.IPV"
    print(f"\n Expected exception: {e_info.value.args[0]}")

    # full sentence
    assert sh_noditto.long("SR05ID01DEV02:MOT01.PVA") == "SR05ID01DEV02:MOT01.PVA"

    # different shorthands, FREELY being replaced. Success of this depoends on
    # shorthands strictly following the convention

    assert sh_noditto.long("MOT_02") == "SR05ID01DEV02:MOT_02.PVA"
    assert sh_noditto.long(":XPV") == "SR05ID01DEV02:MOT_02:XPV"
    assert sh_noditto.long("MOT_03.IPV") == "SR05ID01DEV02:MOT_03.IPV"
    assert sh_noditto.long("DEV03:") == "SR05ID01DEV03:MOT_03.IPV"
    assert sh_noditto.long("ID04DEV04:MOT_04.IPV") == "SR05ID04DEV04:MOT_04.IPV"
    assert sh_noditto.long("SR06") == "SR06ID04DEV04:MOT_04.IPV"


def test_sh_pre_ditto():
    # pre-dittoed shorthands are safer to use. they expect ditto char placeholders for missing prefixes
    sh_pre_ditto = ut.ShortHand(group_formats=epics_motor_field_fs, pre_dittos=True)

    # complete sentence
    assert sh_pre_ditto.long("SR05ID01DEV02:MOT01.PVA") == "SR05ID01DEV02:MOT01.PVA"
    #
    with pytest.raises(Exception) as e_info:
        assert sh_pre_ditto.long("MOT_02") == "SR05ID01DEV02:MOT_02.PVA"
    assert str(e_info.value.args[0]).startswith("pre_dittos")
    # print(f"\n Expected exception: {e_info.value.args[0]}")

    with pytest.raises(Exception) as e_info:
        assert sh_pre_ditto.long("//MOT_02") == "SR05ID01DEV02:MOT_02.PVA"
    assert str(e_info.value.args[0]).startswith("pre_dittos")

    assert sh_pre_ditto.long("///MOT_02//") == "SR05ID01DEV02:MOT_02.PVA"


if __name__ == "__main__":
    test_sh_no_ditto()
    test_sh_pre_ditto()

    print("\n\n\nall tests passed.\n\n\n")
