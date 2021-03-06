# Copyright 2014 Openstack Foundation
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
#

import json
import uuid

import netaddr
from neutron.openstack.common import log as logging
from oslo.config import cfg
import redis
import redis.sentinel

from quark import exceptions as q_exc
from quark import utils


CONF = cfg.CONF
LOG = logging.getLogger(__name__)
SECURITY_GROUP_VERSION_UUID_KEY = "id"
SECURITY_GROUP_RULE_KEY = "rules"

quark_opts = [
    cfg.StrOpt('redis_security_groups_host',
               default='127.0.0.1',
               help=_("The server to write security group rules to or "
                      "retrieve sentinel information from, as appropriate")),
    cfg.IntOpt('redis_security_groups_port',
               default=6379,
               help=_("The port for the redis server to write rules to or "
                      "retrieve sentinel information from, as appropriate")),
    cfg.BoolOpt("redis_use_sentinels",
                default=False,
                help=_("Tell the redis client to use sentinels rather than a "
                       "direct connection")),
    cfg.ListOpt("redis_sentinel_hosts",
                default=["localhost:26397"],
                help=_("Comma-separated list of host:port pairs for Redis "
                       "sentinel hosts")),
    cfg.StrOpt("redis_sentinel_master",
               default='',
               help=_("The name label of the master redis sentinel")),
    cfg.BoolOpt("redis_use_ssl",
                default=False,
                help=_("Configures whether or not to use SSL")),
    cfg.StrOpt("redis_ssl_certfile",
               default='',
               help=_("Path to the SSL cert")),
    cfg.StrOpt("redis_ssl_keyfile",
               default='',
               help=_("Path to the SSL keyfile")),
    cfg.StrOpt("redis_ssl_ca_certs",
               default='',
               help=_("Path to the SSL CA certs")),
    cfg.StrOpt("redis_ssl_cert_reqs",
               default='none',
               help=_("Certificate requirements. Values are 'none', "
                      "'optional', and 'required'")),
    cfg.StrOpt("redis_db",
               default="0",
               help=("The database number to use")),
    cfg.FloatOpt("redis_socket_timeout",
                 default=0.1,
                 help=("Timeout for Redis socket operations"))]

CONF.register_opts(quark_opts, "QUARK")

# TODO(mdietz): Rewrite this to use a module level connection
#               pool, and then incorporate that into creating
#               connections. When connecting to a master we
#               connect by creating a redis client, and when
#               we connect to a slave, we connect by telling it
#               we want a slave and ending up with a connection,
#               with no control over SSL or anything else.  :-|


