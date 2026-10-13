# 绝影 Lite3 运动主机 UDP 通讯接口（协议摘录）

> **来源**：钉钉文档《运动主机通讯接口》（alidocs.dingtalk.com，文档 ID `OlnXRxOLAljEbGLp`）
> **抓取时间**：2026-09-16
> **用途**：本工程 `backend/control_protocol.py` 的实现依据。
>
> 本文档为厂商接口文档的**摘录存档**，仅用于本项目开发对照；如需完整内容请访问原始文档。
> 章节结构：1.1 协议格式 → 1.2 控制指令集 → 1.3 接收信息指令集 → 附录（报文实例）。

---

1.1 协议格式

本节介绍UDP传输的原始数据格式。根据是否携带复杂数据，可以将UDP指令分为两类：简单指令和复杂指令。

1.1.1 简单指令

简单指令格式为 [xxxx yyyy zzzz] ，一个字母表示一个字节。
简单指令采用结构体 CommandHead 存储原始数据内容。

struct CommandHead{
uint32_t code;
uint32_t paramters_size;
uint32_t type;
};

﻿xxxx 是 CommandHead.code 的值，表示指令码。
﻿yyyy 是 CommandHead.paramters_size 的值，表示指令码的指令值，当指令码没有有效指令值时，yyyy = 0。
﻿zzzz 是 CommandHead.type 的值，用于区分指令类型，简单指令的类型值为0，即zzzz = 0。
使用案例如下：

//例程
struct CommandHead command_head = {0};
command_head.code = 1; //指令码
command_head.paramters_size = 0;// 指令值
command_head.type = 0; // 指令类型
sendto(sfd,&command_head,sizeof(command_head),目标地址，地址长度)

1.1.2 复杂指令

复杂指令携带具体的数据内容，格式为 [xxxx yyyy zzzz bbbbb……] ，一个字母表示一个字节。
复杂指令采用结构体 Command 存储原始数据内容。

struct CommandHead{
uint32_t code;
uint32_t paramters_size;
uint32_t type;
};

const uint32_t kDataSize = 256;

struct Command{
CommandHead head;
uint32_t data[kDataSize];
};

﻿xxxx 是 Command.head.code 的值，表示指令码。
﻿yyyy 是 Command.head.paramters_size 的值，表示数据内容 bbbbb…… 的长度。
﻿zzzz 是 Command.head.type 的值，用于区分指令类型，复杂指令的类型值为1，即zzzz=1；
﻿bbbbb……是 Command.data 的值，表示该指令携带的数据内容。
使用案例如下：

//例程
int32_t to_be_send_data[64];
struct Command command = {0};
command.head.code = 52; // 指令码
command.head.paramters_size = sizeof(to_be_send_data);// 数据长度
command.type = 1; // 指令类型
memcpy(&command.data,&to_be_send_data,sizeof(to_be_send_data));
sendto(sfd,&command,sizeof(command.head)+command.head.paramters_size,目标地址，地址长度);

1.1.3 复杂指令接收

以关节速度为例，使用案例如下：

struct RobotJointVel{
double joint_vel[12];
}; // 以关节速度为例

struct CommandMessage{
CommandHead command;
uint8_t data_buffer[1024];
};

CommandMessage cm;
size_t recv_size = 0;
recv_size = recvfrom(server_fd,&cm,sizeof(cm),0,(sockaddr*)&client_addr,&sockaddr_in_size);
if(cm.command.type == 1){ // 判断为复杂指令
if(recv_size == cm.command.paramters_size + sizeof(cm.command)){
uint8_t* temp_values = new uint8_t[cm.command.paramters_size];
memcpy(temp_values,cm.data_buffer,cm.command.paramters_size);
if(cm.command.code == 0x0903){ // 判断指令码，解析数据
RobotJointVel *joint_vel = (RobotJointVel *)temp_values;
}
}
}

1.2 控制指令集

开发者通过UDP通信方式直接向运动主机下发指令从而控制机器人实现相应功能。但请注意，下发消息并不能改变原有的控制逻辑。
绝影Lite3同时能接收来自多个手柄的消息，即0x2*******的指令可以由多个客户端下发，但推流仅能推向最早连接上机器人的客户端。

