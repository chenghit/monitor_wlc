#!/usr/bin/env python3

import re
import json
import logging
from netmiko import Netmiko

from sendEmail.send_email import send_email


log_path = 'monitor_wlc.log'
log_format = '%(asctime)s %(funcName)s:%(levelname)s:%(message)s'
logging.basicConfig(level='INFO', filename=log_path, format=log_format)
CMD_AP_SUMMARY = 'show ap summary'
CMD_AUTO_RF = 'show ap auto-rf 802.11a '


gaoke_wlc = {
    'host': '10.124.37.52',
    'username': 'admin',
    'password': password,
    'device_type': 'cisco_wlc'
}

net_connect = Netmiko(**gaoke_wlc)
output_ap_summary = net_connect.send_command(CMD_AP_SUMMARY).split('\n')
mac_pattern = re.compile(r'(?:[0-9a-fA-F]:?){12}')
json_path = 'wlc_ap_data.json'


def updateApNameModelClientsDict(ap_dict, output_ap_summary):
    '''
    :param output_ap_summary: "show ap summary" 的输出结果
    :return: 以下格式的字典：
        {
        'ApName1': {
             'ap_model': 'AIR-AP2802E-H-K9',
             'clients': 40
            },
        'ApName2': {
             'ap_model': 'C9120AXI-H',
             'clients': 5
            }
        }
    '''
    for line in output_ap_summary:
        s = re.search(mac_pattern, line)
        if s is not None:
            line = line.split()
            try:
                ap_dict.update({line[0]: {'ap_model': line[2], 'clients': int(line[8])}})
            except ValueError:
                ap_dict.update({line[0]: {'ap_model': line[2], 'clients': int(line[7])}})
    return ap_dict


def findNearbyAps(ap_name):
    '''
    :param ap_name: AP Name
    :return: 根据 "show ap auto-rf 802.11a <ap_name>" 的结果，取 RSSI 大于等于 -50 dBm
    的 Nearby AP，返回以下格式的字典：
        {
        'NearbyApName1':{
            'rssi': -40
            },
        'NearbyApName2':{
            'rssi': -40
            }
        }
    '''
    output_auto_rf = net_connect.send_command(CMD_AUTO_RF + ap_name).split('\n')
    pattern = re.compile(r'(-\d\d) dBm.+\)  (\S+)')
    dct = {}
    for line in output_auto_rf:
        m = re.findall(pattern, line)
        if len(m) > 0 and int(m[0][0]) >= -50:
            dct.update({m[0][1]: {'rssi': int(m[0][0])}})
    return dct


def updateNearbyAps(ap_dict):
    '''
    为 AP 字典补充 Nearby 信息
    :param ap_dict: AP 字典
    :return: 以下格式的字典：
        {
        'ApName1': {
            'ap_model': 'AIR-AP2802E-H-K9',
            'clients': 40,
            'nearby_aps': {
                'NearbyApName1':{
                    'rssi': -40
                    },
                'NearbyApName2':{
                    'rssi': -40
                    }
                }
            },
        'ApName2': {
            'ap_model': 'C9120AXI-H',
            'clients': 5,
            'nearby_aps': {}
            }
        }
    '''
    for ap_name in ap_dict.keys():
        nearby_dict = findNearbyAps(ap_name)
        ap_dict[ap_name].update({'nearby_aps': nearby_dict})
    return ap_dict


def compareClients(ap_dict):
    '''
    如果 C9120 AP 的客户端数量少于等于 5，并且它的 Nearby 客户端数量大于等于 40，则将异常信息以列表
    的格式返回。
    AP 检测到的 Nearby 并不完整，所以需要双向查找，以提高监控成功率。
    :param ap_dict: AP 字典
    :return: 以下格式的列表，列表中每个 item 都是一个元组：
    [(<C9120的客户端数量>, <C9120的AP名称>, <它的邻居的客户端数量>, <邻居的AP名称>), (略...)]
    '''
    abnormal_list = []
    for ap_name in ap_dict.keys():
        logging.info('正在检查{}和它邻居AP的客户端数量'.format(ap_name))
        clients = ap_dict[ap_name]['clients']
        if 'C9120AX' in ap_dict[ap_name]['ap_model'] and clients <= 5 and \
                len(ap_dict[ap_name]['nearby_aps']) > 0:
            for nearby in ap_dict[ap_name]['nearby_aps'].keys():
                nearby_clients = ap_dict[nearby]['clients']
                if nearby_clients >= 40:
                    abnormal_list.append((ap_name, clients, nearby, nearby_clients))
        elif clients >= 40 and len(ap_dict[ap_name]['nearby_aps']) > 0:
            for nearby in ap_dict[ap_name]['nearby_aps'].keys():
                nearby_clients = ap_dict[nearby]['clients']
                if nearby_clients <= 5 and 'C9120AX' in ap_dict[nearby]['ap_model']:
                    abnormal_list.append((nearby, nearby_clients, ap_name, clients))
        logging.info('{}检查完毕'.format(ap_name))
    return abnormal_list


def alert(abnormal_list):
    '''
    如果发现异常则调用send_email模块发出告警邮件。
    :param abnormal_list: 异常列表
    '''
    lst = []
    message = ''
    if len(abnormal_list) == 0:
        logging.info('没有检测到异常')
    else:
        for i in abnormal_list:
            msg = '{} 只有 {} 个客户端，但它旁边的 {} 有 {} 个客户端'.format(*i)
            logging.warning(msg)
            lst.append(msg)
        message = '\n'.join(lst)

    if message != '':
        send_email(message)
        logging.info('已发送告警邮件')


def main(json_path):
    '''
    AP 检测到的 Nearby 不完整，所以每一次运行脚本，都需要更新 Nearby 信息，而不是清空并重写
    Nearby 信息。因此需要将相关信息存储在 json 文件中。
    '''
    try:
        with open(json_path, 'r', encoding='utf-8') as json_file:
            ap_dict = json.load(json_file)
    except IOError:
        ap_dict = {}

    ap_dict = updateApNameModelClientsDict(ap_dict, output_ap_summary)
    ap_dict = updateNearbyAps(ap_dict)
    json_str = json.dumps(ap_dict, indent=4)
    with open(json_path, 'w', encoding='utf-8') as json_file:
        json_file.write(json_str)
    abnormal_list = compareClients(ap_dict)
    alert(abnormal_list)


if __name__ == '__main__':
    main(json_path)
    print()
    print('-' * 80)
    print()
    print('执行完毕，请检查日志文件 {}'.format(log_path))
    print()
    print('-' * 80)
    print()