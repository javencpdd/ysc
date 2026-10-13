"""
neupan_core is the main class for the neupan_ros package. It is used to run the NeuPAN algorithm in the ROS framework, which subscribes to the laser scan and localization information, and publishes the velocity command to the robot.

Developed by Ruihua Han
Copyright (c) 2025 Ruihua Han <hanrh@connect.hku.hk>

Modified by Haowen Yu.
Copyright (c) 2026 Manifold Tech Ltd <yuhaowen@manifoldtech.cn>

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program. If not, see <https://www.gnu.org/licenses/>.
"""

import os
from collections import deque
from functools import partial
from math import sin, cos, atan2, pi, inf
import numpy as np
import yaml
from loguru import logger
import time

from neupan import neupan
from neupan.util import get_transform

import rospy
from geometry_msgs.msg import Twist, PoseStamped, Quaternion, PoseWithCovarianceStamped
from nav_msgs.msg import Odometry, Path
from std_msgs.msg import Empty, Float32
from visualization_msgs.msg import MarkerArray, Marker
from sensor_msgs.msg import LaserScan, PointCloud2
import tf
import sensor_msgs.point_cloud2 as pc2

# Parameters that can be tuned online via /neupan/<name> Float32 topics.
# Order is irrelevant; the callback dispatches by name. (Issue E1.)
# NOTE: ro_obs and bk are intentionally NOT tunable online — they're not
# cvxpy Parameters because that would violate DPP. Change them in
# config/restart.
_TUNABLE_PARAMS = (
    "q_s",
    "q_theta",
    "p_u",
    "p_w",
    "p_dw",
    "eta",
    "d_max",
    "d_min",
)