1.2.1 心跳

心跳用于确认连接是否正常，下发频率应不低于2Hz。
指令码
指令值
指令类型

0x21040001
-

【注意】 指令值中-减号表示指令值没有意义，即指令值不会对指令起作用。

1.2.2 机器人基本状态转换指令

机器人基本状态转换通过给出相应指令实现，如下图所示（括号中是对应的状态值）。

涉及的部分指令如下表所示：
指令名称
指令码
指令值
指令类型
指令功能

起立/趴下
0x21010202
-
在趴下状态和初始站立状态之间轮流切换

软急停
0x21020C0E
-
使机器人软急停

回零
0x21010C05
-
初始化机器人关节

进入AI
0x21010528
-
进入AI状态

退出AI
0x2101052B
-
退出AI状态

1.2.3 轴指令

轴指令是手柄左右摇杆x轴和y轴输出的指令，其取值范围为

。轴指令下发的频率应不低于20Hz。轴指令超时时间为250ms，当机器人超过250ms未收到轴指令时，将自动停止运动。

1.2.3.1 原地模式下的轴指令

原地模式下，客户端发送轴指令给运动主机，可以控制机器人改变身体姿势。如果运动主机超过一秒未收到任何轴指令，系统会认为指令失效，机器人将恢复正常站立姿势。若轴指令值在死区范围内，则视轴指令值为0。
指令名称
指令码
指令值
死区
指令功能

调整横滚角
0x21010131
[-12553,12553]
取正值时向右翻滚

调整俯仰角
0x21010130
[-6553,6553]
取正值时低头

调整身体高度
0x21010102
[-20000,20000]
取正值时抬高身体

调整偏航角
0x21010135
[-9553,9553]
取正值时向右旋转

1.2.3.2 移动模式下和AI状态下的轴指令

移动模式下和AI状态下，下发轴指令给运动主机，可以控制机器人改变移动方向和速度。当轴指令取值在死区范围内时，视其值为0，机器人停止移动。轴指令值的正负确定速度方向。
指令名称
指令码
指令值
死区
指令功能

左右平移
0x21010131
[-12553,12553]
指定机器人y轴上的期望线速度，正值向右

前后平移
0x21010130
[-6553,6553]
指定机器人x轴上的期望线速度，正值向前

左右转弯
0x21010135
[-9553,9553]
指定机器人的期望角速度，正值向右转

1.2.3.3 停止指令

机器人在运动过程中，若下发轴指令为0，机器人将停止运动。

1.2.4 运动模式切换指令

指令名称
指令码
指令值
指令类型

原地模式
0x21010D05
-

移动模式
0x21010D06
-

【注意】 机器人处于AI状态时，该指令无效。

1.2.5 步态切换指令

机器人未进入AI状态且处于移动模式下时，可调整其步态。
指令名称
指令码
指令值
指令类型
指令功能

平地低速步态
0x21010300
-
使机器人从当前步态切换到低速步态

平地中速步态
0x21010307
-
使机器人从当前步态切换到中速步态

平地高速步态
0x21010303
-
使机器人从当前步态切换到高速步态

正常/匍匐
0x21010406
-
使机器人从当前步态切换到匍匐低速行走步态，或从匍匐低速行走步态切至正常低速行走步态

抓地越障步态
0x21010402
-
使机器人从当前步态切换到抓地步态

通用越障步态
0x21010401
-
使机器人从当前步态切换到通用步态

高踏步越障步态
0x21010407
-
使机器人从当前步态切换到高踏步步态

1.2.6 动作指令

机器人未进入AI状态且静止站立或趴下时，可下发动作指令使其表演相应动作。
指令名称
指令码
指令值
指令类型
执行动作的条件

扭身体
0x21010204
-
处于力控状态（静止站立）

翻身
0x21010205
-
趴下状态

太空步
0x2101030C
-
处于力控状态（静止站立）

后空翻
0x21010502
-
趴下状态

