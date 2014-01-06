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

import copy
import mock
import uuid

from neutronclient.common import exceptions
from neutronclient.v2_0 import client
from oslo.config import cfg

from ironic.common import neutronv2
from ironic.common.neutronv2 import neutron  # noqa
from ironic.openstack.common import context
from ironic.tests import base


CONF = cfg.CONF

#NOTE: Neutron client raises Exception which is discouraged by HACKING.
#      We set this variable here and use it for assertions below to avoid
#      the hacking checks until we can make neutron client throw a custom
#      exception class instead.
NEUTRON_CLIENT_EXCEPTION = Exception


class NeutronClientTestCase(base.TestCase):
    def setUp(self):
        super(NeutronClientTestCase, self).setUp()

    def test_withtoken(self):
        self.config(neutron_url='http://anyhost/',
                    neutron_url_timeout=30)
        my_context = context.RequestContext(user='userid',
                                            tenant='my_tenant',
                                            auth_token='token')
        with mock.patch.object(client.Client, "__init__") as mock_client_init:
            mock_client_init(auth_strategy=None, endpoint_url=CONF.neutron_url,
                             token=my_context.auth_token,
                             timeout=CONF.neutron_url_timeout, insecure=False,
                             ca_cert=None)
            mock_client_init.return_value = None
            neutronv2.get_client(my_context)

    def test_withouttoken(self):
        my_context = context.RequestContext(user='userid',
                                         tenant='my_tenant')
        self.assertRaises(exceptions.Unauthorized,
                          neutronv2.get_client,
                          my_context)

    def test_withtoken_context_is_admin(self):
        self.config(neutron_url='http://anyhost/',
                    neutron_url_timeout=30)
        my_context = context.RequestContext(user='userid',
                                            tenant='my_tenant',
                                            is_admin=True)
        with mock.patch.object(client.Client, "__init__") as mock_client_init:
            mock_client_init(auth_strategy=None, endpoint_url=CONF.neutron_url,
                             token=my_context.auth_token,
                             timeout=CONF.neutron_url_timeout, insecure=False,
                             ca_cert=None)
            mock_client_init.return_value = None
            # Note that although we have admin set in the context we
            # are not asking for an admin client, and so we auth with
            # our own token
            neutronv2.get_client(my_context)

    def test_withouttoken_keystone_connection_error(self):
        self.config(neutron_url='http://anyhost/',
                    neutron_auth_strategy='keystone',
                    neutron_url_timeout=30)
        my_context = context.RequestContext(user='userid',
                                            tenant='my_tenant')
        self.assertRaises(NEUTRON_CLIENT_EXCEPTION,
                          neutronv2.get_client,
                          my_context)


