# Copyright 2013 Openstack Foundation
# All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
#  under the License.

import json
import uuid

import mock
import netaddr

from quark.drivers import unmanaged
from quark import network_strategy
from quark.tests import test_base


class TestUnmanagedDriver(test_base.TestBase):
    def setUp(self):
        super(TestUnmanagedDriver, self).setUp()
        self.strategy = {"public_network": {"bridge": "xenbr0"}}
        strategy_json = json.dumps(self.strategy)
        self.driver = unmanaged.UnmanagedDriver()
        unmanaged.STRATEGY = network_strategy.JSONStrategy(strategy_json)

    def test_load_config(self):
        self.driver.load_config()

    def test_get_name(self):
        self.assertEqual(self.driver.get_name(), "UNMANAGED")

    def test_get_connection(self):
        self.driver.get_connection()

    def test_create_network(self):
        self.driver.create_network(context=self.context,
                                   network_name="testwork")

    def test_delete_network(self):
        self.driver.delete_network(context=self.context, network_id=1)

    def test_diag_network(self):
        self.assertEqual(self.driver.diag_network(context=self.context,
                                                  network_id=2), {})

    def test_diag_port(self):
        self.assertEqual(self.driver.diag_port(context=self.context,
                                               network_id=2), {})

    def test_create_port(self):
        self.driver.create_port(context=self.context,
                                network_id="public_network", port_id=2)

    def test_update_port(self):
        self.driver.update_port(context=self.context,
                                network_id="public_network", port_id=2)

    @mock.patch("quark.security_groups.redis_client.Client")
    def test_update_port_with_security_groups(self, redis_cli):
        mock_client = mock.MagicMock()
        redis_cli.return_value = mock_client

        port_id = str(uuid.uuid4())
        device_id = str(uuid.uuid4())
        mac_address = netaddr.EUI("AA:BB:CC:DD:EE:FF").value
        security_groups = [str(uuid.uuid4())]
        payload = {}
        mock_client.serialize_groups.return_value = payload
        self.driver.update_port(
            context=self.context, network_id="public_network", port_id=port_id,
            device_id=device_id, mac_address=mac_address,
            security_groups=security_groups)
        mock_client.serialize_groups.assert_called_once_with(security_groups)
        mock_client.apply_rules.assert_called_once_with(
            device_id, mac_address, payload)

    def test_delete_port(self):
        self.driver.delete_port(context=self.context, port_id=2)

    def test_create_security_group(self):
        self.driver.create_security_group(context=self.context,
                                          group_name="mygroup")

    def test_delete_security_group(self):
        self.driver.delete_security_group(context=self.context,
                                          group_id=3)

    def test_update_security_group(self):
        self.driver.update_security_group(context=self.context,
                                          group_id=3)

    def test_create_security_group_rule(self):
        rule = {'ethertype': 'IPv4', 'direction': 'ingress'}
        self.driver.create_security_group_rule(context=self.context,
                                               group_id=3,
                                               rule=rule)

    def test_delete_security_group_rule(self):
        rule = {'ethertype': 'IPv4', 'direction': 'ingress'}
        self.driver.delete_security_group_rule(context=self.context,
                                               group_id=3,
                                               rule=rule)
