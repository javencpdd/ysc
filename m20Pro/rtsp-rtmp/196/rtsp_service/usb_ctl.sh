#!/bin/bash

GPIO_PIN=125

if [[ $# -ne 1 ]]; then
    echo "Usage: $0 <enable|disable>"
    exit 1
fi

if [[ "$1" == "enable" ]]; then
    echo $GPIO_PIN > /sys/class/gpio/export
    echo "out" > /sys/class/gpio/gpio$GPIO_PIN/direction
    echo 1 > /sys/class/gpio/gpio$GPIO_PIN/value
    echo "GPIO $GPIO_PIN enabled and set to 1"
elif [[ "$1" == "disable" ]]; then
    echo 0 > /sys/class/gpio/gpio$GPIO_PIN/value
    echo $GPIO_PIN > /sys/class/gpio/unexport
    echo "GPIO $GPIO_PIN disabled"
else
    echo "Invalid argument. Usage: $0 <enable|disable>"
    exit 1
fi

# 定义自动补全函数
_my_script_completion() {
    local cur=${COMP_WORDS[COMP_CWORD]}
    local options="enable disable"  # 这里列出了可能的选项

    # 使用compgen命令生成补全列表
    COMPREPLY=( $(compgen -W "${options}" -- ${cur}) )
}

# 注册自动补全函数，使用脚本名称作为参数
complete -F _my_script_completion "$(basename "$0")"