打招呼
0x21010507
-
趴下状态

向前跳
0x2101050B
-
趴下状态

扭身跳
0x2101020D
-
处于力控状态（静止站立）

停止动作
0x21010C0B
机器人正在执行扭身体、太空步等持续表演的动作

【注意】 在发送停止动作指令（0x21010C0B）时，需同时发送指令值 0 和 1，以确保机器人能够正确执行停止动作指令。

1.2.7 控制模式切换指令

控制模式决定机器人响应的速度指令来源，自主模式下机器人响应由感知主机下发的速度指令，手动模式下机器人响应由手柄下发的速度指令。
指令名称
指令码
指令值
指令类型
执行动作的条件

自主模式
0x21010C03
-
使机器人从手动模式切入自主模式

手动模式
0x21010C02
-
使机器人从自主模式切入手动模式

【注意】 机器人处于AI状态时，机器人不支持切入自主模式。

1.2.8 保存数据指令

保存数据功能可用于出现故障时使机器人保存前100秒内的数据，机器人将清零电机力矩并关闭运动程序。
指令码
指令值
指令类型

0x21010C01
-

1.2.9 持续运动指令

持续运动开启后，机器人在未进入AI状态且未收到轴指令时也将保持原地踏步。
指令码
指令值
指令类型

0x21010C06
-1=开启，2=关闭

1.2.10 语音指令及扬声器指令

手柄app通过语音功能识别用户语音，并下发携带相应指令值的语音指令来控制机器人运动。
指令码
指令值
指令类型

0x21010C0A
见下表

语音指令值对应的指令功能如下表所示：
指令值
指令值含义

停止语音指令

起立

坐下

前进

后退

向左平移

向右平移

停止

低头

抬头

向左看

向右看

向左转90°

向右转90°

向后转180°

打招呼

扬声器指令：
指令名称
指令码
指令值
指令类型

扬声器指令
0x2101030D
0=关闭扬声器
1=打开扬声器
2=查询扬声器状态

如果发送扬声器指令值为2，即查询扬声器状态，运动主机会上报扬声器状态：
指令码
指令类型
数据内容

0x11050f08
0=关闭状态
1=开启状态

【注意】 机器人收到语音指令后会循环做指令对应的动作，直到收到(0x21010C0A,0,0)指令后结束动作。

1.2.11 感知设置类指令

开发者可向运动主机发送以下指令，以开启或关闭相关功能。
指令名称
指令码
指令值
指令类型

关闭所有AI选项功能
0x21012109
0x00

开启停障
0x21012109
0x20

开启跟随
0x21012109
0xC0

另外，开发者还可向感知主机发送以下指令，目标IP及端口为192.168.1.103:43899。
指令名称
指令码
指令值
指令类型

开启导航避障
0x21012109
0x40

若运动主机IP地址为192.168.1.120，则拉取机器人广角相机视频流的地址为：rtsp://192.168.1.120:8554/test。若运动主机IP地址为192.168.2.1，则拉取机器人广角相机视频流的地址为：rtsp://192.168.2.1:8554/test。
【注意】 机器人使用本节指令包含的功能时，需保证机器人处于非AI状态。

1.2.12 速度指令

速度指令为复杂指令，其携带的数据值均为双精度浮点型，需在自主模式下发送。
指令名称
指令码
指令类型
数据取值范围

指定旋转角速度(rad/s)
0x0141
[-1.5,1.5]

指定前后平移的速度(m/s)
0x0140
[-1.0,1.0]

指定左右平移的速度(m/s)
0x0145
[-0.5,0.5]

1.2.13 AI步态切换指令

机器人处于AI状态时，可切换其AI步态。
指令名称
指令码
指令值
指令类型
指令功能

AI基础步态
0x2101052A
-
使机器人从当前步态换到AI基础步态

AI跳跃步态
0x21010529
-
使机器人从当前步态换到AI跳跃步态

AI站立步态
0x2101052C
-
使机器人从当前步态换到AI站立步态

AI极速步态
0x2101052E
-
使机器人从当前步态换到AI极速步态

