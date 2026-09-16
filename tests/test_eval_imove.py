"""IMOVE reader: the side-mounted cameras and the out-and-back window."""
import cv2
import numpy as np
import pytest

from humancalib.evaluation import imove
from humancalib.evaluation.rig import Camera

XML = """<calibration><cameras>
<camera active="1" serial="22" viewrotation="270" static_boxes="">
<transform x="1037.91" y="-69.4007" z="8188.1" r11="0.37971" r12="-0.0322406" r13="0.924544"
 r21="-0.0679489" r22="-0.997665" r23="-0.00688382" r31="0.922609" r32="-0.0597996" r33="-0.380985"/>
<intrinsic focallength="4.59107e-41" sensorMinU="0" sensorMaxU="1920" sensorMinV="0" sensorMaxV="1080"
 focalLengthU="2139.87" focalLengthV="2138.55" centerPointU="967.724" centerPointV="518.245" skew="0"
 radialDistortion1="-0.0749605" radialDistortion2="0.0126639" radialDistortion3="0.242452"
 tangentalDistortion1="-0.000283447" tangentalDistortion2="0.00165544"/>
</camera></cameras></calibration>"""


def test_xml_is_read_in_metres_with_opencv_distortion_order():
    (serial, rot, cam), = imove.parse_calibration(XML)
    assert (serial, rot) == ("22", 270)
    assert cam.t == pytest.approx([1.03791, -0.0694007, 8.1881])
    # k1 k2 p1 p2 k3: the XML lists the three radial terms before the tangential ones
    assert cam.dist == pytest.approx([-0.0749605, 0.0126639, -0.000283447, 0.00165544, 0.242452])
    assert cam.size == (1920.0, 1080.0)


@pytest.mark.parametrize("clockwise", [True, False])
def test_a_rotated_camera_projects_to_the_rotated_pixel(clockwise):
    """The rotated model must put every point, distortion included, exactly where the
    turned image shows it -- otherwise two cameras of ten are wrong."""
    rng = np.random.default_rng(0)
    R = cv2.Rodrigues(np.array([0.2, -0.4, 0.1]))[0]
    cam = Camera("c", (1920.0, 1080.0), np.array([[1500.0, 0, 950.0], [0, 1490.0, 530.0], [0, 0, 1]]),
                 np.array([-0.1, 0.05, 0.002, -0.001, 0.02]), R, np.array([0.1, -0.2, 4.0]))
    X = rng.uniform(-1, 1, (50, 3))
    uv = cv2.projectPoints(X, cv2.Rodrigues(cam.R)[0], cam.t, cam.K, cam.dist)[0].reshape(-1, 2)
    rot = imove.rotate_camera(cam, clockwise)
    uv2 = cv2.projectPoints(X, cv2.Rodrigues(rot.R)[0], rot.t, rot.K, rot.dist)[0].reshape(-1, 2)
    W, H = cam.size
    expected = np.c_[H - 1 - uv[:, 1], uv[:, 0]] if clockwise else np.c_[uv[:, 1], W - 1 - uv[:, 0]]
    assert uv2 == pytest.approx(expected, abs=1e-6)
    assert rot.size == (1080.0, 1920.0)


def test_the_upright_turn_points_the_image_down_the_world():
    """Camera 22 has viewrotation 270 but must be turned counter-clockwise to stand upright;
    the direction comes from the geometry, not from the attribute."""
    (_, _, cam), = imove.parse_calibration(XML)
    up = imove.upright(cam)
    assert up.R[1] @ np.array(imove.UP) < -0.9
    assert up.K[0, 2] == pytest.approx(cam.K[1, 2])          # counter-clockwise: cx' = cy


def test_walk_window_spans_both_passes_and_the_gap():
    rows = [{"Sujet": 2, "Aller num": 1, "Début": 3370, "Fin": 3900},
            {"Sujet": 2, "Aller num": 1, "Début": 2590, "Fin": 3120},
            {"Sujet": 2, "Aller num": 2, "Début": 4870, "Fin": 5380},
            {"Sujet": 2, "Aller num": 3, "Début": 6550, "Fin": 6880},
            {"Sujet": 3, "Aller num": 1, "Début": 100, "Fin": 200}]
    assert imove.walk_window(rows, 2) == (2590, 5380)
    with pytest.raises(KeyError):
        imove.walk_window(rows, 9)
