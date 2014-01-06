#
# Copyright 2014 OpenStack Foundation
# All Rights Reserved
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

import time

from neutronclient.common import exceptions as neutron_client_exc
from oslo.config import cfg

from ironic.common import neutronv2
from ironic.openstack.common.gettextutils import _
from ironic.openstack.common import log as logging


# -- dekehn these are going to have to be sorted out!!!!
# from nova.network.security_group import openstack_driver


neutron_opts = [
    cfg.StrOpt('neutron_url',
               default='http://127.0.0.1:9696',
               help='URL for connecting to neutron'),
    cfg.IntOpt('neutron_url_timeout',
               default=30,
               help='timeout value for connecting to neutron in seconds'),
    cfg.StrOpt('neutron_admin_username',
               help='username for connecting to neutron in admin context'),
    cfg.StrOpt('neutron_admin_password',
               help='password for connecting to neutron in admin context',
               secret=True),
    cfg.StrOpt('neutron_admin_tenant_name',
               help='tenant name for connecting to neutron in admin context'),
    cfg.StrOpt('neutron_admin_auth_url',
               default='http://localhost:5000/v2.0',
               help='auth url for connecting to neutron in admin context'),
    cfg.BoolOpt('neutron_api_insecure',
                default=False,
                help='if set, ignore any SSL validation issues'),
    cfg.StrOpt('neutron_auth_strategy',
               default='keystone',
               help='auth strategy for connecting to '
                    'neutron in admin context'),
    cfg.StrOpt('neutron_ca_certificates_file',
                help='Location of ca certificates file to use for '
                     'neutron client requests.'),
   ]

CONF = cfg.CONF
CONF.register_opts(neutron_opts)
LOG = logging.getLogger(__name__)


class neutronAPI(object):
    """API for communicating to neutron 2.x API."""

    def udpate_port(self, context, port_id, **kwargs):
        """Update a port's attributes.

        :param port_id: designated which port these attributes
             will be applied to.
        :param dhcp_options: Optional DHCP options.
        """
        port = {}
        start_time = time.time()
        neutron_client = neutronv2.get_client(context)
        dhcp_opts = kwargs.get('dhcp_options', None)
        if port_id:
            port_req_body = {'port': {'id': port_id}}
        if dhcp_opts is not None:
            port_req_body['port']['extra_dhcp_opts'] = dhcp_opts
        try:
            if port_req_body['port']:
                neutron_client.update_port(port_id, port_req_body)
                port = neutron_client.show_port(port_id)['port']
        except neutron_client_exc.NeutronClientException:
            LOG.exception(_('Neutron error updating port: %s') %
                          str(port_id))
            raise

        LOG.debug(_("Neutron update_port call took %4.2f seconds") %
                  (time.time() - start_time))

        return port