class TestNeutronv2Base(base.TestCase):

    def setUp(self):
        super(TestNeutronv2Base, self).setUp()
        self.context = context.RequestContext(user='userid',
                                              tenant='my_tenantid')
        setattr(self.context,
                'auth_token',
                'bff4a5a6b9eb4ea2a6efec6eefb77936')
        self.instance = {'project_id': '9d049e4b60b64716978ab415e6fbd5c0',
                         'uuid': str(uuid.uuid4()),
                         'display_name': 'test_instance',
                         'availability_zone': 'nova',
                         'host': 'some_host',
                         'security_groups': []}
        self.instance2 = {'project_id': '9d049e4b60b64716978ab415e6fbd5c0',
                         'uuid': str(uuid.uuid4()),
                         'display_name': 'test_instance2',
                         'availability_zone': 'nova',
                         'security_groups': []}
        self.nets1 = [{'id': 'my_netid1',
                      'name': 'my_netname1',
                      'tenant_id': 'my_tenantid'}]
        self.nets2 = []
        self.nets2.append(self.nets1[0])
        self.nets2.append({'id': 'my_netid2',
                           'name': 'my_netname2',
                           'tenant_id': 'my_tenantid'})
        self.nets3 = self.nets2 + [{'id': 'my_netid3',
                                    'name': 'my_netname3',
                                    'tenant_id': 'my_tenantid'}]
        self.nets4 = [{'id': 'his_netid4',
                      'name': 'his_netname4',
                      'tenant_id': 'his_tenantid'}]

        self.nets = [self.nets1, self.nets2, self.nets3, self.nets4]

        self.port_address = '10.0.1.2'
        self.port_data1 = [{'network_id': 'my_netid1',
                           'device_id': self.instance2['uuid'],
                           'device_owner': 'compute:nova',
                           'id': 'my_portid1',
                           'fixed_ips': [{'ip_address': self.port_address,
                                          'subnet_id': 'my_subid1'}],
                           'mac_address': 'my_mac1', }]
        self.float_data1 = [{'port_id': 'my_portid1',
                             'fixed_ip_address': self.port_address,
                             'floating_ip_address': '172.0.1.2'}]
        self.dhcp_port_data1 = [{'fixed_ips': [{'ip_address': '10.0.1.9',
                                               'subnet_id': 'my_subid1'}]}]
        self.port_address2 = '10.0.2.2'
        self.port_data2 = []
        self.port_data2.append(self.port_data1[0])
        self.port_data2.append({'network_id': 'my_netid2',
                                'device_id': self.instance['uuid'],
                                'device_owner': 'compute:nova',
                                'id': 'my_portid2',
                                'fixed_ips':
                                        [{'ip_address': self.port_address2,
                                          'subnet_id': 'my_subid2'}],
                                'mac_address': 'my_mac2', })
        self.float_data2 = []
        self.float_data2.append(self.float_data1[0])
        self.float_data2.append({'port_id': 'my_portid2',
                                 'fixed_ip_address': '10.0.2.2',
                                 'floating_ip_address': '172.0.2.2'})
        self.port_data3 = [{'network_id': 'my_netid1',
                           'device_id': 'device_id3',
                           'device_owner': 'compute:nova',
                           'id': 'my_portid3',
                           'fixed_ips': [],  # no fixed ip
                           'mac_address': 'my_mac3', }]
        self.subnet_data1 = [{'id': 'my_subid1',
                             'cidr': '10.0.1.0/24',
                             'network_id': 'my_netid1',
                             'gateway_ip': '10.0.1.1',
                             'dns_nameservers': ['8.8.1.1', '8.8.1.2']}]
        self.subnet_data2 = []
        self.subnet_data_n = [{'id': 'my_subid1',
                               'cidr': '10.0.1.0/24',
                               'network_id': 'my_netid1',
                               'gateway_ip': '10.0.1.1',
                               'dns_nameservers': ['8.8.1.1', '8.8.1.2']},
                              {'id': 'my_subid2',
                               'cidr': '20.0.1.0/24',
                              'network_id': 'my_netid2',
                              'gateway_ip': '20.0.1.1',
                              'dns_nameservers': ['8.8.1.1', '8.8.1.2']}]
        self.subnet_data2.append({'id': 'my_subid2',
                                  'cidr': '10.0.2.0/24',
                                  'network_id': 'my_netid2',
                                  'gateway_ip': '10.0.2.1',
                                  'dns_nameservers': ['8.8.2.1', '8.8.2.2']})

        self.fip_pool = {'id': '4fdbfd74-eaf8-4884-90d9-00bd6f10c2d3',
                         'name': 'ext_net',
                         'router:external': True,
                         'tenant_id': 'admin_tenantid'}
        self.fip_pool_nova = {'id': '435e20c3-d9f1-4f1b-bee5-4611a1dd07db',
                              'name': 'nova',
                              'router:external': True,
                              'tenant_id': 'admin_tenantid'}
        self.fip_unassociated = {'tenant_id': 'my_tenantid',
                                 'id': 'fip_id1',
                                 'floating_ip_address': '172.24.4.227',
                                 'floating_network_id': self.fip_pool['id'],
                                 'port_id': None,
                                 'fixed_ip_address': None,
                                 'router_id': None}
        fixed_ip_address = self.port_data2[1]['fixed_ips'][0]['ip_address']
        self.fip_associated = {'tenant_id': 'my_tenantid',
                               'id': 'fip_id2',
                               'floating_ip_address': '172.24.4.228',
                               'floating_network_id': self.fip_pool['id'],
                               'port_id': self.port_data2[1]['id'],
                               'fixed_ip_address': fixed_ip_address,
                               'router_id': 'router_id1'}
        self._returned_nw_info = []
        # self.mox.StubOutWithMock(neutronv2, 'get_client')
        # self.moxed_client = self.mox.CreateMock(client.Client)
        # self.addCleanup(CONF.reset)
        # self.addCleanup(self.mox.VerifyAll)
        # self.addCleanup(self.mox.UnsetStubs)
        # self.addCleanup(self.stubs.UnsetAll)


class TestNeutronv2(TestNeutronv2Base):

    def setUp(self):
        super(TestNeutronv2, self).setUp()
#        neutronv2.get_client(mox.IgnoreArg()).MultipleTimes().AndReturn(
#            self.moxed_client)

    def test_neutron_port_update(self):
        opt_list = [{'opt_name': 'bootfile-name', 'opt_value': 'pxelinux.0'},
                    {'opt_name': 'tftp-server',
                     'opt_value': '123.123.123.123'},
                    {'opt_name': 'server-ip-address',
                     'opt_value': '123.123.123.456'}]
        upd_opts = [{'opt_name': 'bootfile-name', 'opt_value': 'changeme.0'}]
        expected_opts = copy.deepcopy(opt_list)
        for i in expected_opts:
            if i['opt_name'] == upd_opts[0]['opt_name']:
                i['opt_value'] = upd_opts[0]['opt_value']
                break

        self.config(neutron_url='http://anyhost/',
                    neutron_url_timeout=30)
        my_context = context.RequestContext(user='userid',
                                            tenant='my_tenant',
                                            auth_token='token')
        # TODO(dekehn): needs to add the rest of the update, but we will need
        # to create an entire network with ports in order to modify them. Some
        # of whats below is bogus. But it was necessary to pep8 happy!
        with mock.patch.object(client.Client, "__init__") as mock_client_init:
            mock_client_init(auth_strategy=None, endpoint_url=CONF.neutron_url,
                             token=my_context.auth_token,
                             timeout=CONF.neutron_url_timeout, insecure=False,
                             ca_cert=None)
            mock_client_init.return_value = None
            neutronv2.get_client(my_context)