class Client(object):
    connection_pool = None

    def __init__(self, use_master=False):
        self._ensure_connection_pool_exists()
        self._sentinel_list = None
        self._use_master = use_master

        try:
            if CONF.QUARK.redis_use_sentinels:
                self._client = self._client_from_sentinel(self._use_master)
            else:
                self._client = self._client_from_config()

        except redis.ConnectionError as e:
            LOG.exception(e)
            raise q_exc.RedisConnectionFailure()

    def _ensure_connection_pool_exists(self):
        if not Client.connection_pool:
            LOG.info("Creating redis connection pool for the first time...")
            host = CONF.QUARK.redis_security_groups_host
            port = CONF.QUARK.redis_security_groups_port
            LOG.info("Using redis host %s:%s" % (host, port))

            connect_class = redis.Connection
            connect_kw = {"host": host, "port": port}

            if CONF.QUARK.redis_use_ssl:
                LOG.info("Communicating with redis over SSL")
                connect_class = redis.SSLConnection
                if CONF.QUARK.redis_ssl_certfile:
                    cert_req = CONF.QUARK.redis_ssl_cert_reqs
                    connect_kw["ssl_certfile"] = CONF.QUARK.redis_ssl_certfile
                    connect_kw["ssl_cert_reqs"] = cert_req
                    connect_kw["ssl_ca_certs"] = CONF.QUARK.redis_ssl_ca_certs
                    connect_kw["ssl_keyfile"] = CONF.QUARK.redis_ssl_keyfile

            klass = redis.ConnectionPool
            if CONF.QUARK.redis_use_sentinels:
                klass = redis.sentinel.SentinelConnectionPool

            Client.connection_pool = klass(connection_class=connect_class,
                                           **connect_kw)

    def _get_sentinel_list(self):
        if not self._sentinel_list:
            self._sentinel_list = [tuple(host.split(':'))
                                   for host in CONF.QUARK.redis_sentinel_hosts]
            if not self._sentinel_list:
                raise TypeError("sentinel_list is not a properly formatted"
                                "list of 'host:port' pairs")

        return self._sentinel_list

    def _client_from_config(self):
        kwargs = {"connection_pool": Client.connection_pool,
                  "db": CONF.QUARK.redis_db,
                  "socket_timeout": CONF.QUARK.redis_socket_timeout}
        return redis.StrictRedis(**kwargs)

    def _client_from_sentinel(self, is_master=True):
        master = is_master and "master" or "slave"
        LOG.info("Initializing redis connection to %s node, master label %s" %
                 (master, CONF.QUARK.redis_sentinel_master))

        sentinel = redis.sentinel.Sentinel(self._get_sentinel_list())
        func = sentinel.slave_for
        if is_master:
            func = sentinel.master_for

        return func(CONF.QUARK.redis_sentinel_master,
                    db=CONF.QUARK.redis_db,
                    socket_timeout=CONF.QUARK.redis_socket_timeout,
                    connection_pool=Client.connection_pool)

    def serialize_rules(self, rules):
        """Creates a payload for the redis server."""
        # TODO(mdietz): If/when we support other rule types, this comment
        #               will have to be revised.
        # Action and direction are static, for now. The implementation may
        # support 'deny' and 'egress' respectively in the future. We allow
        # the direction to be set to something else, technically, but current
        # plugin level call actually raises. It's supported here for unit
        # test purposes at this time
        serialized = []
        for rule in rules:
            direction = rule["direction"]
            source = ''
            destination = ''
            if rule["remote_ip_prefix"]:
                if direction == "ingress":
                    source = netaddr.IPNetwork(rule["remote_ip_prefix"])
                    source = str(source.ipv6())
                else:
                    destination = netaddr.IPNetwork(
                        rule["remote_ip_prefix"])
                    destination = str(destination.ipv6())

            serialized.append(
                {"ethertype": rule["ethertype"],
                 "protocol": rule["protocol"],
                 "port start": rule["port_range_min"],
                 "port end": rule["port_range_max"],
                 "source network": source,
                 "destination network": destination,
                 "action": "allow",
                 "direction": "ingress"})
        return serialized

    def serialize_groups(self, groups):
        """Creates a payload for the redis server

        The rule schema is the following:

        REDIS KEY - port_device_id.port_mac_address
        REDIS VALUE - A JSON dump of the following:

        {"id": "<arbitrary uuid>",
         "rules": [
           {"ethertype": <hexademical integer>,
            "protocol": <integer>,
            "port start": <integer>,
            "port end": <integer>,
            "source network": <string>,
            "destination network": <string>,
            "action": <string>,
            "direction": <string>},
          ]
        }

        Example:
        {"id": "004c6369-9f3d-4d33-b8f5-9416bf3567dd",
         "rules": [
           {"ethertype": 0x800,
            "protocol": "tcp",
            "port start": 1000,
            "port end": 1999,
            "source network": "10.10.10.0/24",
            "destination network": "",
            "action": "allow",
            "direction": "ingress"},
          ]
        }
        """
        rules = []
        for group in groups:
            rules.extend(self.serialize_rules(group.rules))
        return rules

    def rule_key(self, device_id, mac_address):
        return "{0}.{1}".format(device_id, str(netaddr.EUI(mac_address)))

    def get_rules_for_port(self, device_id, mac_address):
        return json.loads(self._client.get(
            self.rule_key(device_id, mac_address)))

    def apply_rules(self, device_id, mac_address, rules):
        """Writes a series of security group rules to a redis server."""
        LOG.info("Applying security group rules for device %s with MAC %s" %
                 (device_id, mac_address))
        if not self._use_master:
            raise q_exc.RedisSlaveWritesForbidden()

        ruleset_uuid = str(uuid.uuid4())
        rule_dict = {SECURITY_GROUP_VERSION_UUID_KEY: ruleset_uuid,
                     SECURITY_GROUP_RULE_KEY: rules}
        redis_key = self.rule_key(device_id, mac_address)
        try:
            self._client.set(redis_key, json.dumps(rule_dict))
        except redis.ConnectionError as e:
            LOG.exception(e)
            raise q_exc.RedisConnectionFailure()

    def echo(self, echo_str):
        return self._client.echo(echo_str)

    def vif_keys(self):
        return self._client.keys("*.??-??-??-??-??-??")

    def delete_vif_rules(self, key):
        self._client.delete(key)

    @utils.retry_loop(3)
    def get_security_groups(self, new_interfaces):
        """Gets security groups for interfaces from Redis

        Returns a dictionary of xapi.VIFs mapped to security group version
        UUIDs from a set of xapi.VIF.
        """

        new_interfaces = tuple(new_interfaces)

        p = self._client.pipeline()
        for vif in new_interfaces:
            p.get(str(vif))
        security_groups = p.execute()

        ret = {}
        for vif, security_group in zip(new_interfaces, security_groups):
            security_group_uuid = None
            if security_group:
                security_group_uuid = json.loads(security_group).get(
                    SECURITY_GROUP_VERSION_UUID_KEY)
            ret[vif] = security_group_uuid
        return ret
