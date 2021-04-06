import utils.utils as ut
import utils.eputils as et
import pytest


def test_motor_tests():

    cil_motor_field_fs = [
        [r"CIL[:]{1}", ""],  # Device designator, ends with ":"
        [r"[\w_]+", ""],  # Motor () designator
        [r"[.:]{1}[\w]+", ""],  # Motor field, starts with either "." or ":"
    ]

    sh_cil = ut.ShortHand(group_formats=cil_motor_field_fs, post_dittos=True)
    # complete sentence
    assert sh_cil.long("CIL:MOT1.RBV") == "CIL:MOT1.RBV"

    # now quickly defining all of the required pv's
    mt = et.SmartEpics(prefix="CIL:MOT1")

    if not mt.check(["~.RBV==~.VAL"]):
        print(f"Motor position is not sync'd: {mt.prefix}")

    if mt.check(["~:PhaseFound.RVAL==1", "~.MSTA==0"]):
        # motor is ready for testing!
        pass

    assert mt.check([None, None, "2 ** 2 == 4"])


if __name__ == "__main__":
    test_motor_tests()

    print("\n\n\nAll tests passed.\n\n\n")
