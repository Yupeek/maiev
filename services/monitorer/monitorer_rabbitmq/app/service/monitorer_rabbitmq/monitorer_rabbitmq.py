# -*- coding: utf-8 -*-
import logging

from common.utils import log_all
from nameko.events import EventDispatcher
from nameko.rpc import rpc
from nameko.timer import timer
from service.dependency.rabbitmq import RabbitMq

logger = logging.getLogger(__name__)


class MonitorerRabbitmq(object):
    """
    the monitorer that track rabbitmq stats to
    report performance issues

    public events
    #############

    - metric_updated(): Service

    rcp
    ###

    track(identifier)

    """
    name = 'monitorer_rabbitmq'
    dispatch = EventDispatcher()
    rabbitmq = RabbitMq()
    """
    :type: service.dependency.rabbitmq.RabbitMqApi
    """
    services_to_track = {'rpc-producer'}

    # ####################################################
    #                 EVENTS
    # ####################################################

    # no events

    # ####################################################
    #                 RPC
    # ####################################################

    @rpc
    @log_all
    def track(self, queue_identifier):
        """
        create a service on the valide scaler
        :param service:
        :return:
        """
        logger.debug("will track %s", queue_identifier)
        self.services_to_track |= {queue_identifier}

    # ####################################################
    #                     TIMER
    # $###################################################

    @timer(interval=5)
    @log_all
    def print_status(self):

        for queue_name in self.services_to_track:
            metrics = self._compute_queue(queue_name)
            if metrics is not None:
                self.dispatch("metrics_updated", {
                    'monitorer': "monitorer_rabbitmq",
                    'identifier': queue_name,
                    'metrics': metrics
                })

    # ####################################################
    #                 PRIVATE
    # ####################################################

    def _compute_queue(self, qname):
        data = self.rabbitmq.get_queue_stats(qname, columns='message_stats,messages_ready,consumers')
        if data is None:
            # queue don't exists.
            return {
                "exists": False,
                "waiting": 0,
                "latency": None,
                "rate": None,
                "call_rate": 0,
                "exec_rate": 0,
                "consumers": 0,
            }
        try:
            stats_ = data['message_stats']
        except KeyError:
            # new queue, never ever had messages
            prate, drate = 0, 0
            latency = None
            empty_rate = None
        else:
            prate = stats_.get('publish_details', {}).get('rate', 0)
            drate = stats_.get('deliver_details', {}).get('rate', 0)
            empty_rate = drate - prate
            try:
                latency = data['messages_ready'] / drate
            except ZeroDivisionError:
                latency = None
        return {
            "exists": True,
            "waiting": data['messages_ready'],
            "latency": latency,
            "rate": empty_rate,
            "call_rate": prate,
            "exec_rate": drate,
            "consumers": data['consumers']
        }
