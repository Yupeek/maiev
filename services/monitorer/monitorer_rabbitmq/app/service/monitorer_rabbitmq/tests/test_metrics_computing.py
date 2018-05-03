# -*- coding: utf-8 -*-
import mock
import pytest

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

    return m


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
        assert 'load_passed' not in monitorer.services_to_track
        monitorer.track('load_passed')
        assert 'load_passed' in monitorer.services_to_track

    def test_rpc_get_queue_stats(self, monitorer: MonitorerRabbitmq):
        assert monitorer.get_queue_stats("not_launched") is None
        assert monitorer.get_queue_stats("launched_idle") == {u'consumers': 1, u'messages_ready': 0}

    def test_rpc_compute_queue(self, monitorer: MonitorerRabbitmq):
        assert monitorer.compute_queue('loaded') == {
            'exists': True, 'waiting': 0, 'latency': 0.0,
            'rate': 1.400000000000034, 'call_rate': 269.2, 'exec_rate': 270.6, 'consumers': 1
        }

    def test_timer_time_tick(self, monitorer: MonitorerRabbitmq):
        assert monitorer.dispatch.call_count == 0
        monitorer.track('launched_idle')
        assert monitorer.dispatch.call_count == 0
        monitorer.track('not_launched')
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