【注意】 AI 跳跃和 AI 站立步态仅用于位姿调整。在该步态下，请勿控制机器人运动。

1.2.14 AI动作指令

机器人处于AI状态时，可执行AI步态对应的AI动作。
指令名称
指令码
指令值
指令类型
指令功能
使用条件

AI动作
0x2101030E
表演倒立动作
需要在AI站立步态下使用

表演原地空翻动作
需要在AI跳跃步态下使用

表演原地跳跃动作
需要在AI跳跃步态下使用

停止表演AI动作
在表演倒立动作时使用

【注意】 倒立动作为限时动作，单次最长持续10s；表演结束后机器人自动恢复至四足站立姿态。

1.3 接收信息指令集

用户可按照指令格式获取运动主机上报的信息。

1.3.1 机器人状态信息

指令码
指令类型
数据内容
发送频率

0x0901
结构体RobotStateUpload（具体见下）
50 Hz

struct RobotStateUpload{
int robot_basic_state;
int robot_gait_state;
int robot_policy_state;
double rpy[3];
double rpy_vel[3];
double xyz_acc[3];
double pos_world[3];
double vel_world[3];
double vel_body[3];
unsigned touch_down_and_stair_trot;
bool is_charging;
unsigned error_state;
int robot_motion_state;
double battery_level;
int task_state;
bool is_robot_need_move;
bool zero_position_flag;
bool is_after_first_start;
bool is_voice_ctrl_enable;
double ultrasound[2];
};

字段
类型
含义

robot_basic_state
int
机器人基本运动状态

robot_gait_state
int
机器人当前步态

robot_policy_state
int
机器人当前AI步态

rpy[3]
double
IMU角度信息

rpy_vel[3]
double
IMU角速度信息

xyz_acc[3]
double
IMU加速度信息

pos_world[3]
double
机器人在世界坐标系下的位姿信息

vel_world[3]
double
机器人在世界坐标系下的速度信息

vel_body[3]
double
机器人在身体坐标系下的速度信息

touch_down_and_stair_trot
unsigned
无效数据，仅作占位用

is_charging
bool
无效数据，仅作占位用

error_state
unsigned
无效数据，仅作占位用

robot_motion_state
int
机器人动作状态

battery_level
double
电池电量百分比的小数形式

task_state
int
无效数据，仅作占位用

is_robot_need_move
bool
机器人受外力影响时的平衡状态

zero_position_flag
bool
回零标志位

is_after_first_start
bool
首次开启标志位

is_voice_ctrl_enable
bool
语音控制功能标志位

ultrasound[2]
double
超声波数据

字段 robot_basic_state 的值对应的机器人基本运动状态如下：
变量值
机器人基本运动状态

趴下状态

准备起立状态

正在起立状态

力控状态

正在趴下状态

失控保护状态

姿态调整状态

执行翻身动作

AI状态

回零状态

执行后空翻动作

执行打招呼动作

【注意】 机器人基本状态的转换关系可参考1.2.2。

字段 robot_gait_state 的值对应的机器人步态如下：
变量值
步态

平地低速步态

通用越障步态

平地中速步态

平地高速步态

抓地越障步态

高踏步越障步态

太空步步态

字段 robot_policy_state 的值对应的机器人AI步态如下：
变量值
AI步态

AI基础步态

AI跳跃步态

AI站立步态

AI极速步态

字段 rpy[3] 包含内容如下：

double rpy[3] = {roll,pitch,yaw};

元素名称
含义

roll
IMU在世界坐标系下的roll角(°)

pitch
IMU在世界坐标系下的pitch角(°)

yaw
IMU在世界坐标系下的yaw角(°)

字段 rpy_vel[3] 包含内容如下：

double rpy_vel[3] = {roll_vel,pitch_vel,yaw_vel};

元素名称
含义

roll_vel
IMU在世界坐标系下的roll角速度(rad/s)

pitch_vel
IMU在世界坐标系下的pitch角速度(rad/s)

yaw_vel
IMU在世界坐标系下的yaw角速度(rad/s)

字段 xyz_acc[3] 包含内容如下：

