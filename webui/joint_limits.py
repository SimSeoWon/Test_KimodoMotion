"""Anatomical range-of-motion table for the SOMA30 pose validator.

Values are passive ROM in degrees. "hard" limits reject a pose; "soft" limits
only warn, because no measured reference backs them or because deliberate
athletic/martial poses may exceed them.

Sources (checked 2026-09-27, see history/2026-09-27_pose-anatomy-validator.md):
- AAOS, *Joint Motion: Method of Measuring and Recording* (1965), as tabulated in
  goniometry references (Norkin & White): cervical, shoulder, elbow, forearm,
  wrist, hip, knee, ankle values below marked "AAOS".
- Inman et al. 1944 scapulohumeral rhythm (2:1 glenohumeral:scapulothoracic);
  McQuade & Smidt 1998 report 2.9:1-7.9:1, so the split is only a default.
- Values marked "approx" have no fetched primary source; they are soft limits.
"""

# Knee/elbow hyperextension allowance requested by the user (AAOS records 0°).
HYPEREXTENSION_DEG = 5.0
# A hinge whose rotation leaves its axis by more than this is "bent sideways".
HINGE_OFF_AXIS_DEG = 10.0

# Ball joints: elevation limits of the bone direction away from the anatomical
# neutral direction, per plane, plus twist about the bone. Keys of "swing" name
# the anatomical motion toward +forward, -forward, +outward, -outward (or the
# joint-specific axes documented in pose_anatomy.BALL_JOINTS).
BALL_LIMITS = {
    # Thoracohumeral: measured from the chest, so clavicle + glenohumeral combine.
    "shoulder": {"swing": {"flexion": 180, "extension": 60, "abduction": 180, "adduction": 40},
                 "twist": {"external_rotation": 90, "internal_rotation": 70},
                 "severity": "hard", "source": "AAOS"},
    "hip": {"swing": {"flexion": 120, "extension": 30, "abduction": 45, "adduction": 30},
            "twist": {"external_rotation": 45, "internal_rotation": 45},
            "severity": "hard", "source": "AAOS"},
    "neck": {"swing": {"flexion": 45, "extension": 45, "lateral_flexion_left": 45, "lateral_flexion_right": 45},
             "twist": {"rotation_left": 60, "rotation_right": 60},
             "severity": "hard", "source": "AAOS (cervical)"},
    # Thoracolumbar values are commonly quoted AAOS numbers but were not fetched.
    "spine": {"swing": {"flexion": 80, "extension": 25, "lateral_flexion_left": 35, "lateral_flexion_right": 35},
              "twist": {"rotation_left": 45, "rotation_right": 45},
              "severity": "soft", "source": "approx (thoracolumbar, commonly quoted AAOS)"},
    "ankle": {"swing": {"dorsiflexion": 20, "plantarflexion": 50, "abduction": 20, "adduction": 20},
              "twist": {"inversion": 35, "eversion": 15},
              "severity": "hard", "source": "AAOS (dorsi/plantar, inversion/eversion); toe-in/out approx"},
    "wrist": {"swing": {"flexion": 80, "extension": 70, "radial_deviation": 20, "ulnar_deviation": 30},
              "twist": {"supination": 80, "pronation": 80},
              "severity": "soft", "source": "AAOS (wrist, forearm); twist is rest-relative approx"},
    "clavicle": {"swing": {"protraction": 25, "retraction": 25, "elevation": 40, "depression": 10},
                 "twist": {"rotation_forward": 30, "rotation_backward": 30},
                 "severity": "soft", "source": "approx"},
}

HINGE_LIMITS = {
    "knee": {"flexion": 150, "severity": "hard",
             "source": "AAOS 135° typical; 130-150° full flexion per user"},
    "elbow": {"flexion": 150, "severity": "hard", "source": "AAOS"},
}

# Two-joint muscle coupling (general anatomy, not a fetched number): hamstrings
# limit hip flexion with the knee straight. Warning only.
STRAIGHT_LEG_HIP_FLEXION_WARN_DEG = 90.0
STRAIGHT_LEG_KNEE_MAX_DEG = 20.0

# AAOS ankle dorsiflexion (20°) is non-weight-bearing. With the foot on the ground,
# body weight pushes the tibia over the foot (squat, lunge, horse stance): the
# weight-bearing lunge test regards < ~30° as restricted (search summary; the
# normative papers could not be opened), so 45° is an approximate hard ceiling.
ANKLE_WEIGHT_BEARING_DORSIFLEXION_DEG = 45.0
WEIGHT_BEARING_CONTACT_M = 0.03

# Contact: anything this far below the ground plane is penetration.
GROUND_TOLERANCE_M = 0.02
