# -*- coding: utf-8 -*-
import mock
import pytest

from service.dependency.rabbitmq import RabbitMq, RabbitMqApi
from service.monitorer_rabbitmq.monitorer_rabbitmq import MonitorerRabbitmq


@pytest.fixture
def rmq_result():
    return {
        "launched_idle": {u'consumers': 1, u'messages_ready': 0},
        "not_launched": None,
        "reader_no_activity": {u'consumers': 1, u'messages_ready': 0},
        "loaded": {u'consumers': 1,
                   u'message_stats': {u'ack': 1363,
                                      u'ack_details': {u'rate': 272.6},
                                      u'deliver': 1363,
                                      u'deliver_details': {u'rate': 270.6},
                                      u'deliver_get': 1363,
                                      u'deliver_get_details': {u'rate': 270.6},
                                      u'deliver_no_ack': 0,
                                      u'deliver_no_ack_details': {u'rate': 0.0},
                                      u'get': 0,
                                      u'get_details': {u'rate': 0.0},
                                      u'get_no_ack': 0,
                                      u'get_no_ack_details': {u'rate': 0.0},
                                      u'publish': 1373,
                                      u'publish_details': {u'rate': 269.2},
                                      u'redeliver': 0,
                                      u'redeliver_details': {u'rate': 0.0}},
                   u'messages_ready': 0},
        "load_passed": {u'consumers': 1,
                        u'message_stats': {u'ack': 5021,
                                           u'ack_details': {u'rate': 0.0},
                                           u'deliver': 5021,
                                           u'deliver_details': {u'rate': 0.0},
                                           u'deliver_get': 5021,
                                           u'deliver_get_details': {u'rate': 0.0},
                                           u'deliver_no_ack': 0,
                                           u'deliver_no_ack_details': {u'rate': 0.0},
                                           u'get': 0,
                                           u'get_details': {u'rate': 0.0},
                                           u'get_no_ack': 0,
                                           u'get_no_ack_details': {u'rate': 0.0},
                                           u'publish': 5021,
                                           u'publish_details': {u'rate': 0.0},
                                           u'redeliver': 0,
                                           u'redeliver_details': {u'rate': 0.0}},
                        u'messages_ready': 0},
        "loaded_scaled_down": {u'consumers': 0,
                               u'message_stats': {u'ack': 5021,
                                                  u'ack_details': {u'rate': 0.0},
                                                  u'deliver': 5021,
                                                  u'deliver_details': {u'rate': 0.0},
                                                  u'deliver_get': 5021,
                                                  u'deliver_get_details': {u'rate': 0.0},
                                                  u'deliver_no_ack': 0,
                                                  u'deliver_no_ack_details': {u'rate': 0.0},
                                                  u'get': 0,
                                                  u'get_details': {u'rate': 0.0},
                                                  u'get_no_ack': 0,
                                                  u'get_no_ack_details': {u'rate': 0.0},
                                                  u'publish': 5021,
                                                  u'publish_details': {u'rate': 0.0},
                                                  u'redeliver': 0,
                                                  u'redeliver_details': {u'rate': 0.0}},
                               u'messages_ready': 0}

    }


@pytest.fixture
def monitorer(rmq_result):
    m = MonitorerRabbitmq()
    m.services_to_track = set()
    m.rabbitmq = mock.Mock()
    m.dispatch = mock.Mock()
    m.rabbitmq.get_queue_stats.side_effect = lambda qname, columns: rmq_result.get(qname)
    m.mongo = mock.Mock()

    return m


def dp_rabbitmq_factory(param) -> RabbitMq:
    m = RabbitMq()
    m.container = mock.Mock(config={
        'AMQP_URI': param['AMQP_URI']
    })
    return m


@pytest.fixture
def dp_rabbitmq():
    return dp_rabbitmq_factory({'AMQP_URI': 'amqp://maiev:Paaswd@rbmq/gmd'})


def rabbitm_api_factory(param) -> RabbitMqApi:
    api = RabbitMqApi(param['API_URL'], param['vhost'])
    api.session = mock.Mock()
    return api


@pytest.fixture
def rabbitm_api():
    return rabbitm_api_factory({'API_URL': 'http://maiev:Paaswd@rbmq:15672/api', 'vhost': '/'})


