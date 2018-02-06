"""
Redis Queue Plugin

"""

from __future__ import absolute_import
import logging

from newrelic_plugin_agent.plugins import base

from redis.sentinel import Sentinel, MasterNotFoundError


class RedisQueues(base.SocketStatsPlugin):
    GUID = 'com.meetme.newrelic_redis_cluster_agent'

    def get_config(self):
        self.node_list = self.config.get('nodes', [])
        self.master_name = self.config.get('master_name', 'redis-master')
        self.password = self.config.get('password', '')
        self.queues = self.config.get('queues', '')
        self.db = self.config.get('db', 5)

    def add_queues_length_stats(self):
        if len(self.queues) == 0:
            return
        sentinel_list = [(node.get('host', 'localhost'),
                          node.get('sentinel_port', 26379))
                         for node in self.node_list]
        sentinel = Sentinel(sentinel_list, socket_timeout=5)
        master_host = ''
        queues_length_map = {}
        for queue in self.queues:
            queues_length_map[queue] = -1
        try:
            master_host, master_port = sentinel.discover_master(self.master_name)
            master_conn = sentinel.master_for(self.master_name,
                                              db=self.db,
                                              password=self.password)
            for queue in self.queues:
                try:
                    queues_length_map[queue] = master_conn.llen(queue)
                except Exception:
                    continue
        except Exception:
            pass

        for queue in self.queues:
            self.add_gauge_value('Redis_Queues/%s' % queue, None,
                                 queues_length_map[queue], count=1)

    def poll(self):
        self.initialize()
        self.get_config()
        self.add_queues_length_stats()
        self.finish()
