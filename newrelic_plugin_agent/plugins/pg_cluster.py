"""
PostgreSQL Cluster Plugin

"""
import logging
import os
import psycopg2
from psycopg2 import extras

from newrelic_plugin_agent.plugins import base

LOGGER = logging.getLogger(__name__)

CLUSTER_ROLE = """
SELECT pg_is_in_recovery();
"""
DATABASE = 'SELECT * FROM pg_stat_database;'


class PostgreSqlCluster(base.HTTPStatsPlugin):

    GUID = 'com.meetme.newrelic_postgresql_cluster_agent'

    def get_config(self):
        self.node_list = self.config.nodes
        self.dbname = self.config.get('dbname', 'template0')
        self.user = self.config.get('user', 'postgres')
        self.password = self.config.get('password', '')
        self.cluster_host = self.config.get('cluster_host', 'localhost')
        self.cluster_port = self.config.get('cluster_port', 5432)
        self.tmp_master_file = '/tmp/last_pg_master'
        if not os.path.exists(self.tmp_master_file):
            with open(self.tmp_master_file, 'w') as f:
                f.write('')

    def add_http_status_stats(self):
        status = 0
        status_servers_num = 0
        for node in self.node_list:
            host = node.get('host', 'localhost')
            status_port = node.get('status_port', '15432')
            url = 'http://%s:%s/' % (host, status_port)
            result = self.http_get(url=url)
            # for governor http status
            # http_status   |   cluster role    |   metrics
            # 200           |   master          |   2
            # 502           |   slave           |   1
            # error         |   offline         |   0
            if result == '':
                status = 0
            elif result is None:
                status = 1
            else:
                status = 2

            if status > 0:
                status_servers_num += 1

            self.add_gauge_value('PG_Cluster/HttpStatus/%s' % host,
                                 None,
                                 status,
                                 count=1)

        self.add_gauge_value('PG_Cluster/HttpStatusServersNum',
                             None,
                             status_servers_num,
                             count=1)

    def add_master_slave_stats(self):
        cluster_roles = {}
        master = ''
        slaves_number = 0
        for node in self.node_list:
            host = node.get('host', 'localhost')
            kwargs = {'host': host,
                      'port': node.get('port', 5432),
                      'user': self.user,
                      'password': self.password,
                      'database': self.dbname}
            try:
                conn = psycopg2.connect(**kwargs)
            except:
                cluster_roles[host] = 0
                continue

            cursor = conn.cursor(cursor_factory=extras.RealDictCursor)
            cursor.execute(CLUSTER_ROLE)
            data = cursor.fetchone()
            cursor.close()
            conn.close()
            cluster_roles[host] = 1
            if not data.get('pg_is_in_recovery', True):
                cluster_roles[host] = 2
                master = host
            else:
                slaves_number += 1

            self.add_gauge_value('PG_Cluster/ClusterRole/%s' % host,
                                 None,
                                 cluster_roles[host],
                                 count=1)

        self.add_gauge_value('PG_Cluster/SlavesNum',
                             None,
                             slaves_number,
                             count=1)

        switch_over = 0
        last_master = ''
        with open(self.tmp_master_file, 'r') as f:
            last_master = f.readline().strip()

        if master != last_master:
            switch_over = 1
            with open(self.tmp_master_file, 'w') as f:
                f.write(master)

        self.add_gauge_value('PG_Cluster/SwitchOver',
                             None,
                             switch_over,
                             count=1)

    def add_cluster_stats(self):
        status = 1
        kwargs = {'host': self.cluster_host,
                  'port': self.cluster_port,
                  'user': self.user,
                  'password': self.password,
                  'database': self.dbname}
        data = {}
        try:
            conn = psycopg2.connect(**kwargs)
            cursor = conn.cursor(cursor_factory=extras.RealDictCursor)
            cursor.execute(DATABASE)
            data = cursor.fetchall()
            cursor.close()
            conn.close()
        except:
            data = {}

        if not data:
            status = 0

        self.add_gauge_value('PG_Cluster/ClusterStatus',
                             None,
                             status,
                             count=1)

    def poll(self):
        self.initialize()
        self.get_config()
        self.add_http_status_stats()
        self.add_master_slave_stats()
        self.add_cluster_stats()
        self.finish()