class TestRabbitmAPI(object):

    @pytest.mark.parametrize('env', [
        {'API_URL': 'http://maiev:Paaswd@rbmq:15672/api', 'vhost': '/', 'AMQP_URI': 'amqp://maiev:Paaswd@rbmq/'},
        {'API_URL': 'http://maiev:Paaswd@rbmq:15672/api', 'vhost': 'gmd', 'AMQP_URI': 'amqp://maiev:Paaswd@rbmq/gmd'},
    ], ids=['/', 'gmd'])
    def test_default_vhost(self, env):
        rabbitmq = dp_rabbitmq_factory(env)

        assert rabbitmq.get_default_url() == env['API_URL']
        assert rabbitmq.get_default_vhost() == env['vhost']

    @pytest.mark.parametrize('env', [
        {'API_URL': 'http://maiev:Paaswd@rbmq:15672/api',
         'vhost': '/', 'vhost_enc': '%2F', 'AMQP_URI': 'amqp://maiev:Paaswd@rbmq/'},
        {'API_URL': 'http://maiev:Paaswd@rbmq:15672/api',
         'vhost': 'gmd', 'vhost_enc': 'gmd', 'AMQP_URI': 'amqp://maiev:Paaswd@rbmq/gmd'},
    ], ids=['/', 'gmd'])
    def test_api_query(self, env):
        api = rabbitm_api_factory(env)
        api.session.get.return_value = mock.Mock(
            status_code=200,
            json=mock.Mock(return_value={u'consumers': 1, u'messages_ready': 0}),
            status_text='ok',
        )
        r = api.get_queue_stats('rpc-wrapper-service')
        assert r == {u'consumers': 1, u'messages_ready': 0}
        api.session.get.assert_called_once_with(
            "%(API_URL)s/queues/%(vhost_enc)s/rpc-wrapper-service" % env
        )


class TestMonitorQueue(object):

    @pytest.mark.parametrize('queue,result', [
        ("launched_idle",
         {'exists': True, 'waiting': 0, 'latency': None,
          'rate': None, 'call_rate': 0, 'exec_rate': 0, 'consumers': 1}),
        ("not_launched",
         {'exists': False, 'waiting': 0, 'latency': None,
          'rate': None, 'call_rate': 0, 'exec_rate': 0, 'consumers': 0}),
        ("reader_no_activity",
         {'exists': True, 'waiting': 0, 'latency': None,
          'rate': None, 'call_rate': 0, 'exec_rate': 0, 'consumers': 1}),
        ("loaded",
         {'exists': True, 'waiting': 0, 'latency': 0.0,
          'rate': 1.400000000000034, 'call_rate': 269.2, 'exec_rate': 270.6, 'consumers': 1}),
        ("load_passed",
         {'exists': True, 'waiting': 0, 'latency': None,
          'rate': 0.0, 'call_rate': 0.0, 'exec_rate': 0.0, 'consumers': 1}),
        ("loaded_scaled_down",
         {'exists': True, 'waiting': 0, 'latency': None,
          'rate': 0.0, 'call_rate': 0.0, 'exec_rate': 0.0, 'consumers': 0}),

    ])
    def test_parsing_states(self, monitorer: MonitorerRabbitmq, queue, result):
        assert monitorer._compute_queue(queue) == result

    def test_rpc_track(self, monitorer: MonitorerRabbitmq):
        monitorer.track('load_passed')
        monitorer.mongo.service_to_track.replace_one.assert_called()

    def test_rpc_get_queue_stats(self, monitorer: MonitorerRabbitmq):
        assert monitorer.get_queue_stats("not_launched") is None
        assert monitorer.get_queue_stats("launched_idle") == {u'consumers': 1, u'messages_ready': 0}

    def test_rpc_compute_queue(self, monitorer: MonitorerRabbitmq):
        assert monitorer.compute_queue('loaded') == {
            'exists': True, 'waiting': 0, 'latency': 0.0,
            'rate': 1.400000000000034, 'call_rate': 269.2, 'exec_rate': 270.6, 'consumers': 1
        }

    def test_timer_time_tick(self, monitorer: MonitorerRabbitmq):
        l_iter = iter([{"name": "launched_idle", "last_check": None}, {"name": "not_launched", "last_check": None}])

        def se(**kwarg):
            try:
                return next(l_iter)
            except StopIteration:
                return None
        monitorer.mongo.service_to_track.find_and_modify.side_effect = se
        assert monitorer.dispatch.call_count == 0
        monitorer.time_tick()
        assert monitorer.dispatch.call_count == 2
        monitorer.dispatch.assert_any_call("metrics_updated", {
            'monitorer': "monitorer_rabbitmq",
            'identifier': "launched_idle",
            'metrics': {'exists': True, 'waiting': 0, 'latency': None,
                        'rate': None, 'call_rate': 0, 'exec_rate': 0, 'consumers': 1}
        })
        monitorer.dispatch.assert_any_call("metrics_updated", {
            'monitorer': "monitorer_rabbitmq",
            'identifier': "not_launched",
            'metrics': {'exists': False, 'waiting': 0, 'latency': None,
                        'rate': None, 'call_rate': 0, 'exec_rate': 0, 'consumers': 0}
        })
