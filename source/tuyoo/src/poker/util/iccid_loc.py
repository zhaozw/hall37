# -*- coding: utf-8 -*-
'''
Created on 2015-5-12
@author: zqh
'''

import re

_iccid2prov_map = {
    '01': 10,
    '09': 20,
    '02': 30,
    '31': 40,
    '05': 01,
    '04': 03,
    '03': 05,
    '06': 11,
    '07': 13,
    '08': 15,
    '10': 21,
    '12': 23,
    '15': 25,
    '11': 31,
    '14': 33,
    '13': 35,
    '18': 41,
    '17': 43,
    '16': 45,
    '19': 51,
    '20': 53,
    '23': 55,
    '21': 57,
    '22': 61,
    '24': 65,
    '26': 71,
    '27': 73,
    '29': 75,
    '28': 81,
    '30': 83,
    '25': 85,
}

_match_iccid = re.compile('^[0-9]{10,20}$')


def getProvId(iccid):
    '''
    因为目前只是对中国移动的手机有按省份切换支付方式的需求，
    这里只提供移动的ICCID的省份转换
    '''
    if not iccid or not _match_iccid.match(iccid):
        return -2
    operator = iccid[4:6]
    if operator == '00':  # CMCC
        provid = iccid[8:10]
        try:
            return _iccid2prov_map[provid]
        except:
            return -1
    return -2