double xyz_acc[3] = { x_acc, y_acc, z_acc };

元素名称
含义

x_acc
IMU在世界坐标系x轴上的加速度(m/s²)

y_acc
IMU在世界坐标系y轴上的加速度(m/s²)

z_acc
IMU在世界坐标系z轴上的加速度(m/s²)

字段 pos_world[3] 包含内容如下：

double pos_world[3] = { x, y, yaw};

元素名称
含义

x
机器人在世界坐标系下的x轴坐标值(m)

y
机器人在世界坐标系下的y轴坐标值(m)

yaw
机器人在世界坐标系下的yaw角(rad)

字段 vel_world[3] 包含内容如下：

double vel_world[3] = {x_vel, y_vel, yaw_vel};

元素名称
含义

x_vel
机器人在世界坐标系x轴上的速度(m/s)

y_vel
机器人在世界坐标系y轴上的速度(m/s)

yaw_vel
机器人在世界坐标系下的yaw角速度(rad/s)

字段 vel_body[3] 包含内容如下：

double vel_body[3] = {x_vel, y_vel, yaw_vel};

元素名称
含义

x_vel
机器人在身体坐标系x轴上的速度(m/s)

y_vel
机器人在身体坐标系y轴上的速度(m/s)

yaw_vel
机器人在身体坐标系下的yaw角速度(rad/s)

字段 robot_motion_state 的值的含义如下：
变量值
机器人动作状态

机器人处于robot_basic_state的值对应的状态中

机器人正在以robot_gait_state的值对应的步态踏步/
机器人正处于robot_policy_state的值对应的A步态

机器人正在执行扭身体

机器人正在执行扭身跳

机器人正在执行向前跳

【注意】 机器人基本运动状态robot_basic_state，机器人步态robot_gait_state/机器人AI状态robot_policy_state，机器人动作状态robot_motion_state共同表示机器人状态，可使用附录2.2进行查询。

字段 is_robot_need_move 的值的含义如下：
变量值
平衡状态

可保持平衡

无法保持平衡，踏步调整姿态

字段 zero_position_flag 的值的含义如下：
变量值
回零状态

未完成回零或已退出回零状态

已完成回零

字段 is_after_first_start 的值的含义如下：
变量值
首次开启状态

非首次开启

首次开启

字段 is_voice_control_enable 的值的含义如下：
变量值
语音控制功能状态

语音控制功能关闭

语音控制功能开启

字段 ultrasound[2] 包含内容如下：

double ultrasound[2] = {forward_distance,backward_distance};

元素名称
含义

forward_distance
机器人前方障碍物的距离 (m)

backward_distance
机器人后方障碍物的距离 (m)

【注意】 超声波有效量程为[0.28m,4.50m]，当障碍物距离小于0.28m时显示为0.28m，当障碍物距离大于4.50m时显示为4.50m。

1.3.2 机器人关节信息

机器人关节信息包括关节角度、关节角速度等信息，指令码如下：
指令名称
指令码
指令类型
数据内容
发送频率

关节角度信息
0x0902
结构RobotJointAngle（具体见下）
100 Hz

关节角速度信息
0x0903
结构体RobotJointVel（具体见下）
100 Hz

/// 机器人关节角度 通道0x0902
struct RobotJointAngle{
double joint_angle[12]; /// 单位 rad
};
/// 机器人关节角速度 通道0x0903
struct RobotJointVel{
double joint_vel[12]; /// 单位rad/s
};

关节信息相关数组中12个关节的排列顺序为：左前侧摆关节、左前髋关节、左前膝关节、右前侧摆关节、右前髋关节、右前膝关节、左后侧摆关节、左后髋关节、左后膝关节、右后侧摆关节、右后髋关节、右后膝关节。

2 附录

2.1 UDP传输数据内容详解

本节以机器人关节角度上传数据为例进行分析。

/* 原始数据 总长度108个字节
* 0209 0000 6000 0000 0100 0000 2efd 3ccf
* 47e4 e1bf f130 4992 f49e e7bf c3d7 eefe