class neupan_core:
    def __init__(self) -> None:

        rospy.init_node("neupan_node", anonymous=True)

        config_path = os.path.join(os.path.dirname(__file__), "configs", "config.yaml")
        with open(config_path, "r") as f:
            self.config = yaml.safe_load(f)
        logger.info(f"Configuration:\n {yaml.dump(self.config)}")

        self.scan_angle_range = np.array(self.config["scan_angle"], dtype=np.float32)
        self.scan_range = np.array(self.config["scan_range"], dtype=np.float32)

        pan = {"dune_checkpoint": self.config["dune_checkpoint"]}
        self.neupan_planner = neupan.init_from_yaml(
            os.path.abspath(
                os.path.join(
                    os.path.dirname(__file__), self.config["planner_config_file"]
                )
            ),
            pan=pan,
        )

        # data
        self.obstacle_points = None  # (2, n)  n number of points
        self.robot_state = None  # (3, 1) [x, y, theta]
        self.stop = False

        # publisher
        self.vel_pub = rospy.Publisher(
            self.config["topic"]["cmd_vel"], Twist, queue_size=10
        )
        self.plan_pub = rospy.Publisher("/neupan_plan", Path, queue_size=10)
        self.ref_state_pub = rospy.Publisher(
            "/neupan_ref_state", Path, queue_size=10
        )  # current reference state
        self.ref_path_pub = rospy.Publisher(
            "/neupan_initial_path", Path, queue_size=10
        )  # initial path

        ## for rviz visualization
        self.point_markers_pub_dune = rospy.Publisher(
            "/dune_point_markers", MarkerArray, queue_size=10
        )
        self.robot_marker_pub = rospy.Publisher("/robot_marker", Marker, queue_size=10)
        self.point_markers_pub_nrmp = rospy.Publisher(
            "/nrmp_point_markers", MarkerArray, queue_size=10
        )
        self.arrive_pub = rospy.Publisher(self.config['topic']['arrive'], Empty, queue_size=1)
        self.last_arrive_flag: bool = False

        self.listener = tf.TransformListener()

        # subscriber
        rospy.Subscriber(self.config["topic"]["scan"], LaserScan, self.scan_callback)

        odom_fb_cfg = self.config.get("odom_feedback", {}) or {}
        self._odom_feedback_enable = bool(odom_fb_cfg.get("enable", False))
        self._odom_stale_threshold = float(
            odom_fb_cfg.get("stale_threshold_sec", 0.2)
        )
        self._last_odom_v = 0.0
        self._last_odom_w = 0.0
        self._last_odom_t = None  # ROS time of last odom; None until first msg


        smith_cfg = self.config.get("smith_predictor", {}) or {}
        self._smith_enable = bool(smith_cfg.get("enable", True))
        self._smith_fixed_lag_sec = float(smith_cfg.get("fixed_lag_sec", 0.04))
        self._smith_use_solve_time = bool(smith_cfg.get("use_solve_time", True))
        self._smith_max_tau_sec = float(smith_cfg.get("max_tau_sec", 0.30))
        self._smith_velocity_source = str(
            smith_cfg.get("velocity_source", "odom")
        ).lower()
        self._last_solve_sec = 0.0  # updated each cycle in run()

        needs_odom = self._odom_feedback_enable or (
            self._smith_enable and self._smith_velocity_source == "odom"
        )
        if needs_odom:
            odom_topic = self.config.get("topic", {}).get("odom", "/odin1/odometry")
            rospy.Subscriber(odom_topic, Odometry, self.odometry_callback)
            rospy.loginfo(
                f"[odom] subscribing {odom_topic} "
                f"(F1={self._odom_feedback_enable}, F2={self._smith_enable})"
            )
        if self._odom_feedback_enable:
            rospy.loginfo("[F1] odom_feedback ENABLED")
        else:
            rospy.loginfo("[F1] odom_feedback DISABLED (using cmd feedback)")
        if self._smith_enable:
            rospy.loginfo(
                f"[F2] smith_predictor ENABLED "
                f"(fixed_lag={self._smith_fixed_lag_sec:.3f}s, "
                f"use_solve_time={self._smith_use_solve_time}, "
                f"max_tau={self._smith_max_tau_sec:.2f}s, "
                f"velocity={self._smith_velocity_source})"
            )
        else:
            rospy.loginfo("[F2] smith_predictor DISABLED")

        # three types of initial path:
        # 1. from given path
        # 2. from waypoints
        # 3. from goal position
        rospy.Subscriber(self.config["topic"]["path"], Path, self.path_callback)
        rospy.Subscriber(
            self.config["topic"]["waypoints"], Path, self.waypoints_callback
        )
        rospy.Subscriber(self.config["topic"]["goal"], PoseStamped, self.goal_callback)

        for name in _TUNABLE_PARAMS:
            rospy.Subscriber(
                f"/neupan/{name}",
                Float32,
                partial(self._adjust_param_callback, name=name),
            )

        self._last_cmd_v = 0.0
        self._last_cmd_w = 0.0
        self._last_cmd_t = None

        
        self._cmd_w_lpf_alpha = float(
            self.config.get("cmd_w_lpf_alpha", 0.7)
        )

        prealign_cfg = self.config.get("prealign", {}) or {}
        self._prealign_enable = bool(prealign_cfg.get("enable", False))
        self._prealign_heading_threshold = float(
            prealign_cfg.get("heading_threshold", 0.5)
        )
        self._prealign_obs_distance_threshold = float(
            prealign_cfg.get("obs_distance_threshold", 1.0)
        )
        self._prealign_exit_heading_threshold = float(
            prealign_cfg.get("exit_heading_threshold", 0.2)
        )
        self._prealign_exit_obs_distance_threshold = float(
            prealign_cfg.get("exit_obs_distance_threshold", 1.5)
        )
        self._prealign_cone_half_width_rad = float(
            prealign_cfg.get("cone_half_width_rad", 0.524)
        )
        self._prealign_angular_kp = float(prealign_cfg.get("angular_kp", 1.5))
        self._prealign_max_w = float(prealign_cfg.get("max_w", 0.6))
        self._prealign_ref_avg_count = int(prealign_cfg.get("ref_avg_count", 5))
        self._prealign_active = False  # hysteresis state

        adaptive_cfg = self.config.get("adaptive_d_max", {}) or {}
        self._adaptive_d_max_enable = bool(adaptive_cfg.get("enable", False))
        self._adaptive_d_max_min = float(adaptive_cfg.get("min", 0.05))
        self._adaptive_d_max_max = float(adaptive_cfg.get("max", 0.25))
        self._adaptive_d_max_safety_margin = float(
            adaptive_cfg.get("safety_margin", 0.05)
        )
        self._adaptive_d_max_forward_window_m = float(
            adaptive_cfg.get("forward_window_m", 2.0)
        )
        self._adaptive_d_max_lateral_window_m = float(
            adaptive_cfg.get("lateral_window_m", 2.0)
        )
        self._adaptive_d_max_update_period = float(
            adaptive_cfg.get("update_period_sec", 0.5)
        )
        self._adaptive_d_max_last_t = 0.0


        stuck_cfg = self.config.get("stuck_escape", {}) or {}
        self._stuck_escape_enable = bool(stuck_cfg.get("enable", False))
        self._stuck_escape_v_eps = float(stuck_cfg.get("v_eps", 0.02))
        self._stuck_escape_w_eps = float(stuck_cfg.get("w_eps", 0.05))
        self._stuck_escape_trigger_frames = int(stuck_cfg.get("trigger_frames", 15))
        self._stuck_escape_front_obs_threshold = float(
            stuck_cfg.get("front_obs_threshold", 0.6)
        )
        self._stuck_escape_cone_half_width = float(
            stuck_cfg.get("cone_half_width_rad", 0.524)
        )
        self._stuck_escape_back_speed = float(stuck_cfg.get("back_speed", 0.2))
        self._stuck_escape_rotate_speed = float(stuck_cfg.get("rotate_speed", 0.8))
        self._stuck_escape_duration = float(stuck_cfg.get("duration_sec", 1.5))
        self._stuck_escape_exit_obs_distance = float(
            stuck_cfg.get("exit_obs_distance", 1.0)
        )
        self._stuck_escape_side_radius = float(
            stuck_cfg.get("side_search_radius_m", 2.0)
        )

        self._stuck_escape_displacement_window = float(
            stuck_cfg.get("displacement_window_sec", 1.0)
        )
        self._stuck_escape_displacement_threshold = float(
            stuck_cfg.get("displacement_threshold_m", 0.05)
        )
        self._pose_history = deque(maxlen=400)  # (t, x, y); ~8s @ 50 Hz

        self._stuck_count = 0
        self._stuck_escape_active = False
        self._stuck_escape_start_time = None
        self._stuck_escape_dir = 1.0  # +1 = rotate left, -1 = rotate right


        self._escape_dir_history = deque(maxlen=8)  # (time, dir)
        self._escape_limit_cycle_n = int(
            stuck_cfg.get("limit_cycle_consecutive_n", 3)
        )
        self._escape_limit_cycle_sec = float(
            stuck_cfg.get("limit_cycle_window_sec", 10.0)
        )

        self._stuck_escape_min_rotation = float(
            stuck_cfg.get("min_rotation_rad", 1.05)
        )
        self._stuck_escape_start_yaw = None  # yaw at escape ENTER, for rotation tracking


        self._early_replan_enable = bool(
            stuck_cfg.get("early_replan_enable", True)
        )
        self._early_replan_trigger_frames = int(
            stuck_cfg.get("early_replan_trigger_frames", 5)
        )
        self._early_replan_cooldown_sec = float(
            stuck_cfg.get("early_replan_cooldown_sec", 2.0)
        )
        self._last_early_replan_t = 0.0

        self._post_escape_grace_max = float(
            stuck_cfg.get("post_escape_grace_max_sec", 5.0)
        )
        self._post_escape_grace_clear_threshold = float(
            stuck_cfg.get("post_escape_grace_clear_threshold_m", 1.5)
        )
        self._post_escape_grace_clear_dwell = float(
            stuck_cfg.get("post_escape_grace_clear_dwell_sec", 0.5)
        )
        self._post_escape_grace_scale = float(
            stuck_cfg.get("post_escape_grace_q_theta_scale", 0.25)
        )

        self._post_escape_grace_q_s_scale = float(
            stuck_cfg.get("post_escape_grace_q_s_scale", 0.5)
        )

        self._post_escape_grace_min_distance = float(
            stuck_cfg.get("post_escape_grace_min_distance_m", 1.0)
        )
        # Runtime state for adaptive grace.
        self._post_escape_grace_active = False
        self._post_escape_grace_start_t = None
        self._post_escape_grace_start_xy = None  # (x, y) at grace start
        self._post_escape_grace_clear_since = None

        try:
            self._q_theta_normal = float(
                self.neupan_planner.pan.nrmp_layer.q_theta.detach().item()
            )
        except Exception:
            self._q_theta_normal = 0.2
        try:
            self._q_s_normal = float(
                self.neupan_planner.pan.nrmp_layer.q_s.detach().item()
            )
        except Exception:
            self._q_s_normal = 2.0

    def _adjust_param_callback(self, msg, name):
        """Generic Float32 callback dispatching to update_adjust_parameters()."""
        try:
            value = float(msg.data)
        except (TypeError, ValueError):
            rospy.logwarn(f"/neupan/{name}: invalid payload, ignored")
            return
        logger.info(f"Update {name} to {value}")
        if name == "q_theta":
            self._q_theta_normal = value
            effective = (
                value * self._post_escape_grace_scale
                if self._post_escape_grace_active
                else value
            )
            self.neupan_planner.update_adjust_parameters(q_theta=effective)
        elif name == "q_s":
            self._q_s_normal = value
            effective = (
                value * self._post_escape_grace_q_s_scale
                if self._post_escape_grace_active
                else value
            )
            self.neupan_planner.update_adjust_parameters(q_s=effective)
        else:
            self.neupan_planner.update_adjust_parameters(**{name: value})

    def run(self):

        r = rospy.Rate(50)

        while not rospy.is_shutdown():

            try:
                (trans, rot) = self.listener.lookupTransform(
                    self.config["frame"]["map"],
                    self.config["frame"]["base"],
                    rospy.Time(0),
                )

                yaw = self.quat_to_yaw_list(rot)
                x, y = trans[0], trans[1]
                self.robot_state = np.array([x, y, yaw]).reshape(3, 1)
                # Pose history for displacement-based stuck detection.
                self._pose_history.append((time.time(), float(x), float(y)))

                if self._post_escape_grace_active:
                    self._update_post_escape_grace()

            except (
                tf.LookupException,
                tf.ConnectivityException,
                tf.ExtrapolationException,
            ):
                rospy.loginfo_throttle(
                    3,
                    "waiting for tf for the transform from {} to {}".format(
                        self.config["frame"]["base"], self.config["frame"]["map"]
                    ),
                )
                r.sleep()
                continue

            if self.robot_state is None:
                rospy.logwarn_throttle(3, "waiting for robot state")
                r.sleep()
                continue

            rospy.loginfo_once(
                "robot state received {}".format(self.robot_state.tolist())
            )

            if (
                len(self.neupan_planner.waypoints) >= 1
                and self.neupan_planner.initial_path is None
            ):
                self.neupan_planner.set_initial_path_from_state(self.robot_state)
                # print('set initial path', self.neupan_planner.initial_path)

            if self.neupan_planner.initial_path is None:
                rospy.logwarn_throttle(3, "waiting for neupan initial path")
                r.sleep()
                continue

            rospy.loginfo_once("initial Path Received")
            self.ref_path_pub.publish(
                self.generate_path_msg(self.neupan_planner.initial_path)
            )

            if self.obstacle_points is None:
                rospy.logwarn_throttle(
                    1, "No obstacle points, only path tracking task will be performed"
                )

            # refresh d_max periodically based on local corridor width.
            if self._adaptive_d_max_enable:
                now = time.time()
                if now - self._adaptive_d_max_last_t >= self._adaptive_d_max_update_period:
                    self._update_adaptive_d_max()
                    self._adaptive_d_max_last_t = now

            # Override priority: stuck-escape > prealign > NeuPAN MPC.
            escape_cmd = self._stuck_escape_decide_and_command()
            prealign_cmd = (
                None if escape_cmd is not None
                else self._prealign_decide_and_command()
            )

            bypass_rate_limit = False
            if escape_cmd is not None:
                action = escape_cmd
                bypass_rate_limit = True
                info = {
                    "stop": False,
                    "arrive": False,
                    "opt_state_list": [self.robot_state],
                    "ref_state_list": [self.robot_state],
                    "escape": True,
                }
            elif prealign_cmd is not None:
                action = prealign_cmd
                info = {
                    "stop": False,
                    "arrive": False,
                    "opt_state_list": [self.robot_state],
                    "ref_state_list": [self.robot_state],
                    "prealign": True,
                }
            else:
                if not self.last_arrive_flag:
                    t_start = time.time()

                # Smith Predictor — when enabled, plan from the state we
                # PREDICT the robot will be in by the time this command takes
                # effect (now + last_solve_time + fixed_actuator_lag) instead
                # of from "where the robot is now". 
                planner_state = self._predict_state_for_solve(self.robot_state)

                action, info = self.neupan_planner(planner_state, self.obstacle_points)

                if not self.last_arrive_flag:
                    t_end = time.time()
                    self._last_solve_sec = t_end - t_start
                    rospy.loginfo(
                        f"neupan planning time: {self._last_solve_sec*1000:.1f} ms"
                    )

            self.stop = info["stop"]
            self.arrive = info["arrive"]

            if info["arrive"] and not self.last_arrive_flag:
                self.arrive_pub.publish(Empty())
                rospy.loginfo("arrive at the target")

            self.last_arrive_flag = info["arrive"]


            if bypass_rate_limit:
                self._last_cmd_v = float(action[0, 0])
                self._last_cmd_w = float(action[1, 0])
                self._last_cmd_t = time.time()

                v_fb, w_fb = self._velocity_for_feedback(
                    self._last_cmd_v, self._last_cmd_w
                )
                try:
                    self.neupan_planner.cur_vel_array[0, 0] = v_fb
                    self.neupan_planner.cur_vel_array[1, 0] = w_fb
                except Exception as e:  # pragma: no cover - defensive
                    rospy.logwarn_throttle(5, f"escape feedback skipped: {e}")
            else:
                action = self._rate_limit_action(action)


            opt_states = info.get("opt_state_list")
            if opt_states:
                self.plan_pub.publish(self.generate_path_msg(opt_states))
            ref_states = info.get("ref_state_list")
            if ref_states:
                self.ref_state_pub.publish(self.generate_path_msg(ref_states))
            if not info["arrive"] or not self.last_arrive_flag:
                self.vel_pub.publish(self.generate_twist_msg(action))

            self.point_markers_pub_dune.publish(self.generate_dune_points_markers_msg())
            self.point_markers_pub_nrmp.publish(self.generate_nrmp_points_markers_msg())
            self.robot_marker_pub.publish(self.generate_robot_marker_msg())

            if info["stop"]:
                rospy.logwarn_throttle(
                    0.5,
                    "neupan stop with the min distance "
                    + str(self.neupan_planner.min_distance.detach().item())
                    + " threshold "
                    + str(self.neupan_planner.collision_threshold),
                )

            r.sleep()

    def _rate_limit_action(self, action):
        """
        Clamp the change in (v, omega) since the last published command using
        wall-clock dt and ``robot.max_acce``. The clamped values are written
        back into ``planner.cur_vel_array[:, 0]`` so that the MPC's next
        linearization point matches reality (this is the key piece the earlier
        ``neupan_ros_modify`` attempt was missing).

        Returns a 2x1 numpy array suitable for downstream publishing.
        """
        if action is None:
            return action

        v_cmd = float(action[0, 0])
        w_cmd = float(action[1, 0])

        now = time.time()
        if self._last_cmd_t is None:
            dt = float(self.neupan_planner.robot.dt)
        else:
            dt = max(now - self._last_cmd_t, 1e-3)

        if self._cmd_w_lpf_alpha > 0.0:
            a = self._cmd_w_lpf_alpha
            w_cmd = a * self._last_cmd_w + (1.0 - a) * w_cmd

        max_acce = self.neupan_planner.robot.max_acce  # (2, 1) numpy
        dv_max = float(max_acce[0, 0]) * dt
        dw_max = float(max_acce[1, 0]) * dt

        v_cmd = float(np.clip(v_cmd, self._last_cmd_v - dv_max, self._last_cmd_v + dv_max))
        w_cmd = float(np.clip(w_cmd, self._last_cmd_w - dw_max, self._last_cmd_w + dw_max))

        self._last_cmd_v = v_cmd
        self._last_cmd_w = w_cmd
        self._last_cmd_t = now


        v_fb, w_fb = self._velocity_for_feedback(v_cmd, w_cmd)
        try:
            self.neupan_planner.cur_vel_array[0, 0] = v_fb
            self.neupan_planner.cur_vel_array[1, 0] = w_fb
        except Exception as e:  # pragma: no cover - defensive
            rospy.logwarn_throttle(5, f"rate_limit feedback skipped: {e}")

        limited = np.array([[v_cmd], [w_cmd]], dtype=float)
        return limited


    def _prealign_decide_and_command(self):
        """
        Return a 2x1 numpy command (v=0, w=signed) when pre-align is engaged,
        otherwise None (meaning: defer to NeuPAN). Hysteresis is applied via
        ``self._prealign_active`` so we don't oscillate between modes.
        """
        if not self._prealign_enable:
            return None
        if self.neupan_planner.initial_path is None or self.robot_state is None:
            return None

        ref_heading = self._get_first_ref_heading()
        if ref_heading is None:
            return None

        heading_err = self._wrap_to_pi(ref_heading - float(self.robot_state[2, 0]))
        front_obs = self._min_obs_distance_in_cone(self._prealign_cone_half_width_rad)

        if not self._prealign_active:
            should_enter = (
                abs(heading_err) > self._prealign_heading_threshold
                and front_obs < self._prealign_obs_distance_threshold
            )
            if should_enter:
                self._prealign_active = True
                rospy.loginfo(
                    f"[prealign] enter: heading_err={heading_err:.3f} rad, "
                    f"front_obs={front_obs:.2f} m"
                )
        else:
            should_exit = (
                abs(heading_err) < self._prealign_exit_heading_threshold
                or front_obs > self._prealign_exit_obs_distance_threshold
            )
            if should_exit:
                self._prealign_active = False
                rospy.loginfo(
                    f"[prealign] exit: heading_err={heading_err:.3f} rad, "
                    f"front_obs={front_obs:.2f} m"
                )

        if not self._prealign_active:
            return None

        w_cmd = self._prealign_angular_kp * heading_err
        w_cmd = float(
            np.clip(w_cmd, -self._prealign_max_w, self._prealign_max_w)
        )
        rospy.loginfo_throttle(
            1.0,
            f"[prealign] active: w_cmd={w_cmd:.3f} (err={heading_err:.3f})",
        )
        return np.array([[0.0], [w_cmd]], dtype=float)

    def _get_first_ref_heading(self):
        """Average the first few reference yaws in vector form to get a
        robust target heading near the robot's current point on the path."""
        path = self.neupan_planner.initial_path
        if path is None or len(path) == 0:
            return None
        n = min(self._prealign_ref_avg_count, len(path))
        if n < 1:
            return None
        sum_sin = 0.0
        sum_cos = 0.0
        for i in range(n):
            yaw = float(path[i][2, 0])
            sum_sin += sin(yaw)
            sum_cos += cos(yaw)
        return atan2(sum_sin, sum_cos)

    def _min_obs_distance_in_cone(self, half_width_rad):
        """Minimum distance from the robot to any obstacle point that lies in
        the forward cone ``[-half_width, +half_width]`` in the robot frame."""
        if self.obstacle_points is None or self.robot_state is None:
            return inf
        x = float(self.robot_state[0, 0])
        y = float(self.robot_state[1, 0])
        theta = float(self.robot_state[2, 0])
        rel = self.obstacle_points - np.array([[x], [y]])
        rel_angles = np.arctan2(rel[1, :], rel[0, :]) - theta
        rel_angles = (rel_angles + pi) % (2 * pi) - pi
        in_cone = np.abs(rel_angles) < half_width_rad
        if not np.any(in_cone):
            return inf
        return float(np.linalg.norm(rel[:, in_cone], axis=0).min())

    @staticmethod
    def _wrap_to_pi(rad):
        return (rad + pi) % (2 * pi) - pi


    def _update_adaptive_d_max(self):
        """Estimate local corridor half-width and push a fresh d_max into the
        planner. If estimation is invalid (no points in window) the previous
        value is kept."""
        half_width = self._estimate_corridor_half_width()
        if half_width is None or not np.isfinite(half_width):
            return

        robot_half_width = self._robot_half_width()
        effective_d_max = half_width - robot_half_width - self._adaptive_d_max_safety_margin
        effective_d_max = float(
            np.clip(
                effective_d_max,
                self._adaptive_d_max_min,
                self._adaptive_d_max_max,
            )
        )
        rospy.loginfo_throttle(
            2.0,
            f"[adaptive_d_max] half_width={half_width:.2f} -> d_max={effective_d_max:.3f}",
        )
        self.neupan_planner.update_adjust_parameters(d_max=effective_d_max)

    def _estimate_corridor_half_width(self):
        """Half-width = min(left_clearance, right_clearance) inside a forward
        rectangular window in the robot frame. Returns None if invalid."""
        if self.obstacle_points is None or self.robot_state is None:
            return None
        x = float(self.robot_state[0, 0])
        y = float(self.robot_state[1, 0])
        theta = float(self.robot_state[2, 0])
        c, s = cos(theta), sin(theta)
        # Inverse rotation: world -> robot frame.
        R_inv = np.array([[c, s], [-s, c]])
        rel = self.obstacle_points - np.array([[x], [y]])
        local = R_inv @ rel  # (2, n): row 0 = forward, row 1 = lateral

        forward_mask = (local[0] >= -self._adaptive_d_max_safety_margin) & (
            local[0] <= self._adaptive_d_max_forward_window_m
        )
        lateral_mask = np.abs(local[1]) <= self._adaptive_d_max_lateral_window_m
        mask = forward_mask & lateral_mask
        if not np.any(mask):
            return None

        y_vals = local[1, mask]
        left = y_vals[y_vals > 0]
        right = y_vals[y_vals < 0]
        left_min = float(left.min()) if left.size > 0 else self._adaptive_d_max_lateral_window_m
        right_min = float(-right.max()) if right.size > 0 else self._adaptive_d_max_lateral_window_m
        return min(left_min, right_min)

    def _robot_half_width(self):
        """Best-effort half-width of the robot footprint."""
        rb = self.neupan_planner.robot
        if getattr(rb, "shape", None) == "rectangle" and getattr(rb, "width", None):
            return float(rb.width) / 2.0
        # Fallback: bounding-box half-width from vertices.
        verts = getattr(rb, "vertices", None)
        if verts is not None:
            return float((verts[1, :].max() - verts[1, :].min()) / 2.0)
        return 0.2

    # ----------------------------------------------------------------------
    # Stuck-escape (opt-in)
    # ----------------------------------------------------------------------
    def _stuck_escape_decide_and_command(self):
        """
        Returns a 2x1 numpy command (negative v + signed w) when the planner
        should escape, otherwise ``None``. Manages a 3-state machine:
        idle -> counting -> active. Once active, the same command is held
        until either ``duration_sec`` elapses or the front clearance grows.
        """
        if not self._stuck_escape_enable:
            return None

        # ---- Already escaping: hold the command, check exit conditions ----
        if self._stuck_escape_active:
            now = time.time()
            elapsed = now - (self._stuck_escape_start_time or now)
            front_obs = self._min_obs_distance_in_cone(
                self._stuck_escape_cone_half_width
            )
            time_up = elapsed > self._stuck_escape_duration
            # Compute rotation done since ENTER (wrap-safe).
            if self._stuck_escape_start_yaw is None:
                rotation_done = 0.0
            else:
                dyaw = float(self.robot_state[2, 0]) - self._stuck_escape_start_yaw
                rotation_done = abs((dyaw + pi) % (2 * pi) - pi)

            cleared = (
                front_obs > self._stuck_escape_exit_obs_distance
                and rotation_done >= self._stuck_escape_min_rotation
            )
            if time_up or cleared:
                self._stuck_escape_active = False
                self._stuck_escape_start_time = None
                self._stuck_escape_start_yaw = None
                self._stuck_count = 0
                # Reset MPC nominal velocity to zero so it doesn't have to
                # ramp up from (v=-0.2, w=+/-0.8) against the p_u/p_w
                # smoothness penalties — that ramp was causing the dog to
                # crawl forward for ~1s after each escape, often re-entering
                # the stuck pattern before regaining speed.
                try:
                    self.neupan_planner.cur_vel_array[0, 0] = 0.0
                    self.neupan_planner.cur_vel_array[1, 0] = 0.0
                except Exception as e:  # pragma: no cover - defensive
                    rospy.logwarn_throttle(5, f"escape exit vel reset skipped: {e}")
                self._last_cmd_v = 0.0
                self._last_cmd_w = 0.0
                self._post_escape_grace_active = True
                self._post_escape_grace_start_t = time.time()
                self._post_escape_grace_start_xy = (
                    float(self.robot_state[0, 0]),
                    float(self.robot_state[1, 0]),
                )
                self._post_escape_grace_clear_since = None
                effective_q_theta = (
                    self._q_theta_normal * self._post_escape_grace_scale
                )
                effective_q_s = (
                    self._q_s_normal * self._post_escape_grace_q_s_scale
                )
                try:
                    self.neupan_planner.update_adjust_parameters(
                        q_theta=effective_q_theta, q_s=effective_q_s
                    )
                except Exception as e:  # pragma: no cover - defensive
                    rospy.logwarn_throttle(5, f"escape grace scale skipped: {e}")
                rospy.loginfo(
                    "[escape] exit: elapsed={:.2f}s, front_obs={:.2f}m, "
                    "rot={:.0f}deg, time_up={}, cleared={}; grace ON "
                    "q_theta {:.3f}->{:.3f}, q_s {:.3f}->{:.3f} "
                    "(need {:.1f}m + front clear, max {:.1f}s)".format(
                        elapsed, front_obs, rotation_done * 180 / pi,
                        time_up, cleared,
                        self._q_theta_normal, effective_q_theta,
                        self._q_s_normal, effective_q_s,
                        self._post_escape_grace_min_distance,
                        self._post_escape_grace_max,
                    )
                )

                self.arrive_pub.publish(Empty())
                rospy.loginfo("[escape] requested replan (publishing arrive)")
                return None
            v = -self._stuck_escape_back_speed
            w = self._stuck_escape_dir * self._stuck_escape_rotate_speed
            rospy.loginfo_throttle(
                0.5,
                "[escape] active: v={:.2f}, w={:+.2f} (dir={:+}), "
                "elapsed={:.2f}s, front_obs={:.2f}m, "
                "rot={:.0f}/{:.0f}deg".format(
                    v, w, self._stuck_escape_dir, elapsed, front_obs,
                    rotation_done * 180 / pi,
                    self._stuck_escape_min_rotation * 180 / pi,
                ),
            )
            return np.array([[v], [w]], dtype=float)

        # ---- Not escaping: detect the trigger condition ----
        # Need at least one prior published cmd (so _last_cmd_v/w/t are real).
        if self._last_cmd_t is None or self.robot_state is None:
            return None

        displacement = self._displacement_in_window(
            self._stuck_escape_displacement_window
        )
        cmd_low = (
            abs(self._last_cmd_v) < self._stuck_escape_v_eps
            and abs(self._last_cmd_w) < self._stuck_escape_w_eps
        )
        is_stuck_motion = (
            displacement is not None
            and displacement < self._stuck_escape_displacement_threshold
        ) or cmd_low

        front_obs = self._min_obs_distance_in_cone(
            self._stuck_escape_cone_half_width
        )
        has_close_front = front_obs < self._stuck_escape_front_obs_threshold

        if is_stuck_motion and has_close_front:
            self._stuck_count += 1
        else:
            self._stuck_count = max(0, self._stuck_count - 2)

        if has_close_front or self._stuck_count > 0:
            disp_str = (
                "n/a" if displacement is None else "{:.3f}".format(displacement)
            )
            rospy.loginfo_throttle(
                1.0,
                "[escape] watching: disp({:.1f}s)={}m v={:+.2f} w={:+.2f} "
                "front_obs={:.2f} stuck={} count={}/{}".format(
                    self._stuck_escape_displacement_window,
                    disp_str,
                    self._last_cmd_v,
                    self._last_cmd_w,
                    front_obs,
                    is_stuck_motion,
                    self._stuck_count,
                    self._stuck_escape_trigger_frames,
                ),
            )

        if (
            self._early_replan_enable
            and self._stuck_count >= self._early_replan_trigger_frames
        ):
            now_t_er = time.time()
            if (now_t_er - self._last_early_replan_t
                    >= self._early_replan_cooldown_sec):
                self.arrive_pub.publish(Empty())
                self._last_early_replan_t = now_t_er
                rospy.loginfo(
                    "[escape] early replan requested "
                    "(count={}, front={:.2f}m)".format(
                        self._stuck_count, front_obs
                    )
                )

        if self._stuck_count < self._stuck_escape_trigger_frames:
            return None

        left_min, left_count = self._side_clearance(side=+1)
        right_min, right_count = self._side_clearance(side=-1)
        # Larger min-distance wins. Tie / both empty -> left.
        natural_dir = 1.0 if left_min >= right_min else -1.0

        now_t = time.time()
        recent = [d for (t, d) in self._escape_dir_history
                  if now_t - t <= self._escape_limit_cycle_sec]
        forced = False
        if (len(recent) >= self._escape_limit_cycle_n
                and all(d == natural_dir for d in recent[-self._escape_limit_cycle_n:])):
            self._stuck_escape_dir = -natural_dir
            forced = True
        else:
            self._stuck_escape_dir = natural_dir
        self._escape_dir_history.append((now_t, self._stuck_escape_dir))

        self._stuck_escape_active = True
        self._stuck_escape_start_time = now_t
        self._stuck_escape_start_yaw = float(self.robot_state[2, 0])
        rospy.logwarn(
            "[escape] ENTER: stuck for {} frames "
            "(L_min={:.2f}m/{}pts, R_min={:.2f}m/{}pts, front={:.2f}m), "
            "dir={:+}{}".format(
                self._stuck_count,
                left_min, left_count,
                right_min, right_count,
                front_obs,
                self._stuck_escape_dir,
                " [LIMIT-CYCLE FLIPPED]" if forced else "",
            )
        )

        v = -self._stuck_escape_back_speed
        w = self._stuck_escape_dir * self._stuck_escape_rotate_speed
        return np.array([[v], [w]], dtype=float)

    def _displacement_in_window(self, window_sec):
        """
        Euclidean displacement (m) between the oldest pose within
        ``window_sec`` of "now" and the most recent pose. Returns ``None`` if
        the history doesn't yet span the requested window (gives the user
        a chance to actually move before we judge them as stuck).
        """
        if not self._pose_history:
            return None
        t_now, _, _ = self._pose_history[-1]
        cutoff = t_now - window_sec
        # Earliest pose with t >= cutoff. deque doesn't support binary search,
        # but maxlen=400 keeps this O(N) at ≤400 per call (~1ms).
        earliest = None
        for entry in self._pose_history:
            if entry[0] >= cutoff:
                earliest = entry
                break
        if earliest is None:
            return None
        # Require the window to be (mostly) covered before judging.
        if (t_now - earliest[0]) < 0.8 * window_sec:
            return None
        _, x0, y0 = earliest
        _, x1, y1 = self._pose_history[-1]
        dx = x1 - x0
        dy = y1 - y0
        return float((dx * dx + dy * dy) ** 0.5)

    def _update_post_escape_grace(self):
        """
        Adaptive exit criterion for the post-escape grace period.

        Called once per loop iteration while ``_post_escape_grace_active``.
        Restores both ``q_theta`` and ``q_s`` to their normal values (and
        clears the active flag) when EITHER:
        - the robot has moved at least ``min_distance_m`` from grace start
          AND the front cone has been continuously clear for
          ``clear_dwell_sec`` seconds, OR
        - ``max_sec`` has elapsed since grace started (hard upper bound).
        """
        now = time.time()
        front_obs = self._min_obs_distance_in_cone(
            self._stuck_escape_cone_half_width
        )
        is_clear = front_obs > self._post_escape_grace_clear_threshold

        if is_clear:
            if self._post_escape_grace_clear_since is None:
                self._post_escape_grace_clear_since = now
            clear_for = now - self._post_escape_grace_clear_since
        else:
            self._post_escape_grace_clear_since = None
            clear_for = 0.0

        # Distance moved since grace ENTER.
        if self._post_escape_grace_start_xy is not None:
            sx, sy = self._post_escape_grace_start_xy
            x = float(self.robot_state[0, 0])
            y = float(self.robot_state[1, 0])
            distance_moved = ((x - sx) ** 2 + (y - sy) ** 2) ** 0.5
        else:
            distance_moved = 0.0

        elapsed = now - (self._post_escape_grace_start_t or now)
        timed_out = elapsed >= self._post_escape_grace_max
        far_enough = distance_moved >= self._post_escape_grace_min_distance
        clear_long_enough = clear_for >= self._post_escape_grace_clear_dwell
        cleared = far_enough and clear_long_enough

        # Throttled progress log while grace is active.
        rospy.loginfo_throttle(
            1.0,
            "[escape] grace: dist={:.2f}/{:.1f}m, clear_for={:.1f}/{:.1f}s, "
            "elapsed={:.2f}/{:.1f}s, front_obs={:.2f}m".format(
                distance_moved, self._post_escape_grace_min_distance,
                clear_for, self._post_escape_grace_clear_dwell,
                elapsed, self._post_escape_grace_max, front_obs,
            ),
        )

        if not (timed_out or cleared):
            return

        try:
            self.neupan_planner.update_adjust_parameters(
                q_theta=self._q_theta_normal, q_s=self._q_s_normal,
            )
        except Exception as e:  # pragma: no cover - defensive
            rospy.logwarn_throttle(5, f"grace restore skipped: {e}")
        rospy.loginfo(
            "[escape] grace OFF: q_theta->{:.3f}, q_s->{:.3f} "
            "(elapsed={:.2f}s, distance={:.2f}m, front_obs={:.2f}m, "
            "cleared={}, timed_out={})".format(
                self._q_theta_normal, self._q_s_normal,
                elapsed, distance_moved, front_obs, cleared, timed_out,
            )
        )
        self._post_escape_grace_active = False
        self._post_escape_grace_start_t = None
        self._post_escape_grace_start_xy = None
        self._post_escape_grace_clear_since = None

    def _side_clearance(self, side):
        """
        Inspect the forward half-cone on the given side (``+1`` left, ``-1``
        right) within ``side_search_radius_m``.

        Returns ``(min_distance, count)``:
        - ``min_distance``: distance to the nearest obstacle in the cone, in
          meters; ``+inf`` if the cone is empty (treated as "infinitely clear").
        - ``count``: number of obstacle points in the cone (kept for logging).

        Used to pick the rotation direction during escape: the side with the
        larger ``min_distance`` has more turning room.
        """
        if self.obstacle_points is None or self.robot_state is None:
            return float("inf"), 0
        x = float(self.robot_state[0, 0])
        y = float(self.robot_state[1, 0])
        theta = float(self.robot_state[2, 0])
        rel = self.obstacle_points - np.array([[x], [y]])
        rel_angles = np.arctan2(rel[1, :], rel[0, :]) - theta
        rel_angles = (rel_angles + pi) % (2 * pi) - pi
        if side > 0:
            angle_mask = (rel_angles > 0) & (
                rel_angles < self._stuck_escape_cone_half_width
            )
        else:
            angle_mask = (rel_angles < 0) & (
                rel_angles > -self._stuck_escape_cone_half_width
            )
        distances = np.linalg.norm(rel, axis=0)
        near_mask = distances < self._stuck_escape_side_radius
        mask = angle_mask & near_mask
        count = int(np.sum(mask))
        if count == 0:
            return float("inf"), 0
        return float(np.min(distances[mask])), count

    # scan callback
    def scan_callback(self, scan_msg):

        if self.robot_state is None:
            return None

        ranges = np.array(scan_msg.ranges)
        angles = np.linspace(scan_msg.angle_min, scan_msg.angle_max, len(ranges))

        points = []
        # x, y, z, yaw, pitch, roll = self.lidar_offset

        if self.config["flip_angle"]:
            angles = np.flip(angles)

        for i in range(len(ranges)):
            distance = ranges[i]
            angle = angles[i]

            if (
                i % self.config["scan_downsample"] == 0
                and distance >= self.scan_range[0]
                and distance <= self.scan_range[1]
                and angle > self.scan_angle_range[0]
                and angle < self.scan_angle_range[1]
            ):
                point = np.array([[distance * cos(angle)], [distance * sin(angle)]])
                points.append(point)

        if len(points) == 0:
            self.obstacle_points = None
            rospy.loginfo_once("No valid scan points")
            return None

        point_array = np.hstack(points)

        try:
            (trans, rot) = self.listener.lookupTransform(
                self.config["frame"]["map"],
                self.config["frame"]["lidar"],
                rospy.Time(0),
            )

            yaw = self.quat_to_yaw_list(rot)
            x, y = trans[0], trans[1]

            trans_matrix, rot_matrix = get_transform(np.c_[x, y, yaw].reshape(3, 1))
            self.obstacle_points = rot_matrix @ point_array + trans_matrix
            rospy.loginfo_once("Scan obstacle points Received")

            return

        except (
            tf.LookupException,
            tf.ConnectivityException,
            tf.ExtrapolationException,
        ):
            rospy.loginfo_throttle(
                3,
                "waiting for tf for the transform from {} to {}".format(
                    self.config["frame"]["lidar"], self.config["frame"]["map"]
                ),
            )
            return

    def path_callback(self, path):

        initial_point_list = []

        for i in range(len(path.poses)):
            p = path.poses[i]
            x = p.pose.position.x
            y = p.pose.position.y

            if self.config["include_initial_path_direction"]:
                theta = self.quat_to_yaw(p.pose.orientation)
            else:
                rospy.loginfo_once(
                    "Using the points gradient as the initial path direction"
                )

                if i + 1 < len(path.poses):
                    p2 = path.poses[i + 1]
                    x2 = p2.pose.position.x
                    y2 = p2.pose.position.y
                    theta = atan2(y2 - y, x2 - x)
                else:
                    theta = initial_point_list[-1][2, 0]

            points = np.array([x, y, theta, 1]).reshape(4, 1)
            initial_point_list.append(points)

        if (
            self.neupan_planner.initial_path is None
            or self.config["refresh_initial_path"]
        ):
            rospy.loginfo_throttle(0.1, "initial path update from given path")
            self.neupan_planner.set_initial_path(initial_point_list)
            self.neupan_planner.reset()

    def waypoints_callback(self, path):
        """
        Utilize multiple waypoints (goals) to set the initial path
        """

        waypoints_list = [self.robot_state]

        for i in range(len(path.poses)):
            p = path.poses[i]
            x = p.pose.position.x
            y = p.pose.position.y

            if self.config["include_initial_path_direction"]:
                theta = self.quat_to_yaw(p.pose.orientation)
            else:
                rospy.loginfo_once(
                    "Using the points gradient as the initial path direction"
                )

                if i + 1 < len(path.poses):
                    p2 = path.poses[i + 1]
                    x2 = p2.pose.position.x
                    y2 = p2.pose.position.y
                    theta = atan2(y2 - y, x2 - x)
                else:
                    theta = waypoints_list[-1][2, 0]

            points = np.array([x, y, theta, 1]).reshape(4, 1)
            waypoints_list.append(points)

        if (
            self.neupan_planner.initial_path is None
            or self.config["refresh_initial_path"]
        ):
            rospy.loginfo_throttle(0.1, "initial path update from waypoints")
            self.neupan_planner.update_initial_path_from_waypoints(waypoints_list)
            self.neupan_planner.reset()

    def goal_callback(self, goal):

        x = goal.pose.position.x
        y = goal.pose.position.y
        theta = self.quat_to_yaw(goal.pose.orientation)

        self.goal = np.array([[x], [y], [theta]])

        rospy.loginfo("set neupan goal: {}".format([x, y, theta]))
        rospy.loginfo_throttle(0.1, "initial path update from goal position")
        self.neupan_planner.update_initial_path_from_goal(self.robot_state, self.goal)
        self.neupan_planner.reset()

    def quat_to_yaw_list(self, quater):

        x = quater[0]
        y = quater[1]
        z = quater[2]
        w = quater[3]

        yaw = atan2(2 * (w * z + x * y), 1 - 2 * (pow(z, 2) + pow(y, 2)))

        return yaw

    # ----------------------------------------------------------------------
    # Odom velocity feedback
    # ----------------------------------------------------------------------
    def odometry_callback(self, msg):
        """Cache the latest body-frame linear-x and yaw-rate from odom.
        Used by `_velocity_for_feedback` to replace the open-loop cmd
        feedback into MPC's `cur_vel_array` linearization point."""
        self._last_odom_v = float(msg.twist.twist.linear.x)
        self._last_odom_w = float(msg.twist.twist.angular.z)
        self._last_odom_t = time.time()

    def _velocity_for_feedback(self, v_cmd, w_cmd):
        """Return (v, w) to write into NeuPAN's cur_vel_array warm-start.
        Prefers odom-measured values when F1 is enabled and odom is fresh;
        falls back to the just-published cmd otherwise (= legacy behavior)."""
        if not self._odom_feedback_enable:
            return v_cmd, w_cmd
        if self._last_odom_t is None:
            rospy.logwarn_throttle(
                5.0, "[F1] no odom received yet; using cmd feedback"
            )
            return v_cmd, w_cmd
        age = time.time() - self._last_odom_t
        if age > self._odom_stale_threshold:
            rospy.logwarn_throttle(
                2.0,
                f"[F1] odom stale ({age:.2f}s > {self._odom_stale_threshold:.2f}s); "
                "falling back to cmd feedback",
            )
            return v_cmd, w_cmd
        return self._last_odom_v, self._last_odom_w

    # ----------------------------------------------------------------------
    # Smith Predictor (state forward-roll by control delay tau)
    # ----------------------------------------------------------------------
    def _predict_state_for_solve(self, state):
        """Forward-roll the robot state by tau = last_solve_time + fixed_lag
        using current measured (or commanded) velocity, so the MPC plans
        starting from where the robot WILL be when its next command takes
        effect — not where it currently is. Compensates the ~100-200ms
        cmd-to-effect delay that creates phase lag in the MPC loop.

        When disabled, returns the state unchanged (= legacy behavior).
        Diff-drive only.
        """
        if not self._smith_enable or state is None:
            return state

        tau = self._smith_fixed_lag_sec
        if self._smith_use_solve_time:
            tau += float(self._last_solve_sec)
        if tau > self._smith_max_tau_sec:
            tau = self._smith_max_tau_sec
        if tau <= 1e-3:
            return state

        v, w = self._smith_pick_velocity()

        theta = float(state[2, 0])
        rolled = state.copy()
        rolled[0, 0] = float(state[0, 0]) + v * cos(theta) * tau
        rolled[1, 0] = float(state[1, 0]) + v * sin(theta) * tau
        rolled[2, 0] = float(state[2, 0]) + w * tau
        return rolled

    def _smith_pick_velocity(self):
        """Choose (v, w) to forward-roll during the predictor's tau window.
        Honors `smith_predictor.velocity_source` (`odom`|`cmd`) with
        automatic fallback when odom is stale/missing."""
        if self._smith_velocity_source == "cmd":
            return self._last_cmd_v, self._last_cmd_w
        # default: odom (with fallback)
        if (
            self._last_odom_t is not None
            and (time.time() - self._last_odom_t) <= self._odom_stale_threshold
        ):
            return self._last_odom_v, self._last_odom_w
        rospy.logwarn_throttle(
            5.0,
            "[F2] odom unavailable/stale; predictor using last cmd as fallback",
        )
        return self._last_cmd_v, self._last_cmd_w

    # generate ros message
    def generate_path_msg(self, path_list):

        path = Path()
        path.header.frame_id = self.config["frame"]["map"]
        path.header.stamp = rospy.Time.now()
        path.header.seq = 0

        for index, point in enumerate(path_list):
            ps = PoseStamped()
            ps.header.frame_id = self.config["frame"]["map"]
            ps.header.seq = index

            ps.pose.position.x = point[0, 0]
            ps.pose.position.y = point[1, 0]
            ps.pose.orientation = self.yaw_to_quat(point[2, 0])

            path.poses.append(ps)

        return path

    def generate_twist_msg(self, vel):

        if vel is None:
            return Twist()

        speed = vel[0, 0]
        steer = vel[1, 0]

        if self.stop or self.arrive:
            # print('stop flag true')
            return Twist()

        else:
            action = Twist()

            action.linear.x = speed
            action.angular.z = steer

            return action

    def generate_dune_points_markers_msg(self):

        marker_array = MarkerArray()

        if self.neupan_planner.dune_points is None:
            return
        else:
            points = self.neupan_planner.dune_points

            for index, point in enumerate(points.T):

                marker = Marker()
                marker.header.frame_id = self.config["frame"]["map"]
                marker.header.seq = 0
                marker.header.stamp = rospy.get_rostime()

                marker.scale.x = self.config["marker_size"]
                marker.scale.y = self.config["marker_size"]
                marker.scale.z = self.config["marker_size"]
                marker.color.a = 1.0

                marker.color.r = 160 / 255
                marker.color.g = 32 / 255
                marker.color.b = 240 / 255

                marker.id = index
                marker.type = 1
                marker.pose.position.x = point[0]
                marker.pose.position.y = point[1]
                marker.pose.position.z = 0.3
                marker.pose.orientation = Quaternion()

                marker_array.markers.append(marker)

            return marker_array

    def generate_nrmp_points_markers_msg(self):

        marker_array = MarkerArray()

        if self.neupan_planner.nrmp_points is None:
            return
        else:
            points = self.neupan_planner.nrmp_points

            for index, point in enumerate(points.T):

                marker = Marker()
                marker.header.frame_id = self.config["frame"]["map"]
                marker.header.seq = 0
                marker.header.stamp = rospy.get_rostime()

                marker.scale.x = self.config["marker_size"]
                marker.scale.y = self.config["marker_size"]
                marker.scale.z = self.config["marker_size"]
                marker.color.a = 1.0

                marker.color.r = 255 / 255
                marker.color.g = 128 / 255
                marker.color.b = 0 / 255

                marker.id = index
                marker.type = 1
                marker.pose.position.x = point[0]
                marker.pose.position.y = point[1]
                marker.pose.position.z = 0.3
                marker.pose.orientation = Quaternion()

                marker_array.markers.append(marker)

            return marker_array

    def generate_robot_marker_msg(self):

        marker = Marker()

        marker.header.frame_id = self.config["frame"]["map"]
        marker.header.seq = 0
        marker.header.stamp = rospy.get_rostime()

        marker.color.a = 1.0
        marker.color.r = 0 / 255
        marker.color.g = 255 / 255
        marker.color.b = 0 / 255

        marker.id = 0

        if self.neupan_planner.robot.shape == "rectangle":
            length = self.neupan_planner.robot.length
            width = self.neupan_planner.robot.width
            wheelbase = self.neupan_planner.robot.wheelbase

            marker.scale.x = length
            marker.scale.y = width
            marker.scale.z = self.config["marker_z"]

            marker.type = 1

            x = self.robot_state[0, 0]
            y = self.robot_state[1, 0]
            theta = self.robot_state[2, 0]

            if self.neupan_planner.robot.kinematics == "acker":
                diff_len = (length - wheelbase) / 2
                marker_x = x + diff_len * cos(theta)
                marker_y = y + diff_len * sin(theta)
            else:
                marker_x = x
                marker_y = y

            marker.pose.position.x = marker_x
            marker.pose.position.y = marker_y
            marker.pose.position.z = 0
            marker.pose.orientation = self.yaw_to_quat(self.robot_state[2, 0])

        return marker

    @staticmethod
    def yaw_to_quat(yaw):

        quater = Quaternion()

        quater.x = 0
        quater.y = 0
        quater.z = sin(yaw / 2)
        quater.w = cos(yaw / 2)

        return quater

    @staticmethod
    def quat_to_yaw(quater):

        x = quater.x
        y = quater.y
        z = quater.z
        w = quater.w

        raw = atan2(2 * (w * z + x * y), 1 - 2 * (pow(z, 2) + pow(y, 2)))

        return raw


if __name__ == "__main__":
    try:
        neupan_node = neupan_core()
        neupan_node.run()
    except rospy.ROSInterruptException:
        pass
