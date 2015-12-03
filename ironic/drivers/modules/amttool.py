# coding=utf-8

# Copyright 2015 Hewlett-Packard Development Company, L.P.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import os
import re
# sometimes you just need to sleep
import time

from oslo_concurrency import processutils
from oslo_config import cfg
from oslo_log import log as logging
from oslo_utils import excutils

from ironic.common import boot_devices
from ironic.common import exception
from ironic.common.i18n import _
from ironic.common.i18n import _LE
from ironic.common.i18n import _LW
from ironic.common import paths
from ironic.common import states
from ironic.common import utils
from ironic.conductor import task_manager
from ironic.drivers import base

CONF = cfg.CONF

opts = [
    cfg.StrOpt('amttool_path',
               default='/usr/local/bin/amtctrl',
               help='Path to the amttool executable'),
]

opt_group = cfg.OptGroup(name='amt',
                         title='Options for the AMT power driver')
CONF.register_group(opt_group)
CONF.register_opts(opts, opt_group)

LOG = logging.getLogger(__name__)

REQUIRED_PROPERTIES = {
    'amt_address': _('IP address or host name of the node. Required.'),
    'amt_password': _('Password. Required.'),
    }


POWER_MAP = {
    'on': states.POWER_ON,
    'off': states.POWER_OFF,
    'reboot': states.REBOOT
}


BOOT_DEVICE_MAP = {
    boot_devices.PXE: 'pxe',
    boot_devices.DISK: 'hd'
}

def _unprep_amttool(info):
    args = [
            CONF.amt.amttool_path,
            'rm',
            info['address']
            ]
    try:
        out, err = utils.execute(*args)
    except processutils.ProcessExecutionError as e:
        LOG.error(e)
        raise exception.AMTFailure('_unprep_amttool')
    else:
        return out, err

def _prep_amttool(info):
    args = [
            CONF.amt.amttool_path,
            'add',
            info['address'],
            info['address'],
            info['password']
            ]
    try:
        out, err = utils.execute(*args)
    except processutils.ProcessExecutionError as e:
        LOG.error(e)
        raise exception.AMTFailure('_prep_amttool')
    else:
        return out, err

def _exec_amttool(info, command):
    args = [
            CONF.amt.amttool_path,
            info['address'],
            command
            ]
    try:
        out, err = utils.execute(*args)
    except processutils.ProcessExecutionError as e:
        LOG.error(e)
        raise exception.AMTFailure(cmd=command)
    else:
        return out, err


def _get_power_state(driver_info):
    _unprep_amttool(driver_info)
    _rep_amttool(driver_info)
    out, err = _exec_amttool(driver_info, 'status')

    ps = ''
    for line in out.split('\n'):
        if line.startswith('on'):
            ps = 'on'
            break
        elif line.startswith('off'):
            ps = 'off'
            break
        elif line.startswith('reboot'):
            ps = 'reboot'
            break
    ps = POWER_MAP[ps]
    if not ps:
        raise exception.PowerStateFailure(pstate=None)
    return ps


def _power_on(driver_info, device=''):
    _unprep_amttool(driver_info)
    _rep_amttool(driver_info)

    command = 'on'
    if device == 'pxe':
        command = 'pxeboot'

    out, err = _exec_amttool(driver_info, command)

    return _get_power_state(driver_info)

def _power_off(driver_info):
    _unprep_amttool(driver_info)
    _rep_amttool(driver_info)
    out, err = _exec_amttool(driver_info, 'off')

    return _get_power_state(driver_info)

def _reboot(driver_info):
    _unprep_amttool(driver_info)
    _rep_amttool(driver_info)
    out, err = _exec_amttool(driver_info, 'reboot')

    return _get_power_state(driver_info)        


def _parse_driver_info(node):
    address = node.driver_info.get('amt_address')
    password = node.driver_info.get('amt_password')
    if not address or not password:
        raise exception.InvalidParamterValue(_(
            "Missing one or more of the following required parameters: %s."
            ) % REQUIRED_PROPERTIES.keys())
    return {'address': address,
            'password': password
    }


class AMTPower(base.PowerInterface):

    def __init__(self):
        if not os.path.exists(CONF.amt.amttool_path):
            raise exception.DriverLoadError(
                driver=self.__class__.__name__,
                reason=(_("Unable to locate amttool binary at the configured "
                         "path %s") % CONF.amt.amttool_path)
            )

    def get_properties(self):
        return REQUIRED_PROPERTIES

    def validate(self, task):
        _parse_driver_info(task.node)

    def get_power_state(self, task):
        driver_info = _parse_driver_info(task.node)
        return _get_power_state(driver_info)

    @task_manager.require_exclusive_lock
    def set_power_state(self, task, pstate):
        driver_info = _parse_driver_info(task.node)
        driver_internal_info = task.node.driver_internal_info

        if pstate == states.POWER_ON:
            requested_dev = driver_internal_info.get('amt_boot_device')
            if requested_dev:
                state = _power_on(driver_info,
                                  device=BOOT_DEVICE_MAP[requested_dev])
                if not driver_internal_info.get('amt_boot_persistent'):
                    del(driver_internal_info['amt_boot_device'])
                    del(driver_internal_info['amt_boot_persistent'])
                    task.node.driver_internal_info = driver_internal_info
            else:
                state = _power_on(driver_info)
        elif pstate == states.POWER_OFF:
            state = _power_off(driver_info)
        elif pstate == states.REBOOT:
            state = _reboot(driver_info)
        else:
            raise exception.InvalidParameterValue(_("set_power_state called "
                    "with invalid power state %s.") % pstate)

        if state != pstate:
            raise exception.PowerStateFailure(pstate=pstate)

    @task_manager.require_exclusive_lock
    def reboot(self, task):
        self.set_power_state(task, states.REBOOT)


class AMTManagement(base.ManagementInterface):

    def get_properties(self):
        return REQUIRED_PROPERTIES

    def validate(self, task):
        _parse_driver_info(task.node)

    def get_supported_boot_devices(self):
        return [boot_devices.PXE, boot_devices.DISK]

    def set_boot_device(self, task, device, persistent=False):
        if device not in self.get_supported_boot_devices():
            raise exception.InvalidParameterValue(_(
                "Invalid boot device %s specified.") % device)

        # AMT/vPro doesn't support set boot_device persistent, so we have to
        # save amt_boot_device/amt_boot_persistent in driver_internal_info.
        driver_internal_info = task.node.driver_internal_info
        driver_internal_info['amt_boot_device'] = device
        driver_internal_info['amt_boot_persistent'] = persistent
        task.node.driver_internal_info = driver_internal_info
        task.node.save()

    def get_boot_device(self, task):
        driver_internal_info = task.node.driver_internal_info
        device = driver_internal_info.get('amt_boot_device')
        persistent = driver_internal_info.get('amt_boot_persistent')
        if not device:
            device = amt_common.DEFAULT_BOOT_DEVICE
            persistent = True
        return {'boot_device': device,
                'persistent': persistent}

    def get_sensors_data(self, task):
        raise NotImplementedError()
