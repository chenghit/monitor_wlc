#!/usr/bin/env python3

import json
import logging
from ttp import ttp
from netmiko import Netmiko
from collections import defaultdict

from sendEmail.send_email import send_email


log_path = 'monitor_wlc.log'
json_path = 'wlc_ap_data.json'
log_format = '%(asctime)s %(funcName)s:%(levelname)s:%(message)s'
logging.basicConfig(level='INFO', filename= log_path, format=log_format)
cmd_ap_inventory = 'show ap inventory all'
cmd_auto_rf = 'show ap auto-rf 802.11a '

inventory_template = '''
<group name="{{ ap_name }}" del="name, descr, vid, sn">
Inventory for {{ ap_name }}

NAME: {{ name }}    , DESCR: {{ descr }}
PID: {{ pid }},  VID: {{ vid }},  SN: {{ sn }}
</group>
'''

# ttp 内置的 greaterthan 函数不生效，所以无法直接过滤 rssi 值，只能后期处理
auto_rf_template = '''
<group name="{{ ap_name }}**">
AP Name.......................................... {{ ap_name }}
    Attached Clients............................. {{ clients | to_int }} clients
</group>
<group name="{{ ap_name }}.nearby.{{ nearby_name }}**" del="mac, channel, BW, ip">
    AP {{ mac }} slot 1..................  {{ rssi | to_int }} dBm on  {{ channel }}  {{ BW }} ({{ ip }})  {{ nearby_name }}
</group>
'''

gaoke_wlc = {
    'host': '10.*.*.*',
    'username': 'admin',
    'password': '***',
    'device_type': 'cisco_wlc'
}

net_connect = Netmiko(**gaoke_wlc)
output_ap_inventory = net_connect.send_command(cmd_ap_inventory)


def parserTtp(data, template):
    parser = ttp(data, template)
    parser.parse()
    return parser.result()


def mergeDicts(*args):
    dct = defaultdict(list)
    for d in args:
        for key, value in d.items():
            dct[key].append(value)
    return dct


def getApNamePid():
    return parserTtp(output_ap_inventory, inventory_template)[0][0]


def getClientsNearby(ap_name):
    output_auto_rf = net_connect.send_command(cmd_auto_rf + ap_name)
    return parserTtp(output_auto_rf, auto_rf_template)[0][0]


def compareClients(ap_dict):
    '''
    如果 C9120 AP 的客户端数量少于等于 5，并且它的 RSSI 大于 -49 dBm 的 Nearby 的客户端数量大于等于 40，
    则将异常信息以列表的格式返回。
    AP 检测到的 Nearby 并不完整，所以需要双向查找，以提高监控成功率。
    :param ap_dict: AP 字典
    :return: 以下格式的列表，列表中每个 item 都是一个元组：
    [(<C9120的客户端数量>, <C9120的AP名称>, <它的邻居的客户端数量>, <邻居的AP名称>), (略...)]
    '''
    abnormal_list = []
    for ap_name in ap_dict.keys():
        clients = ap_dict[ap_name][1]['clients']
        if 'C9120AX' in ap_dict[ap_name][0]['pid'] and clients <= 5 and \
                'nearby' in ap_dict[ap_name][1].keys():
            for nearby in ap_dict[ap_name][1]['nearby'].keys():
                if nearby['rssi'] > -49:
                    nearby_clients = ap_dict[nearby][1]['clients']
                    if nearby_clients >= 40:
                        abnormal_list.append((ap_name, clients, nearby, nearby_clients))
        elif clients >= 40 and 'nearby' in ap_dict[ap_name][1].keys():
            for nearby in ap_dict[ap_name][1]['nearby'].keys():
                if nearby['rssi'] > -49:
                    nearby_clients = ap_dict[nearby][1]['clients']
                    if nearby_clients <= 5 and 'C9120AX' in ap_dict[nearby][0]['pid']:
                        abnormal_list.append((nearby, nearby_clients, ap_name, clients))
    return abnormal_list


def alert(abnormal_list):
    '''
    如果发现异常则调用send_email模块发出告警邮件。
    :param abnormal_list: 异常列表
    '''
    lst = []
    message = ''
    if len(abnormal_list) == 0:
        msg = '没有检测到客户端数量异常的C9120'
        print(msg)
        logging.info(msg)
    else:
        for i in abnormal_list:
            msg = '{} 只有 {} 个客户端，但它旁边的 {} 有 {} 个客户端'.format(*i)
            print(msg)
            logging.warning(msg)
            lst.append(msg)
        message = '\n'.join(lst)

    if message != '':
        send_email(message)
        msg = '已发送告警邮件'
        print(msg)
        logging.info(msg)


def main():

    name_pid = getApNamePid()
    print('已获取 AP Name 和 PID 信息')
    print('正在获取 AP 客户端数量和 Nearby 信息')

    clients_nearby = {}
    for i in name_pid.keys():
        clients_nearby.update(getClientsNearby(i))

    ap_dict = mergeDicts(name_pid, clients_nearby)
    json_str = json.dumps(ap_dict, indent=4)
    with open(json_path, 'w', encoding='utf-8') as json_file:
        json_file.write(json_str)
    print('已经完成所有 AP 的信息获取，正在检索客户端数量异常的 C9120 AP')

    abnormal_list = compareClients(ap_dict)
    print('检索完成')
    alert(abnormal_list)


if __name__ == '__main__':
    print()
    print('-' * 80)
    print()
    main()
    logging.info('程序执行完毕')
    print()
    print('-' * 80)
    print()
    print('执行完毕，请检查日志文件 {}'.format(log_path))
    print()
    print('-' * 80)
    print()
