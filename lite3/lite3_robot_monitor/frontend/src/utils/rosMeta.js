/**
 * ROS 数据源元数据描述符。
 *
 * 用途：给监控数据区提供悬停提示所需的 ROS 话题名、消息类型、字段结构与示例。
 * 内容依据 `backend/ros_bridge_node.py` 的实际订阅与组帧逻辑整理，务必与之保持一致。
 *
 * 接入新的监控数据源时：在这里追加一个 area 描述符即可，
 * 前端无需改动（RosInfoTip 按 area 取值，取不到会走兜底文案）。
 */

/** 单个字段说明 */
// { name: 字段名, type: 类型, unit: 单位, desc: 说明, from: 来源字段（可选） }

export const ROS_META = {
  imu: {
    area: 'imu',
    label: 'IMU 姿态与加速度',
    topics: [{ name: '/imu/data', type: 'sensor_msgs/Imu' }],
    /** 从 ROS 消息到本系统字段的映射关系 */
    mapping: [
      { from: 'orientation (x, y, z, w)', to: 'imu.roll / imu.pitch / imu.yaw', note: '四元数经 quat_to_rpy 转成欧拉角' },
      { from: 'angular_velocity (x, y, z)', to: 'imu.roll_vel / imu.pitch_vel / imu.yaw_vel', note: 'rad/s' },
      { from: 'linear_acceleration (x, y, z)', to: 'imu.x_acc / imu.y_acc / imu.z_acc', note: 'm/s²' }
    ],
    fields: [
      { name: 'imu.roll / pitch / yaw', type: 'float64', unit: 'rad', desc: '横滚 / 俯仰 / 偏航角' },
      { name: 'imu.roll_vel / pitch_vel / yaw_vel', type: 'float64', unit: 'rad/s', desc: '三轴角速度' },
      { name: 'imu.x_acc / y_acc / z_acc', type: 'float64', unit: 'm/s²', desc: '三轴线性加速度' }
    ],
    example: '{\n  "imu": {\n    "roll": 0.012, "pitch": -0.031, "yaw": 1.204,\n    "roll_vel": 0.00, "pitch_vel": 0.01, "yaw_vel": -0.02,\n    "x_acc": 0.02, "y_acc": 0.01, "z_acc": 9.79\n  }\n}',
    caveats: []
  },

  odom: {
    area: 'odom',
    label: '位姿与速度（世界系）',
    topics: [{ name: '/leg_odom2', type: 'nav_msgs/Odometry' }],
    mapping: [
      { from: 'pose.pose.position (x, y)', to: 'position.x / position.y', note: 'm' },
      { from: 'pose.pose.orientation (x, y, z, w)', to: 'position.yaw', note: '取四元数中的偏航角，rad' },
      { from: 'twist.twist.linear (x, y)', to: 'velocity.x / velocity.y', note: 'm/s，世界系' },
      { from: 'twist.twist.angular.z', to: 'velocity.yaw', note: 'rad/s' }
    ],
    fields: [
      { name: 'position.x / y', type: 'float64', unit: 'm', desc: '世界系平面位置' },
      { name: 'position.yaw', type: 'float64', unit: 'rad', desc: '世界系朝向' },
      { name: 'velocity.x / y', type: 'float64', unit: 'm/s', desc: '世界系线速度' },
      { name: 'velocity.yaw', type: 'float64', unit: 'rad/s', desc: '世界系角速度' },
      { name: 'velocity_body.x / y / yaw', type: 'float64', unit: 'm/s, rad/s', desc: '机体系速度' }
    ],
    example: '{\n  "position": { "x": 1.204, "y": -0.318, "yaw": 0.876 },\n  "velocity": { "x": 0.15, "y": 0.00, "yaw": -0.03 }\n}',
    caveats: [
      '⚠️ velocity_body 目前 ROS 侧只初始化为 0，桥接节点未从话题填充，故恒为 0.00（机体系速度请暂以世界系为准）。'
    ]
  },

  joint: {
    area: 'joint',
    label: '12 个关节角度与角速度',
    topics: [
      { name: '/joint_states', type: 'sensor_msgs/JointState' }
    ],
    mapping: [
      { from: 'name[i]', to: 'joint_names[i]', note: '按名称前缀映射到 12 关节序号' },
      { from: 'position[i]', to: 'joint[i]', note: 'rad' },
      { from: 'velocity[i]', to: 'velocity[i]', note: 'rad/s' }
    ],
    fields: [
      { name: 'joint_names', type: 'string[12]', unit: '', desc: '关节名，缺失时退化为 joint_N' },
      { name: 'joint', type: 'float64[12]', unit: 'rad', desc: '关节角度' },
      { name: 'velocity', type: 'float64[12]', unit: 'rad/s', desc: '关节角速度' }
    ],
    example: '{\n  "joint_names": ["LF_hip_x", "LF_thigh", "LF_calf", ...],\n  "joint": [0.02, 0.51, -0.93, ...],\n  "velocity": [0.0, 0.01, -0.02, ...],\n  "unit": "rad"\n}',
    caveats: [
      '关节顺序：左前 → 右前 → 左后 → 右后（LF / RF / LB / RB），每腿 侧摆(hip) / 髋(thigh) / 膝(calf)。',
      '名称映射规则：leg 取 LF/RF/LB/RB 前缀，hip→0、thigh→1、calf→2，序号 = leg*3 + part；名称不匹配则跳过。'
    ]
  }
}

/**
 * 取指定区域的 ROS 元数据。
 * @param {string} area imu | odom | joint
 * @returns {object|null} 未登记时返回 null，由调用方展示兜底文案
 */
export function getRosMeta(area) {
  return ROS_META[area] || null
}

/** 已登记的 area 列表（便于接入方自检） */
export const ROS_AREAS = Object.keys(ROS_META)
