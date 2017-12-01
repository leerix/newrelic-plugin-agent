"""
Redis Cluster Plugin

"""
from __future__ import absolute_import
import logging
import os
import random
import redis
from redis.sentinel import Sentinel, MasterNotFoundError

from newrelic_plugin_agent.plugins import base

LOGGER = logging.getLogger(__name__)


class RedisCluster(base.SocketStatsPlugin):

    GUID = 'com.meetme.newrelic_redis_cluster_agent'

    def get_config(self):
        self.node_list = self.config.get('nodes', [])
        self.master_name = self.config.get('master_name', 'redis-master')
        self.password = self.config.get('password', '')
        self.db = self.config.get('test_db', 5)
        self.tmp_master_file = '/tmp/last_redis_master'
        if not os.path.exists(self.tmp_master_file):
            with open(self.tmp_master_file, 'w') as f:
                f.write('')

    def add_master_slave_stats(self):
        master_normal = 1
        switch_over = 0
        slaves_list = []
        master_host = ''
        sentinel_list = [(node.get('host', 'localhost'),
                          node.get('sentinel_port', 26379))
                         for node in self.node_list]
        sentinel = Sentinel(sentinel_list, socket_timeout=5)
        try:
            master_host, master_port = sentinel.discover_master(self.master_name)
            last_master = ''
            with open(self.tmp_master_file, 'r') as f:
                last_master = f.readline().strip()
            if last_master != master_host:
                switch_over = 1
                with open(self.tmp_master_file, 'w') as f:
                    f.write(master_host)
        except MasterNotFoundError:
            master_normal = 0

        try:
            master_conn = sentinel.master_for(self.master_name,
                                              db=self.db,
                                              password=self.password)
            set_data = random.randint(0, 10)
            if master_conn.set('newrelic_redis_cluster_agent', set_data):
                if master_conn.get('newrelic_redis_cluster_agent') != str(set_data):
                    master_normal = 0
            else:
                master_normal = 0
        except MasterNotFoundError:
            master_normal = 0

        slaves_list = sentinel.discover_slaves(self.master_name)
        slaves_hosts = [slave[0] for slave in slaves_list]
        for node in self.node_list:
            host = node.get('host', 'localhost')
            status = 0
            if host == master_host:
                status = 2
            if host in slaves_hosts:
                status = 1
            self.add_gauge_value('Redis_Cluster/ClusterStatus/%s' % host,
                                 None, status, count=1)

        self.add_gauge_value('Redis_Cluster/SlavesNum', None,
                             len(slaves_list), count=1)
        self.add_gauge_value('Redis_Cluster/MasterStatus', None,
                             master_normal, count=1)
        self.add_gauge_value('Redis_Cluster/SwitchOver', None,
                             switch_over, count=1)

    def poll(self):
        self.initialize()
        self.get_config()
        self.add_master_slave_stats()
        self.finish()
