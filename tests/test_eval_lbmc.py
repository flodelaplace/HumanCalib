"""LBMC reader: the distortion coefficients Calib.toml gets wrong."""
import numpy as np
import pytest

from humancalib.evaluation import lbmc

QCA = """<calibration><cameras>
<camera active="1" calibrated="true" message="" point-count="2241" avg-residual="0.5" serial="26580" model="Miqus Video" viewrotation="0">
<transform x="4263.3" y="2283.8" z="1794.3" r11="1" r12="0" r13="0" r21="0" r22="1" r23="0" r31="0" r32="0" r33="1"/>
<intrinsic focallength="9.27" sensorMinU="0.000000" sensorMaxU="122879.000000" sensorMinV="0.000000" sensorMaxV="69631.000000"
 focalLengthU="107872.609375" focalLengthV="107880.257813" centerPointU="60827.273438" centerPointV="32684.021484" skew="0"
 radialDistortion1="-0.045450" radialDistortion2="0.139604" radialDistortion3="0.000000"
 tangentalDistortion1="0.000615" tangentalDistortion2="-0.000391"/>
</camera></cameras></calibration>"""


def test_intrinsics_are_read_in_pixels_but_distortion_is_not_scaled():
    raw = lbmc.read_raw(QCA)["26580"]
    assert (raw["W"], raw["H"]) == (1920.0, 1088.0)
    assert raw["fx"] == pytest.approx(1685.51, abs=0.01)
    assert raw["dist"] == pytest.approx([-0.04545, 0.139604, 0.000615, -0.000391, 0.0])


@pytest.mark.parametrize("clockwise", [True, False])
def test_distortion_turns_the_way_the_principal_point_says(clockwise):
    raw = lbmc.read_raw(QCA)["26580"]
    cx = raw["H"] - raw["cy"] if clockwise else raw["cy"]
    K = np.array([[raw["fy"], 0, cx], [0, raw["fx"], 960.0], [0, 0, 1]])
    dist, cw = lbmc.rotated_distortion(raw, K)
    assert cw == clockwise
    k1, k2, p1, p2, k3 = raw["dist"]
    # same convention as imove.rotate_camera, whose projection test covers the sign
    assert dist == pytest.approx([k1, k2, p2, -p1, k3] if clockwise else [k1, k2, -p2, p1, k3])
